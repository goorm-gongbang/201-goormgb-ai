"""Events package — event catalog and common event model.

Ref: L1/runtime/events.yaml
"""

from .catalog import (
    # Runtime event types
    FLOW_STATE_TRANSITION,
    HIGH_VALUE_CLICK,
    S3_RESULT,
    API_CALL_OBS,
    TURNSTILE_TRIGGERED,
    TURNSTILE_VERIFIED,
    RUNTIME_EVENT_TYPES,
    # Audit event types
    AUDIT_EVENT_TYPES,
    DEF_GUARD_SCORED,
    DEF_ANALYZER_EVIDENCE_UPDATED,
    DEF_PLAN_COMPUTED,
    DEF_ORCH_EXECUTED,
    DEF_INVALID_TRANSITION,
    DEF_THROTTLE_APPLIED,
    DEF_BLOCK_DECIDED,
    DEF_BLOCK_ENFORCED,
    S3_CHALLENGE_ISSUED,
    S3_CHALLENGE_RESULT,
    S3_CHALLENGE_HALTED,
    validate_event_payload,
    validate_runtime_event_envelope,
    assert_valid_event_payload,
)
from .common import RuntimeEvent

__all__ = [
    "RuntimeEvent",
    "FLOW_STATE_TRANSITION",
    "HIGH_VALUE_CLICK",
    "S3_RESULT",
    "API_CALL_OBS",
    "TURNSTILE_TRIGGERED",
    "TURNSTILE_VERIFIED",
    "RUNTIME_EVENT_TYPES",
    "AUDIT_EVENT_TYPES",
    "DEF_GUARD_SCORED",
    "DEF_ANALYZER_EVIDENCE_UPDATED",
    "DEF_PLAN_COMPUTED",
    "DEF_ORCH_EXECUTED",
    "DEF_INVALID_TRANSITION",
    "DEF_THROTTLE_APPLIED",
    "DEF_BLOCK_DECIDED",
    "DEF_BLOCK_ENFORCED",
    "S3_CHALLENGE_ISSUED",
    "S3_CHALLENGE_RESULT",
    "S3_CHALLENGE_HALTED",
    "validate_event_payload",
    "validate_runtime_event_envelope",
    "assert_valid_event_payload",
]
