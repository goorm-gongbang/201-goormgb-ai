"""Collector that ingests decision_audit into the local warehouse."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping, Optional

from ..core.constants import AUDIT_COLLECTOR_CHECKPOINT_FILENAME
from .audit_logger import AuditLogger
from .schemas import AuditEntry
from .warehouse import AuditWarehouse


class AuditCollector:
    """decision_audit -> warehouse collector with backfill support."""

    def __init__(
        self,
        *,
        audit_logger: AuditLogger,
        warehouse: AuditWarehouse,
        checkpoint_file: str = AUDIT_COLLECTOR_CHECKPOINT_FILENAME,
    ) -> None:
        self._audit_logger = audit_logger
        self._warehouse = warehouse
        self._checkpoint_path = Path(checkpoint_file)
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._rows_ingested_total = 0
        self._last_ingested_ts_ms: Optional[int] = None
        self._last_ingest_lag_ms: Optional[int] = None
        self._last_sync_started_ms: Optional[int] = None
        self._last_sync_finished_ms: Optional[int] = None

    @property
    def warehouse(self) -> AuditWarehouse:
        return self._warehouse

    def ingest_entry(self, entry: AuditEntry | Mapping[str, Any]) -> None:
        payload = entry.to_dict() if isinstance(entry, AuditEntry) else dict(entry)
        appended = self._warehouse.append(payload)
        if not appended:
            return
        self._rows_ingested_total += 1
        ts_ms = _safe_int(payload.get("tsMs"))
        if ts_ms is not None:
            self._last_ingested_ts_ms = ts_ms
            self._last_ingest_lag_ms = max(0, int(time.time() * 1000) - ts_ms)

    def sync(self) -> int:
        """Replay newly appended decision_audit rows into the warehouse."""
        self._last_sync_started_ms = int(time.time() * 1000)
        start_index = self._read_checkpoint()
        entries = self._audit_logger.read_all()
        existing_keys = {_entry_identity(row) for row in self._warehouse.read_all()}
        if start_index >= len(entries):
            self._last_sync_finished_ms = int(time.time() * 1000)
            return 0
        count = 0
        for entry in entries[start_index:]:
            identity = _entry_identity(entry)
            if identity in existing_keys:
                continue
            self.ingest_entry(entry)
            existing_keys.add(identity)
            count += 1
        self._write_checkpoint(len(entries))
        self._last_sync_finished_ms = int(time.time() * 1000)
        return count

    def backfill(self) -> int:
        """Replay all decision_audit rows from scratch."""
        self._warehouse.clear()
        self._write_checkpoint(0)
        return self.sync()

    def status(self) -> dict[str, Any]:
        return {
            "mode": "jsonl_tail_and_inline_ingest",
            "checkpointFile": str(self._checkpoint_path),
            "rowsIngestedTotal": self._rows_ingested_total,
            "lastIngestedTsMs": self._last_ingested_ts_ms,
            "lastIngestLagMs": self._last_ingest_lag_ms,
            "lastSyncStartedMs": self._last_sync_started_ms,
            "lastSyncFinishedMs": self._last_sync_finished_ms,
            "goalLatencySeconds": {"p50": 5, "p90": 15},
            "retentionDays": self._warehouse.retention_days,
        }

    def _read_checkpoint(self) -> int:
        if not self._checkpoint_path.exists():
            return 0
        try:
            raw = self._checkpoint_path.read_text(encoding="utf-8").strip()
            return max(0, int(raw or "0"))
        except (OSError, ValueError):
            return 0

    def _write_checkpoint(self, value: int) -> None:
        self._checkpoint_path.write_text(str(max(0, value)), encoding="utf-8")


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _entry_identity(entry: Mapping[str, Any]) -> tuple[str, str, str, str, int]:
    return (
        str(entry.get("requestId", "")),
        str(entry.get("eventType", "")),
        str(entry.get("traceId", "")),
        str(entry.get("sessionId", "")),
        _safe_int(entry.get("tsMs")) or 0,
    )


__all__ = ["AuditCollector"]
