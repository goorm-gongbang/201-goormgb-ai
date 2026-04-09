from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass

from .keyspace import ETL_PROCESSED_KEY_PREFIX
from .redis_client import RedisLike


@dataclass(slots=True, frozen=True)
class ETLProcessedS3ObjectIdentity:
    bucket: str
    object_key: str
    etag: str | None = None

    @property
    def canonical_identity(self) -> str:
        return f"{self.bucket}\n{self.object_key}\n{self.normalized_etag}"

    @property
    def normalized_etag(self) -> str:
        cleaned = (self.etag or "").strip()
        return cleaned if cleaned else "-"


@dataclass(slots=True, frozen=True)
class ETLProcessedS3ObjectRecord:
    status: str
    bucket: str
    object_key: str
    etag: str | None
    processed_at_ms: int
    row_count: int

    def to_json(self) -> str:
        return json.dumps(
            {
                "status": self.status,
                "bucket": self.bucket,
                "object_key": self.object_key,
                "etag": self.etag,
                "processed_at_ms": self.processed_at_ms,
                "row_count": self.row_count,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str) -> ETLProcessedS3ObjectRecord | None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        try:
            status = str(payload["status"])
            bucket = str(payload["bucket"])
            object_key = str(payload["object_key"])
            etag = payload.get("etag")
            processed_at_ms = int(payload["processed_at_ms"])
            row_count = int(payload["row_count"])
        except (KeyError, TypeError, ValueError):
            return None
        if etag is not None:
            etag = str(etag)
        return cls(
            status=status,
            bucket=bucket,
            object_key=object_key,
            etag=etag,
            processed_at_ms=processed_at_ms,
            row_count=row_count,
        )


def build_etl_processed_s3_object_ledger_key(
    identity: ETLProcessedS3ObjectIdentity,
    *,
    key_prefix: str = ETL_PROCESSED_KEY_PREFIX,
) -> str:
    digest = hashlib.sha256(identity.canonical_identity.encode("utf-8")).hexdigest()
    return f"{key_prefix}{identity.bucket}:{digest}"


class ETLProcessedS3ObjectLedger:
    def __init__(
        self,
        redis: RedisLike,
        *,
        ttl_s: int,
        key_prefix: str = ETL_PROCESSED_KEY_PREFIX,
    ) -> None:
        if ttl_s <= 0:
            raise ValueError("ttl_s must be > 0.")
        self._redis = redis
        self._ttl_s = ttl_s
        self._key_prefix = key_prefix

    @property
    def ttl_s(self) -> int:
        return self._ttl_s

    def key_for_object(self, identity: ETLProcessedS3ObjectIdentity) -> str:
        return build_etl_processed_s3_object_ledger_key(
            identity,
            key_prefix=self._key_prefix,
        )

    def get_record(
        self,
        identity: ETLProcessedS3ObjectIdentity,
    ) -> ETLProcessedS3ObjectRecord | None:
        raw = self._redis.get(self.key_for_object(identity))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return ETLProcessedS3ObjectRecord.from_json(str(raw))

    def is_processed(self, identity: ETLProcessedS3ObjectIdentity) -> bool:
        record = self.get_record(identity)
        return record is not None and record.status == "completed"

    def mark_completed(
        self,
        identity: ETLProcessedS3ObjectIdentity,
        *,
        row_count: int,
        processed_at_ms: int | None = None,
    ) -> ETLProcessedS3ObjectRecord:
        record = ETLProcessedS3ObjectRecord(
            status="completed",
            bucket=identity.bucket,
            object_key=identity.object_key,
            etag=identity.etag,
            processed_at_ms=int(time.time() * 1000) if processed_at_ms is None else processed_at_ms,
            row_count=row_count,
        )
        written = self._redis.set(
            self.key_for_object(identity),
            record.to_json(),
            ex=self._ttl_s,
        )
        if not written:
            raise RuntimeError("processed-key ledger write was not acknowledged.")
        return record
