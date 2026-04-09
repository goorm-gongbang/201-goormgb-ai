"""Write-only ClickHouse raw-fact repository skeleton for Backoffice Copilot."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Protocol, Sequence

from .clickhouse_connection import (
    DEFAULT_CLICKHOUSE_AUDIT_TABLE,
    ClickHouseBatchWriteClient,
    ClickHouseWriteConfig,
)
from .clickhouse_validators import (
    ClickHouseAuditEventInsertRow,
    serialize_clickhouse_audit_event_insert_rows,
)

logger = logging.getLogger(__name__)

_RAW_FACT_INSERT_COLUMNS = (
    "ts_ms",
    "session_id",
    "event_type",
    "trace_id",
    "challenge_id",
    "flow_state",
    "risk_tier",
    "action",
    "reason_code",
    "policy_version",
    "raw_payload_json",
)


class ClickHouseBatchWriteError(RuntimeError):
    """Raised when one ClickHouse raw-fact batch cannot be persisted."""

    def __init__(
        self,
        *,
        table_name: str,
        attempted_row_count: int,
        max_attempts: int,
        backoff_ms: int,
        last_error_message: str | None,
    ) -> None:
        self.table_name = table_name
        self.attempted_row_count = attempted_row_count
        self.max_attempts = max_attempts
        self.backoff_ms = backoff_ms
        self.last_error_message = last_error_message
        self.replay_hint = (
            "Keep the source batch as replay input and retry raw-fact ingest from the "
            "serialized batch or upstream S3 archive."
        )
        failure_suffix = (
            f" last_error={last_error_message}." if last_error_message else ""
        )
        super().__init__(
            "ClickHouse raw-fact write failed "
            f"(table={table_name}, attempted_row_count={attempted_row_count}, "
            f"max_attempts={max_attempts}, backoff_ms={backoff_ms})."
            f"{failure_suffix} "
            f"{self.replay_hint}"
        )


@dataclass(slots=True, frozen=True)
class ClickHouseBatchWriteRetryPolicy:
    """Minimal retry surface for one raw-fact batch write."""

    max_attempts: int = 1
    backoff_ms: int = 0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1.")
        if self.backoff_ms < 0:
            raise ValueError("backoff_ms must be >= 0.")


class ClickHouseAuditEventWriteRepository(Protocol):
    """Write-focused repository contract for Task 9 raw-fact persistence."""

    def write_batch(
        self,
        rows: Sequence[ClickHouseAuditEventInsertRow],
    ) -> int:
        """Persist one sanitized raw-fact batch."""


@dataclass(slots=True, frozen=True)
class ClickHouseBatchWriteRequest:
    """Explicit batch entrypoint DTO for ETL/collector integration."""

    rows: tuple[ClickHouseAuditEventInsertRow, ...]


@dataclass(slots=True, frozen=True)
class ClickHouseBatchWriteResult:
    """Minimal write result surface for the raw-fact writer skeleton."""

    table_name: str
    attempted_row_count: int
    accepted_row_count: int


@dataclass(slots=True)
class ClickHouseAuditEventWriterRepository:
    """Thin raw-fact writer that only knows the ClickHouse insert contract.

    Gaps intentionally left for later tasks:
    - real network client construction and retry policy
    - async insert settings / dedup strategy
    - canonical audit shaping and privacy sanitation
    - rollup or candidate-layer orchestration
    """

    client: ClickHouseBatchWriteClient
    config: ClickHouseWriteConfig = field(default_factory=ClickHouseWriteConfig)

    def write_batch(
        self,
        rows: Sequence[ClickHouseAuditEventInsertRow],
    ) -> int:
        """Persist one sanitized raw-fact batch and return accepted row count."""

        request = ClickHouseBatchWriteRequest(rows=tuple(rows))
        return self.write_batch_request(request).accepted_row_count

    def write_batch_request(
        self,
        request: ClickHouseBatchWriteRequest,
    ) -> ClickHouseBatchWriteResult:
        """Persist one explicit batch request for future ETL/collector callers."""

        return self.write_batch_request_with_retry(
            request,
            retry_policy=ClickHouseBatchWriteRetryPolicy(),
        )

    def write_batch_request_with_retry(
        self,
        request: ClickHouseBatchWriteRequest,
        *,
        retry_policy: ClickHouseBatchWriteRetryPolicy,
    ) -> ClickHouseBatchWriteResult:
        """Persist one batch request with minimal retry and explicit replay surfacing."""

        if not request.rows:
            return ClickHouseBatchWriteResult(
                table_name=self.config.table_name,
                attempted_row_count=0,
                accepted_row_count=0,
            )

        payload = serialize_clickhouse_audit_event_insert_rows(request.rows)
        last_error_message: str | None = None
        for attempt in range(1, retry_policy.max_attempts + 1):
            try:
                self.client.execute(self.insert_sql, payload)
                return ClickHouseBatchWriteResult(
                    table_name=self.config.table_name,
                    attempted_row_count=len(request.rows),
                    accepted_row_count=len(payload),
                )
            except Exception as exc:
                last_error_message = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    "ClickHouse raw-fact write failed for table=%s attempt=%s/%s row_count=%s backoff_ms=%s last_error=%s",
                    self.config.table_name,
                    attempt,
                    retry_policy.max_attempts,
                    len(payload),
                    retry_policy.backoff_ms,
                    last_error_message,
                )
                if attempt < retry_policy.max_attempts and retry_policy.backoff_ms > 0:
                    time.sleep(retry_policy.backoff_ms / 1000.0)

        raise ClickHouseBatchWriteError(
            table_name=self.config.table_name,
            attempted_row_count=len(request.rows),
            max_attempts=retry_policy.max_attempts,
            backoff_ms=retry_policy.backoff_ms,
            last_error_message=last_error_message,
        )

    @property
    def insert_sql(self) -> str:
        columns = ", ".join(_RAW_FACT_INSERT_COLUMNS)
        return f"INSERT INTO {self.config.table_name} ({columns}) VALUES"


def build_clickhouse_audit_event_writer_repository(
    client: ClickHouseBatchWriteClient,
    *,
    table_name: str = DEFAULT_CLICKHOUSE_AUDIT_TABLE,
) -> ClickHouseAuditEventWriterRepository:
    """Build the raw-fact writer skeleton with explicit client injection."""

    return ClickHouseAuditEventWriterRepository(
        client=client,
        config=ClickHouseWriteConfig(table_name=table_name),
    )
