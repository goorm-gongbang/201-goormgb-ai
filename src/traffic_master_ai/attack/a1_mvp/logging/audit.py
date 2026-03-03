"""Decision audit logger (JSONL).

This is intentionally simple for MVP: append-only JSONL with flush on write.
Files under logs/ are gitignored by default in this repo.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any, Mapping


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True, slots=True)
class AuditEntry:
    ts_ms: int
    session_id: str
    flow_state: str
    event: str
    action: str
    payload: dict[str, Any]


class DecisionAuditLogger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._fp = path.open("a", encoding="utf-8")

    @property
    def path(self) -> Path:
        return self._path

    def log(self, record: Mapping[str, Any]) -> None:
        self._fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()

    def __enter__(self) -> "DecisionAuditLogger":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

