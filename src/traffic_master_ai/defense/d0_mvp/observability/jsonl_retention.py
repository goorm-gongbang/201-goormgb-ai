"""Helpers for enforcing JSONL retention in local observability stores."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_RETENTION_EPOCH_FLOOR_MS = 946684800000  # 2000-01-01T00:00:00Z


def retention_cutoff_ms(retention_days: int) -> int | None:
    if retention_days <= 0:
        return None
    return int(time.time() * 1000) - (retention_days * 24 * 60 * 60 * 1000)


def load_rows(path: Path, *, retention_days: int) -> tuple[list[dict[str, Any]], bool]:
    if not path.exists():
        return [], False

    cutoff_ms = retention_cutoff_ms(retention_days)
    rows: list[dict[str, Any]] = []
    pruned = False
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            ts_ms = _safe_ts_ms(parsed.get("tsMs"))
            if (
                cutoff_ms is not None
                and ts_ms is not None
                and ts_ms >= _RETENTION_EPOCH_FLOOR_MS
                and ts_ms < cutoff_ms
            ):
                pruned = True
                continue
            rows.append(parsed)
    return rows, pruned


def persist_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def is_within_retention(entry: dict[str, Any], *, retention_days: int) -> bool:
    cutoff_ms = retention_cutoff_ms(retention_days)
    if cutoff_ms is None:
        return True
    ts_ms = _safe_ts_ms(entry.get("tsMs"))
    if ts_ms is None:
        return True
    if ts_ms < _RETENTION_EPOCH_FLOOR_MS:
        return True
    return ts_ms >= cutoff_ms


def _safe_ts_ms(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["is_within_retention", "load_rows", "persist_rows", "retention_cutoff_ms"]
