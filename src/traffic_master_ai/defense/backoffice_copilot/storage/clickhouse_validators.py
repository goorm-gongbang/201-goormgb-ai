"""Column-level validators for ClickHouse raw-fact writes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from .validators import StorageValidationError


@dataclass(slots=True, frozen=True)
class ClickHouseAuditEventInsertRow:
    """Sanitized insert DTO for `defense_audit_events`.

    This DTO matches Task 2 / Task 8 minimum DDL only.
    Richer typed fields remain explicit gaps for later tasks.
    """

    ts_ms: int
    session_id: str
    event_type: str
    trace_id: str | None = None
    challenge_id: str | None = None
    flow_state: str | None = None
    risk_tier: str | None = None
    action: str | None = None
    reason_code: str | None = None
    policy_version: str | None = None
    raw_payload_json: str = "{}"


def validate_clickhouse_audit_event_insert_row(
    row: ClickHouseAuditEventInsertRow,
) -> ClickHouseAuditEventInsertRow:
    """Validate one raw-fact insert DTO against the fixed minimum contract."""

    if not isinstance(row.ts_ms, int) or isinstance(row.ts_ms, bool) or row.ts_ms < 0:
        raise StorageValidationError("ts_ms must be a non-negative int.")
    _ensure_required_text(row.session_id, "session_id")
    _ensure_required_text(row.event_type, "event_type")

    for field_name in (
        "trace_id",
        "challenge_id",
        "flow_state",
        "risk_tier",
        "action",
        "reason_code",
        "policy_version",
    ):
        _ensure_nullable_text(getattr(row, field_name), field_name)

    _ensure_json_object_text(row.raw_payload_json, "raw_payload_json")
    return row


def serialize_clickhouse_audit_event_insert_row(
    row: ClickHouseAuditEventInsertRow,
) -> dict[str, object]:
    """Validate and convert one insert DTO into ClickHouse parameter payload."""

    validate_clickhouse_audit_event_insert_row(row)
    return {
        "ts_ms": row.ts_ms,
        "session_id": row.session_id,
        "event_type": row.event_type,
        "trace_id": row.trace_id,
        "challenge_id": row.challenge_id,
        "flow_state": row.flow_state,
        "risk_tier": row.risk_tier,
        "action": row.action,
        "reason_code": row.reason_code,
        "policy_version": row.policy_version,
        "raw_payload_json": row.raw_payload_json,
    }


def serialize_clickhouse_audit_event_insert_rows(
    rows: Sequence[ClickHouseAuditEventInsertRow],
) -> list[dict[str, object]]:
    """Validate and convert one batch of sanitized raw-fact rows."""

    return [serialize_clickhouse_audit_event_insert_row(row) for row in rows]


def _ensure_required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise StorageValidationError(f"{field_name} must be a non-empty string.")
    return value


def _ensure_nullable_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise StorageValidationError(f"{field_name} must be a non-empty string or None.")
    return value


def _ensure_json_object_text(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, str) or not value:
        raise StorageValidationError(f"{field_name} must be a non-empty JSON string.")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise StorageValidationError(f"{field_name} must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise StorageValidationError(f"{field_name} must encode a JSON object.")
    return parsed

