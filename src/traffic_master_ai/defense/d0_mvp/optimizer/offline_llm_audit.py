"""Append-only offline LLM audit helpers."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from ..core.constants import OFFLINE_OPT_AUDIT_FILENAME


class OfflineLLMAuditLogger:
    """Shared JSONL logger for offline LLM activity."""

    def __init__(self, file_path: str = OFFLINE_OPT_AUDIT_FILENAME) -> None:
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, payload: Mapping[str, Any]) -> None:
        row = {
            "tsMs": int(time.time() * 1000),
            "eventType": event_type,
            **dict(payload),
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


_DEFAULT_LOGGER = OfflineLLMAuditLogger()


def append_offline_llm_audit(event_type: str, payload: Mapping[str, Any]) -> None:
    _DEFAULT_LOGGER.append(event_type, payload)


__all__ = ["OfflineLLMAuditLogger", "append_offline_llm_audit"]
