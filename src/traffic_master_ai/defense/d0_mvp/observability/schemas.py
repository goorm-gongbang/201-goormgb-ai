"""Observability schemas for decision_audit JSONL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ...audit_contract import build_canonical_audit_row, normalize_audit_row, validate_canonical_audit_row
from ..events.catalog import AUDIT_EVENT_TYPES

LEGACY_API_AUDIT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "EVALUATE",
        "CHALLENGE_ISSUED",
        "CHALLENGE_VERIFIED",
    }
)

RUNTIME_AUDIT_EVENT_TYPES: frozenset[str] = AUDIT_EVENT_TYPES
CANONICAL_AUDIT_EVENT_TYPES: frozenset[str] = frozenset(
    set(RUNTIME_AUDIT_EVENT_TYPES) | set(LEGACY_API_AUDIT_EVENT_TYPES)
)
OPTIMIZER_INCLUDED_AUDIT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "DEF_ORCH_EXECUTED",
        "DEF_THROTTLE_APPLIED",
        "DEF_BLOCK_ENFORCED",
        "S3_CHALLENGE_RESULT",
        "S3_CHALLENGE_HALTED",
        "DEF_GUARD_SCORED",
    }
)

MANDATORY_AUDIT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "DEF_ORCH_EXECUTED",
        "DEF_PLAN_COMPUTED",
        "DEF_ANALYZER_EVIDENCE_UPDATED",
        "DEF_GUARD_SCORED",
        "DEF_THROTTLE_APPLIED",
        "DEF_BLOCK_ENFORCED",
        "S3_CHALLENGE_RESULT",
        "TURNSTILE_VERIFIED",
    }
)

_PROHIBITED_PII_KEYWORDS: tuple[str, ...] = (
    "email",
    "phone",
    "address",
    "dom",
    "selector",
    "raw_mouse",
    "raw_key",
    "ip",
)


@dataclass(slots=True)
class AuditEntry:
    ts_ms: int
    session_id: str
    event_type: str
    raw_payload: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    challenge_id: str | None = None
    flow_state: str | None = None
    risk_tier: str | None = None
    action: str | None = None
    reason_code: str | None = None
    policy_version: str | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []

        try:
            payload = validate_canonical_audit_row(self.to_dict())
        except ValueError as exc:
            errors.append(str(exc))
            return errors

        event_type = payload["event_type"]
        if event_type not in RUNTIME_AUDIT_EVENT_TYPES:
            errors.append(f"event_type not in audit catalog: {event_type}")

        pii_hits = _scan_pii_keys(payload)
        if pii_hits:
            errors.append("PII-prohibited keys found: " + ", ".join(sorted(pii_hits)))

        return errors

    def to_dict(self) -> dict[str, Any]:
        return build_canonical_audit_row(
            ts_ms=self.ts_ms,
            session_id=self.session_id,
            event_type=self.event_type,
            raw_payload=self.raw_payload,
            trace_id=self.trace_id,
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            challenge_id=self.challenge_id,
            flow_state=self.flow_state,
            risk_tier=self.risk_tier,
            action=self.action,
            reason_code=self.reason_code,
            policy_version=self.policy_version,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuditEntry":
        row = normalize_audit_row(data)
        return cls(
            ts_ms=row["ts_ms"],
            session_id=row["session_id"],
            event_type=row["event_type"],
            raw_payload=dict(row["raw_payload"]),
            trace_id=row.get("trace_id"),
            request_id=row.get("request_id"),
            correlation_id=row.get("correlation_id"),
            challenge_id=row.get("challenge_id"),
            flow_state=row.get("flow_state"),
            risk_tier=row.get("risk_tier"),
            action=row.get("action"),
            reason_code=row.get("reason_code"),
            policy_version=row.get("policy_version"),
        )


def _scan_pii_keys(data: Any, prefix: str = "") -> set[str]:
    hits: set[str] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            key_str = str(key)
            path = f"{prefix}.{key_str}" if prefix else key_str
            lower_key = key_str.lower()
            if any(word in lower_key for word in _PROHIBITED_PII_KEYWORDS):
                hits.add(path)
            hits.update(_scan_pii_keys(value, path))
    elif isinstance(data, list):
        for idx, value in enumerate(data):
            path = f"{prefix}[{idx}]"
            hits.update(_scan_pii_keys(value, path))
    return hits


__all__ = [
    "AuditEntry",
    "CANONICAL_AUDIT_EVENT_TYPES",
    "LEGACY_API_AUDIT_EVENT_TYPES",
    "MANDATORY_AUDIT_EVENT_TYPES",
    "OPTIMIZER_INCLUDED_AUDIT_EVENT_TYPES",
    "RUNTIME_AUDIT_EVENT_TYPES",
]
