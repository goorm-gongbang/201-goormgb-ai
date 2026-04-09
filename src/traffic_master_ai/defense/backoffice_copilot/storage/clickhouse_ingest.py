"""Canonical audit -> ClickHouse raw-fact mapping helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from ...audit_contract import normalize_audit_row
from .clickhouse_validators import ClickHouseAuditEventInsertRow


class CanonicalAuditMappingError(ValueError):
    """Raised when one canonical audit payload cannot be mapped to the raw-fact contract."""


def map_canonical_audit_payload_to_clickhouse_row(
    payload: Mapping[str, Any],
) -> ClickHouseAuditEventInsertRow:
    try:
        row = normalize_audit_row(payload, allow_legacy=False)
    except ValueError as exc:
        raise CanonicalAuditMappingError(str(exc)) from exc

    return ClickHouseAuditEventInsertRow(
        ts_ms=_require_non_negative_int(row.get("ts_ms"), field_name="ts_ms"),
        session_id=_require_non_empty_text(row.get("session_id"), field_name="session_id"),
        event_type=_require_non_empty_text(row.get("event_type"), field_name="event_type"),
        trace_id=_optional_text(row.get("trace_id")),
        challenge_id=_optional_text(row.get("challenge_id")),
        flow_state=_optional_text(row.get("flow_state")),
        risk_tier=_optional_text(row.get("risk_tier")),
        action=_optional_text(row.get("action")),
        reason_code=_optional_text(row.get("reason_code")),
        policy_version=_optional_text(row.get("policy_version")),
        raw_payload_json=_serialize_raw_payload_json(row.get("raw_payload")),
    )


def compute_clickhouse_raw_fact_dedup_key(row: ClickHouseAuditEventInsertRow) -> str:
    """Compute a stable per-row ingest dedup key.

    This is intentionally a minimum local replay guard only. It prevents duplicate
    inserts inside one ETL run or one replay batch. Cross-run exactly-once delivery
    remains an explicit operations gap.
    """

    fingerprint = {
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
    encoded = json.dumps(fingerprint, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _serialize_raw_payload_json(payload: object) -> str:
    if not isinstance(payload, Mapping):
        raise CanonicalAuditMappingError("raw_payload must be an object.")
    return json.dumps(
        {str(key): value for key, value in payload.items()},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _require_non_negative_int(value: object, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CanonicalAuditMappingError(f"{field_name} must be a non-negative int.")
    return value


def _require_non_empty_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise CanonicalAuditMappingError(f"{field_name} must be a non-empty string.")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise CanonicalAuditMappingError("optional typed raw-fact fields must be non-empty strings.")
    return value


__all__ = [
    "CanonicalAuditMappingError",
    "compute_clickhouse_raw_fact_dedup_key",
    "map_canonical_audit_payload_to_clickhouse_row",
]
