from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..backoffice_copilot.storage.clickhouse_connection import (
    ClickHouseWriteConfig,
    build_clickhouse_batch_write_client,
)
from ..backoffice_copilot.storage.clickhouse_ingest import (
    CanonicalAuditMappingError,
    compute_clickhouse_raw_fact_dedup_key,
    map_canonical_audit_payload_to_clickhouse_row,
)
from ..backoffice_copilot.storage.clickhouse_repository import (
    ClickHouseAuditEventWriterRepository,
    ClickHouseBatchWriteRequest,
    ClickHouseBatchWriteRetryPolicy,
)
from ..backoffice_copilot.storage.clickhouse_validators import ClickHouseAuditEventInsertRow
from ..d0_mvp.state.etl_processed_ledger import (
    ETLProcessedS3ObjectIdentity,
    ETLProcessedS3ObjectLedger,
)
from ..d0_mvp.state.redis_client import RedisLike, build_runtime_redis_from_env
from ..storage_env import (
    ETLWorkerConfig,
    StorageOperationalConfigError,
    load_etl_worker_config_from_env,
    validate_clickhouse_ingest_env_for_prod,
)

logger = logging.getLogger(__name__)


class ETLIngestError(RuntimeError):
    """Raised when one S3 archive object cannot be ingested into ClickHouse."""


class ETLConfigurationError(StorageOperationalConfigError):
    """Raised when the ETL worker is missing required operational config."""


@dataclass(slots=True, frozen=True)
class S3AuditIngestResult:
    key: str
    object_etag: str | None
    source_row_count: int
    attempted_row_count: int
    accepted_row_count: int
    duplicate_row_count: int
    flush_count: int
    batch_size: int
    retry_max_attempts: int
    retry_backoff_ms: int
    skipped_by_processed_ledger: bool


@dataclass(slots=True, frozen=True)
class S3ArchiveObjectMetadata:
    key: str
    etag: str | None = None


def _ensure_clickhouse_ingest_operational_config(config: ETLWorkerConfig) -> None:
    if not (config.s3.bucket or "").strip():
        raise ETLConfigurationError("TM_S3_BUCKET must be set to run the ClickHouse ETL worker.")
    if not config.clickhouse.enabled:
        raise ETLConfigurationError("TM_CLICKHOUSE_URL must be set to run the ClickHouse ETL worker.")


class ETLWorker:
    """ETL process to move rotated audit JSONL files from S3 into ClickHouse."""

    def __init__(
        self,
        config: ETLWorkerConfig,
        *,
        s3_client: Any | None = None,
        clickhouse_writer: ClickHouseAuditEventWriterRepository | None = None,
        clickhouse_client: Any | None = None,
        processed_key_ledger: ETLProcessedS3ObjectLedger | None = None,
        processed_key_redis: RedisLike | None = None,
    ) -> None:
        self.config = config
        self.s3_bucket = config.s3.bucket or ""
        self.s3_prefix = config.s3.prefix
        self.s3 = s3_client or self._build_s3_client(region_name=config.s3.region)
        self.writer = clickhouse_writer or self._build_default_clickhouse_writer(
            clickhouse_client=clickhouse_client,
        )
        self.retry_policy = ClickHouseBatchWriteRetryPolicy(
            max_attempts=config.clickhouse.write_retry_max_attempts,
            backoff_ms=config.clickhouse.write_retry_backoff_ms,
        )
        self.processed_key_ledger = processed_key_ledger or self._build_default_processed_key_ledger(
            redis_client=processed_key_redis,
        )

    @staticmethod
    def _build_s3_client(*, region_name: str | None) -> Any:
        try:
            import boto3
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "boto3 is required to construct the ETL worker S3 client. "
                "Install boto3 or inject s3_client explicitly."
            ) from exc
        return boto3.client("s3", region_name=region_name)

    def _build_default_clickhouse_writer(
        self,
        *,
        clickhouse_client: Any | None,
    ) -> ClickHouseAuditEventWriterRepository:
        write_config = ClickHouseWriteConfig(
            url=self.config.clickhouse.url,
            table_name=self.config.clickhouse.audit_table,
            batch_size=self.config.clickhouse.ingest_batch_size,
            timeout_ms=self.config.clickhouse.ingest_timeout_ms,
        )
        client = clickhouse_client or build_clickhouse_batch_write_client(write_config)
        return ClickHouseAuditEventWriterRepository(client=client, config=write_config)

    def _build_default_processed_key_ledger(
        self,
        *,
        redis_client: RedisLike | None,
    ) -> ETLProcessedS3ObjectLedger:
        resolved_redis = redis_client
        if resolved_redis is None:
            try:
                resolved_redis, _ = build_runtime_redis_from_env()
            except ValueError as exc:
                raise ETLConfigurationError(
                    "TM_REDIS_URL must be set to run the ClickHouse ETL worker processed-key ledger."
                ) from exc
        return ETLProcessedS3ObjectLedger(
            resolved_redis,
            ttl_s=self.config.processed_ledger.ttl_seconds,
        )

    @classmethod
    def from_env(cls) -> ETLWorker:
        """Build the ClickHouse ETL worker from env config."""

        try:
            validate_clickhouse_ingest_env_for_prod()
        except StorageOperationalConfigError as exc:
            raise ETLConfigurationError(str(exc)) from exc
        return cls(load_etl_worker_config_from_env())

    def run_once(self) -> int:
        """Scan S3 for archived audit JSONL files and ingest them into ClickHouse."""

        self._ensure_runtime_ingest_config()

        total_rows = 0
        for object_metadata in self._iter_source_objects():
            result = self._process_s3_file(object_metadata)
            total_rows += result.accepted_row_count
        return total_rows

    def replay_key(self, key: str, *, force: bool = False) -> S3AuditIngestResult:
        """Replay one explicit archive object into ClickHouse."""

        if not key or not self._is_ingest_candidate_key(key):
            raise ETLIngestError("replay key must be one .jsonl archive object.")
        return self._process_s3_file(
            self._get_explicit_object_metadata(key),
            force_replay=force,
        )

    def replay_keys(self, keys: list[str], *, force: bool = False) -> int:
        """Replay a fixed archive object list in order."""

        total_rows = 0
        for key in keys:
            result = self.replay_key(key, force=force)
            total_rows += result.accepted_row_count
        return total_rows

    def _ensure_runtime_ingest_config(self) -> None:
        if not self.s3_bucket:
            raise ETLConfigurationError(
                "TM_S3_BUCKET must be set to run the ClickHouse ETL worker."
            )
        if not self.config.clickhouse.enabled:
            raise ETLConfigurationError(
                "TM_CLICKHOUSE_URL must be set to run the ClickHouse ETL worker."
            )
        if self.processed_key_ledger.ttl_s <= 0:
            raise ETLConfigurationError(
                "TM_ETL_PROCESSED_LEDGER_TTL_SECONDS must be a positive integer."
            )

    def _iter_source_objects(self) -> list[S3ArchiveObjectMetadata]:
        objects: list[S3ArchiveObjectMetadata] = []
        continuation_token: str | None = None
        while True:
            request: dict[str, object] = {
                "Bucket": self.s3_bucket,
                "Prefix": self.s3_prefix,
            }
            if continuation_token is not None:
                request["ContinuationToken"] = continuation_token

            response = self.s3.list_objects_v2(**request)
            for obj in response.get("Contents", []):
                key = obj.get("Key")
                if isinstance(key, str) and self._is_ingest_candidate_key(key):
                    objects.append(
                        S3ArchiveObjectMetadata(
                            key=key,
                            etag=self._normalize_s3_etag(obj.get("ETag")),
                        )
                    )

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                break
        return objects

    def _get_explicit_object_metadata(self, key: str) -> S3ArchiveObjectMetadata:
        etag: str | None = None
        head_object = getattr(self.s3, "head_object", None)
        if callable(head_object):
            try:
                head_response = head_object(Bucket=self.s3_bucket, Key=key)
            except Exception as exc:
                logger.warning(
                    "Falling back to bucket/key processed-key identity for key=%s because S3 head_object failed: %s",
                    key,
                    exc,
                )
            else:
                etag = self._normalize_s3_etag(head_response.get("ETag"))
        return S3ArchiveObjectMetadata(key=key, etag=etag)

    def _process_s3_file(
        self,
        object_metadata: S3ArchiveObjectMetadata,
        *,
        force_replay: bool = False,
    ) -> S3AuditIngestResult:
        """Download one S3 JSONL object, map canonical rows, dedupe, and batch-write."""

        key = object_metadata.key
        object_identity = ETLProcessedS3ObjectIdentity(
            bucket=self.s3_bucket,
            object_key=key,
            etag=object_metadata.etag,
        )
        source_row_count = 0
        attempted_row_count = 0
        accepted_row_count = 0
        duplicate_row_count = 0
        flush_count = 0
        try:
            existing_record = None
            if not force_replay:
                existing_record = self.processed_key_ledger.get_record(object_identity)
            if existing_record is not None and existing_record.status == "completed":
                logger.info(
                    "Skipped already-processed S3 archive key=%s etag=%s processed_at_ms=%s row_count=%s ledger_ttl_seconds=%s",
                    key,
                    existing_record.etag,
                    existing_record.processed_at_ms,
                    existing_record.row_count,
                    self.processed_key_ledger.ttl_s,
                )
                return S3AuditIngestResult(
                    key=key,
                    object_etag=object_metadata.etag,
                    source_row_count=0,
                    attempted_row_count=0,
                    accepted_row_count=0,
                    duplicate_row_count=0,
                    flush_count=0,
                    batch_size=self.writer.config.batch_size,
                    retry_max_attempts=self.retry_policy.max_attempts,
                    retry_backoff_ms=self.retry_policy.backoff_ms,
                    skipped_by_processed_ledger=True,
                )
            if force_replay:
                logger.info(
                    "Bypassing processed-key ledger for explicit replay key=%s etag=%s ledger_ttl_seconds=%s",
                    key,
                    object_metadata.etag,
                    self.processed_key_ledger.ttl_s,
                )

            response = self.s3.get_object(Bucket=self.s3_bucket, Key=key)
            raw_body = response["Body"].read()
            if isinstance(raw_body, bytes):
                lines = raw_body.decode("utf-8").splitlines()
            else:
                lines = str(raw_body).splitlines()

            dedup_keys: set[str] = set()
            batch = []
            for line_number, raw_line in enumerate(lines, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                source_row_count += 1
                payload = self._parse_json_line(stripped, key=key, line_number=line_number)
                row = map_canonical_audit_payload_to_clickhouse_row(payload)
                dedup_key = compute_clickhouse_raw_fact_dedup_key(row)
                if dedup_key in dedup_keys:
                    duplicate_row_count += 1
                    continue
                dedup_keys.add(dedup_key)
                batch.append(row)
                if len(batch) >= self.writer.config.batch_size:
                    attempted_row_count += len(batch)
                    flush_count += 1
                    accepted_row_count += self._flush_batch(
                        key=key,
                        rows=tuple(batch),
                        flush_index=flush_count,
                    )
                    batch.clear()

            if batch:
                attempted_row_count += len(batch)
                flush_count += 1
                accepted_row_count += self._flush_batch(
                    key=key,
                    rows=tuple(batch),
                    flush_index=flush_count,
                )

            self.processed_key_ledger.mark_completed(
                object_identity,
                row_count=accepted_row_count,
            )
            logger.info(
                "Ingested ClickHouse raw-fact archive key=%s etag=%s source_row_count=%s attempted_row_count=%s accepted_row_count=%s duplicate_row_count=%s flush_count=%s batch_size=%s retry_max_attempts=%s retry_backoff_ms=%s ledger_ttl_seconds=%s",
                key,
                object_metadata.etag,
                source_row_count,
                attempted_row_count,
                accepted_row_count,
                duplicate_row_count,
                flush_count,
                self.writer.config.batch_size,
                self.retry_policy.max_attempts,
                self.retry_policy.backoff_ms,
                self.processed_key_ledger.ttl_s,
            )
            return S3AuditIngestResult(
                key=key,
                object_etag=object_metadata.etag,
                source_row_count=source_row_count,
                attempted_row_count=attempted_row_count,
                accepted_row_count=accepted_row_count,
                duplicate_row_count=duplicate_row_count,
                flush_count=flush_count,
                batch_size=self.writer.config.batch_size,
                retry_max_attempts=self.retry_policy.max_attempts,
                retry_backoff_ms=self.retry_policy.backoff_ms,
                skipped_by_processed_ledger=False,
            )
        except Exception as exc:
            error_summary = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "Failed to ingest S3 archive key=%s etag=%s into ClickHouse source_row_count=%s attempted_row_count=%s duplicate_row_count=%s flush_count=%s batch_size=%s retry_max_attempts=%s retry_backoff_ms=%s ledger_ttl_seconds=%s force_replay=%s last_error=%s",
                key,
                object_metadata.etag,
                source_row_count,
                attempted_row_count,
                duplicate_row_count,
                flush_count,
                self.writer.config.batch_size,
                self.retry_policy.max_attempts,
                self.retry_policy.backoff_ms,
                self.processed_key_ledger.ttl_s,
                force_replay,
                error_summary,
            )
            raise ETLIngestError(
                "ClickHouse raw-fact ingest failed "
                f"for S3 key={key!r} "
                f"(source_row_count={source_row_count}, attempted_row_count={attempted_row_count}, "
                f"duplicate_row_count={duplicate_row_count}, flush_count={flush_count}, "
                f"batch_size={self.writer.config.batch_size}, retry_max_attempts={self.retry_policy.max_attempts}, "
                f"retry_backoff_ms={self.retry_policy.backoff_ms}, ledger_ttl_seconds={self.processed_key_ledger.ttl_s}, "
                f"force_replay={force_replay}, last_error={error_summary})."
            ) from exc

    def _flush_batch(
        self,
        *,
        key: str,
        rows: tuple[ClickHouseAuditEventInsertRow, ...],
        flush_index: int,
    ) -> int:
        result = self.writer.write_batch_request_with_retry(
            ClickHouseBatchWriteRequest(rows=rows),
            retry_policy=self.retry_policy,
        )
        logger.info(
            "Flushed ClickHouse raw-fact batch key=%s flush_index=%s table=%s attempted_row_count=%s accepted_row_count=%s batch_size=%s retry_max_attempts=%s retry_backoff_ms=%s",
            key,
            flush_index,
            result.table_name,
            result.attempted_row_count,
            result.accepted_row_count,
            self.writer.config.batch_size,
            self.retry_policy.max_attempts,
            self.retry_policy.backoff_ms,
        )
        return result.accepted_row_count

    @staticmethod
    def _is_ingest_candidate_key(key: str) -> bool:
        return key.endswith(".jsonl")

    @staticmethod
    def _normalize_s3_etag(raw_etag: object | None) -> str | None:
        if isinstance(raw_etag, bytes):
            raw_etag = raw_etag.decode("utf-8", errors="replace")
        if raw_etag is None:
            return None
        cleaned = str(raw_etag).strip()
        return cleaned or None

    @staticmethod
    def _parse_json_line(raw_line: str, *, key: str, line_number: int) -> dict[str, object]:
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ETLIngestError(
                f"invalid JSONL in S3 key={key!r} line={line_number}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ETLIngestError(
                f"invalid canonical audit row in S3 key={key!r} line={line_number}: JSON object required."
            )
        try:
            return {str(field_name): value for field_name, value in payload.items()}
        except Exception as exc:  # pragma: no cover - defensive, mapping keys should already be strings
            raise ETLIngestError(
                f"invalid canonical audit row in S3 key={key!r} line={line_number}: mapping conversion failed."
            ) from exc


def run_etl() -> None:
    """CLI entry point for the ClickHouse ETL worker."""

    try:
        validate_clickhouse_ingest_env_for_prod()
        config = load_etl_worker_config_from_env()
        _ensure_clickhouse_ingest_operational_config(config)
        worker = ETLWorker(config=config)
        total = worker.run_once()
    except ETLConfigurationError as exc:
        logger.error("ClickHouse ETL configuration invalid: %s", exc)
        raise SystemExit(str(exc)) from exc
    except CanonicalAuditMappingError as exc:
        logger.error("Canonical audit -> ClickHouse mapping failed: %s", exc)
        raise SystemExit(f"Canonical audit -> ClickHouse mapping failed: {exc}") from exc
    except ETLIngestError as exc:
        logger.error("ClickHouse ETL failed: %s", exc)
        raise SystemExit(str(exc)) from exc
    except StorageOperationalConfigError as exc:
        logger.error("ClickHouse ETL configuration invalid: %s", exc)
        raise SystemExit(str(exc)) from exc
    print(f"ClickHouse ETL completed. Accepted {total} rows.")


def run_etl_replay_keys(keys: list[str], *, force: bool = False) -> None:
    """Operational replay entry point for one explicit archive object list."""

    try:
        config = load_etl_worker_config_from_env()
        _ensure_clickhouse_ingest_operational_config(config)
        worker = ETLWorker(config=config)
        total = worker.replay_keys(keys, force=force)
    except ETLConfigurationError as exc:
        logger.error("ClickHouse ETL replay configuration invalid: %s", exc)
        raise SystemExit(str(exc)) from exc
    except CanonicalAuditMappingError as exc:
        logger.error("Canonical audit -> ClickHouse mapping failed: %s", exc)
        raise SystemExit(f"Canonical audit -> ClickHouse mapping failed: {exc}") from exc
    except ETLIngestError as exc:
        logger.error("ClickHouse ETL replay failed: %s", exc)
        raise SystemExit(str(exc)) from exc
    except StorageOperationalConfigError as exc:
        logger.error("ClickHouse ETL replay configuration invalid: %s", exc)
        raise SystemExit(str(exc)) from exc
    print(f"ClickHouse ETL replay completed. Accepted {total} rows.")


if __name__ == "__main__":
    run_etl()
