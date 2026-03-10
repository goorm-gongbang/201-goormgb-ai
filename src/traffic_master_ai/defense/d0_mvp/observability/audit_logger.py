"""JSONL append-only audit logger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from ..core.constants import AUDIT_FILENAME, AUDIT_RETENTION_DAYS
from .jsonl_retention import is_within_retention, load_rows, persist_rows
from .schemas import AuditEntry, MANDATORY_AUDIT_EVENT_TYPES


class AuditLogger:
    """Append-only decision_audit logger with schema validation."""

    def __init__(
        self,
        file_path: str = AUDIT_FILENAME,
        *,
        retention_days: int = AUDIT_RETENTION_DAYS,
    ) -> None:
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._retention_days = max(0, int(retention_days))

    @property
    def file_path(self) -> Path:
        return self._path

    @property
    def retention_days(self) -> int:
        return self._retention_days

    def append(self, entry: AuditEntry | Mapping[str, Any]) -> bool:
        """Append one validated entry to JSONL file."""
        item = entry if isinstance(entry, AuditEntry) else AuditEntry.from_dict(entry)
        errors = item.validate()
        if errors:
            raise ValueError("invalid audit entry: " + "; ".join(errors))

        payload = item.to_dict()
        self._prune_expired()
        if not is_within_retention(payload, retention_days=self._retention_days):
            return False

        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        return True

    def read_all(self) -> list[dict[str, Any]]:
        """Read all JSONL entries."""
        rows, pruned = load_rows(self._path, retention_days=self._retention_days)
        if pruned:
            persist_rows(self._path, rows)
        return rows

    def missing_mandatory_events(
        self,
        entries: Optional[Iterable[Mapping[str, Any]]] = None,
    ) -> list[str]:
        """Return missing mandatory event types defined in L2 observability spec."""
        if entries is None:
            source = self.read_all()
        else:
            source = list(entries)

        seen = {str(item.get("eventType", "")) for item in source}
        missing = sorted(ev for ev in MANDATORY_AUDIT_EVENT_TYPES if ev not in seen)
        return missing

    def _prune_expired(self) -> None:
        rows, pruned = load_rows(self._path, retention_days=self._retention_days)
        if pruned:
            persist_rows(self._path, rows)


__all__ = ["AuditLogger"]
