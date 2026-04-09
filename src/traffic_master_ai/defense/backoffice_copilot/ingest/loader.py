"""Raw defense_audit_events loader for Backoffice Copilot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ...audit_contract import normalize_audit_row
from ..core.models import DefenseAuditEventRow
from ..core.state import AnalysisInput, PostReviewRunInput

_ROW_ID_KEYS: frozenset[str] = frozenset(
    {
        "ts_ms",
        "tsMs",
        "trace_id",
        "traceId",
        "session_id",
        "sessionId",
        "event_type",
        "eventType",
    }
)


def load_analysis_input(
    jsonl_path: str | Path,
    *,
    run_input: PostReviewRunInput,
) -> AnalysisInput:
    """Load raw rows into the minimal Task 3 analysis input bundle."""

    return AnalysisInput(
        defense_audit_events=load_defense_audit_events(
            jsonl_path,
            window_start_ms=run_input.window_start_ms,
            window_end_ms=run_input.window_end_ms,
            limit=run_input.limit,
        ),
        raw_audit_available=run_input.use_raw_audit_fallback,
    )


def load_defense_audit_events(
    jsonl_path: str | Path,
    *,
    window_start_ms: int,
    window_end_ms: int,
    limit: int,
) -> tuple[DefenseAuditEventRow, ...]:
    """Load raw rows with a deterministic time-window filter and limit."""

    if limit < 0:
        raise ValueError("limit must be non-negative")
    if window_start_ms > window_end_ms:
        raise ValueError("window_start_ms must be <= window_end_ms")
    if limit == 0:
        return ()

    rows: list[DefenseAuditEventRow] = []
    path = Path(jsonl_path)
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
            row = parse_defense_audit_event_row(payload)
            if row.ts_ms < window_start_ms or row.ts_ms > window_end_ms:
                continue
            rows.append(row)
            # Apply limit after the time-window filter while preserving source order.
            if len(rows) >= limit:
                break
    return tuple(rows)


def parse_defense_audit_event_row(data: Mapping[str, Any]) -> DefenseAuditEventRow:
    """Parse a minimal raw row without semantic interpretation."""

    payload = _extract_payload(data)
    return DefenseAuditEventRow(
        ts_ms=_require_int(data, "ts_ms", "tsMs"),
        trace_id=(
            _optional_str(data, "trace_id", "traceId")
            or _optional_str(data, "request_id", "requestId")
            or _require_str(data, "session_id", "sessionId")
        ),
        session_id=_require_str(data, "session_id", "sessionId"),
        event_type=_require_str(data, "event_type", "eventType"),
        payload=payload,
    )


def parse_canonical_defense_audit_event_row(
    data: Mapping[str, Any],
) -> DefenseAuditEventRow:
    row = normalize_audit_row(data, allow_legacy=False)
    trace_id = row.get("trace_id") or row.get("request_id") or row["session_id"]
    return DefenseAuditEventRow(
        ts_ms=row["ts_ms"],
        trace_id=trace_id,
        session_id=row["session_id"],
        event_type=row["event_type"],
        payload=dict(row["raw_payload"]),
    )


def _extract_payload(data: Mapping[str, Any]) -> dict[str, object]:
    merged_payload: dict[str, object] = {}

    embedded_raw_payload = data.get("raw_payload")
    if embedded_raw_payload is not None:
        if not isinstance(embedded_raw_payload, Mapping):
            raise TypeError("raw_payload must be an object when present")
        merged_payload.update({str(key): value for key, value in embedded_raw_payload.items()})

    embedded_payload = data.get("payload")
    if embedded_payload is not None:
        if not isinstance(embedded_payload, Mapping):
            raise TypeError("payload must be an object when present")
        merged_payload.update({str(key): value for key, value in embedded_payload.items()})

    for key, value in data.items():
        if key in _ROW_ID_KEYS or key in {"payload", "raw_payload"}:
            continue
        merged_payload[str(key)] = value
    return merged_payload


def _require_int(data: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            break
        return value
    raise TypeError(f"expected integer field, checked keys={keys!r}")


def _require_str(data: Mapping[str, Any], *keys: str) -> str:
    value = _optional_str(data, *keys)
    if value is not None:
        return value
    raise TypeError(f"expected non-empty string field, checked keys={keys!r}")


def _optional_str(data: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            break
        return value
    return None


__all__ = [
    "load_analysis_input",
    "load_defense_audit_events",
    "parse_canonical_defense_audit_event_row",
    "parse_defense_audit_event_row",
]
