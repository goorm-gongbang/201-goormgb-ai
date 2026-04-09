"""Legacy local warehouse for near-real-time defense audit queries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from ...audit_contract import build_warehouse_audit_row, normalize_audit_row
from ...storage_env import load_warehouse_file_config_from_env
from ..core.constants import AUDIT_RETENTION_DAYS, WAREHOUSE_FILENAME
from .jsonl_retention import is_within_retention, load_rows, persist_rows
from .schemas import AuditEntry


class AuditWarehouse:
    """Append-only local warehouse of normalized audit events.

    Legacy local-only implementation of the L2 warehouse contract using JSONL rows.
    Production raw-fact ingest authority now lives in ClickHouse ETL, not this file.
    """

    def __init__(
        self,
        file_path: str = WAREHOUSE_FILENAME,
        *,
        retention_days: int = AUDIT_RETENTION_DAYS,
    ) -> None:
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._retention_days = max(0, int(retention_days))

    @classmethod
    def from_env(cls) -> AuditWarehouse:
        """Build the local JSONL warehouse using the current MVP file-path env."""

        return cls(file_path=load_warehouse_file_config_from_env().file_path)

    @property
    def file_path(self) -> Path:
        return self._path

    @property
    def retention_days(self) -> int:
        return self._retention_days

    def metadata(self) -> dict[str, Any]:
        return {
            "backend": "legacy_jsonl_local_only",
            "table": "defense_audit_events",
            "filePath": str(self._path),
            "primaryOptions": ["ClickHouse"],
            "indices": ["traceId", "sessionId", "eventType", "tsMs"],
            "partitioning": "by day(tsMs)",
            "retentionDays": self._retention_days,
        }

    def append(self, entry: AuditEntry | Mapping[str, Any]) -> bool:
        item = entry if isinstance(entry, AuditEntry) else AuditEntry.from_dict(entry)
        errors = item.validate()
        if errors:
            raise ValueError("invalid warehouse entry: " + "; ".join(errors))

        row = build_warehouse_audit_row(item.to_dict())
        self._prune_expired()
        if not is_within_retention(row, retention_days=self._retention_days):
            return False
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        return True

    def append_many(self, entries: Iterable[AuditEntry | Mapping[str, Any]]) -> int:
        count = 0
        for entry in entries:
            if self.append(entry):
                count += 1
        return count

    def clear(self) -> None:
        """Remove all stored warehouse rows."""
        self._path.write_text("", encoding="utf-8")

    def read_all(self) -> list[dict[str, Any]]:
        rows, pruned = load_rows(self._path, retention_days=self._retention_days)
        if pruned:
            persist_rows(self._path, rows)
        return rows

    def query(
        self,
        *,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        rows = self.read_all()
        out: list[dict[str, Any]] = []
        for row in rows:
            normalized = normalize_audit_row(row)
            if session_id is not None and normalized.get("session_id") != session_id:
                continue
            if trace_id is not None and normalized.get("trace_id") != trace_id:
                continue
            if event_type is not None and normalized.get("event_type") != event_type:
                continue
            out.append(row)
        out.sort(key=lambda row: int(normalize_audit_row(row).get("ts_ms", 0)), reverse=True)
        if limit is not None and limit >= 0:
            return out[:limit]
        return out

    def _prune_expired(self) -> None:
        rows, pruned = load_rows(self._path, retention_days=self._retention_days)
        if pruned:
            persist_rows(self._path, rows)

__all__ = ["AuditWarehouse"]
