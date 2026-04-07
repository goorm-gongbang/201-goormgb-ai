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
from ..storage_env import (
    ETLWorkerConfig,
    load_etl_worker_config_from_env,
    StorageOperationalConfigError,
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
    accepted_row_count: int
    duplicate_row_count: int


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
        for key in self._iter_source_keys():
            result = self._process_s3_file(key)
            total_rows += result.accepted_row_count
        return total_rows

    def replay_key(self, key: str) -> S3AuditIngestResult:
        """Replay one explicit archive object into ClickHouse."""

        if not key or not self._is_ingest_candidate_key(key):
            raise ETLIngestError("replay key must be one .jsonl archive object.")
        return self._process_s3_file(key)

    def replay_keys(self, keys: list[str]) -> int:
        """Replay a fixed archive object list in order."""

        total_rows = 0
        for key in keys:
            result = self.replay_key(key)
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

    def _iter_source_keys(self) -> list[str]:
        keys: list[str] = []
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
                    keys.append(key)

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                break
        return keys

    def _process_s3_file(self, key: str) -> S3AuditIngestResult:
        """Download one S3 JSONL object, map canonical rows, dedupe, and batch-write."""

        try:
            response = self.s3.get_object(Bucket=self.s3_bucket, Key=key)
            raw_body = response["Body"].read()
            if isinstance(raw_body, bytes):
                lines = raw_body.decode("utf-8").splitlines()
            else:
                lines = str(raw_body).splitlines()

            accepted_row_count = 0
            duplicate_row_count = 0
            dedup_keys: set[str] = set()
            batch = []
            for line_number, raw_line in enumerate(lines, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                payload = self._parse_json_line(stripped, key=key, line_number=line_number)
                row = map_canonical_audit_payload_to_clickhouse_row(payload)
                dedup_key = compute_clickhouse_raw_fact_dedup_key(row)
                if dedup_key in dedup_keys:
                    duplicate_row_count += 1
                    continue
                dedup_keys.add(dedup_key)
                batch.append(row)
                if len(batch) >= self.writer.config.batch_size:
                    accepted_row_count += self._flush_batch(key=key, rows=tuple(batch))
                    batch.clear()

            if batch:
                accepted_row_count += self._flush_batch(key=key, rows=tuple(batch))

            logger.info(
                "Ingested ClickHouse raw-fact archive key=%s accepted_row_count=%s duplicate_row_count=%s",
                key,
                accepted_row_count,
                duplicate_row_count,
            )
            return S3AuditIngestResult(
                key=key,
                accepted_row_count=accepted_row_count,
                duplicate_row_count=duplicate_row_count,
            )
        except Exception as exc:
            logger.exception("Failed to ingest S3 archive key=%s into ClickHouse", key)
            raise ETLIngestError(
                f"ClickHouse raw-fact ingest failed for S3 key={key!r}."
            ) from exc

    def _flush_batch(self, *, key: str, rows: tuple[ClickHouseAuditEventInsertRow, ...]) -> int:
        result = self.writer.write_batch_request_with_retry(
            ClickHouseBatchWriteRequest(rows=rows),
            retry_policy=self.retry_policy,
        )
        logger.info(
            "Flushed ClickHouse raw-fact batch key=%s table=%s accepted_row_count=%s",
            key,
            result.table_name,
            result.accepted_row_count,
        )
        return result.accepted_row_count

    @staticmethod
    def _is_ingest_candidate_key(key: str) -> bool:
        return key.endswith(".jsonl")

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


def run_etl_replay_keys(keys: list[str]) -> None:
    """Operational replay entry point for one explicit archive object list."""

    try:
        config = load_etl_worker_config_from_env()
        _ensure_clickhouse_ingest_operational_config(config)
        worker = ETLWorker(config=config)
        total = worker.replay_keys(keys)
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
