"""Observability schemas for decision_audit JSONL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..events.catalog import AUDIT_EVENT_TYPES

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
    """Decision audit entry (L0 minimum + L2 extension)."""

    ts_ms: int
    event_type: str
    trace_id: str
    session_id: str
    flow_state: str
    request_id: str
    server_decision: dict[str, Any]
    result: dict[str, Any]
    dedup: dict[str, Any] = field(default_factory=dict)
    throttle: dict[str, Any] = field(default_factory=dict)
    block: dict[str, Any] = field(default_factory=dict)
    challenge: dict[str, Any] = field(default_factory=dict)
    turnstile: dict[str, Any] = field(default_factory=dict)
    guard: dict[str, Any] = field(default_factory=dict)
    analyzer: dict[str, Any] = field(default_factory=dict)
    planner: dict[str, Any] = field(default_factory=dict)
    orchestrator: dict[str, Any] = field(default_factory=dict)
    langsmith: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Validate against required minimum schema and privacy policy."""
        errors: list[str] = []

        if not isinstance(self.ts_ms, int) or self.ts_ms < 0:
            errors.append("tsMs must be non-negative int")
        if not isinstance(self.event_type, str) or not self.event_type:
            errors.append("eventType must be non-empty string")
        if self.event_type not in AUDIT_EVENT_TYPES:
            errors.append(f"eventType not in audit catalog: {self.event_type}")
        if not isinstance(self.trace_id, str) or not self.trace_id:
            errors.append("traceId required")
        if not isinstance(self.session_id, str) or not self.session_id:
            errors.append("sessionId required")
        if self.flow_state not in {"S0", "S1", "S2", "S3", "S4", "S5", "S6", "SX"}:
            errors.append(f"invalid flowState: {self.flow_state}")
        if not isinstance(self.request_id, str) or not self.request_id:
            errors.append("requestId required")

        if not isinstance(self.server_decision, dict):
            errors.append("serverDecision must be object")
        else:
            if self.server_decision.get("riskTier") not in {"T0", "T1", "T2", "T3"}:
                errors.append("serverDecision.riskTier invalid")
            if self.server_decision.get("action") not in {
                "NONE",
                "THROTTLE",
                "REQUIRE_S3",
                "BLOCK",
            }:
                errors.append("serverDecision.action invalid")
            if not isinstance(self.server_decision.get("policyVersion"), str):
                errors.append("serverDecision.policyVersion required")

        if not isinstance(self.result, dict):
            errors.append("result must be object")
        else:
            if self.result.get("status") not in {"OK", "FAIL"}:
                errors.append("result.status invalid")

        pii_hits = _scan_pii_keys(self.to_dict())
        if pii_hits:
            errors.append("PII-prohibited keys found: " + ", ".join(sorted(pii_hits)))

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-ready dict."""
        return {
            "tsMs": self.ts_ms,
            "eventType": self.event_type,
            "traceId": self.trace_id,
            "sessionId": self.session_id,
            "flowState": self.flow_state,
            "requestId": self.request_id,
            "serverDecision": self.server_decision,
            "result": self.result,
            "dedup": self.dedup,
            "throttle": self.throttle,
            "block": self.block,
            "challenge": self.challenge,
            "turnstile": self.turnstile,
            "guard": self.guard,
            "analyzer": self.analyzer,
            "planner": self.planner,
            "orchestrator": self.orchestrator,
            "langsmith": self.langsmith,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuditEntry":
        """Build entry from dict using audit JSON field names."""
        return cls(
            ts_ms=int(data.get("tsMs", 0)),
            event_type=str(data.get("eventType", "")),
            trace_id=str(data.get("traceId", "")),
            session_id=str(data.get("sessionId", "")),
            flow_state=str(data.get("flowState", "")),
            request_id=str(data.get("requestId", "")),
            server_decision=dict(data.get("serverDecision", {})),
            result=dict(data.get("result", {})),
            dedup=dict(data.get("dedup", {})),
            throttle=dict(data.get("throttle", {})),
            block=dict(data.get("block", {})),
            challenge=dict(data.get("challenge", {})),
            turnstile=dict(data.get("turnstile", {})),
            guard=dict(data.get("guard", {})),
            analyzer=dict(data.get("analyzer", {})),
            planner=dict(data.get("planner", {})),
            orchestrator=dict(data.get("orchestrator", {})),
            langsmith=dict(data.get("langsmith", {})),
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


__all__ = ["AuditEntry", "MANDATORY_AUDIT_EVENT_TYPES"]
