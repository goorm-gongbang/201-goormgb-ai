"""Authoritative event catalog and payload validators.

Ref:
- L1/runtime/events.yaml#event_catalog
- L1/runtime/events.yaml#audit_event_catalog
"""

from __future__ import annotations

import math
from typing import Any, Mapping


# =========================================
# Runtime event types (events.yaml §event_catalog.eventTypes)
# =========================================
FLOW_STATE_TRANSITION: str = "FLOW_STATE_TRANSITION"
HIGH_VALUE_CLICK: str = "HIGH_VALUE_CLICK"
S3_RESULT: str = "S3_RESULT"
API_CALL_OBS: str = "API_CALL_OBS"
TURNSTILE_TRIGGERED: str = "TURNSTILE_TRIGGERED"
TURNSTILE_VERIFIED: str = "TURNSTILE_VERIFIED"

RUNTIME_EVENT_TYPES: frozenset[str] = frozenset(
    {
        FLOW_STATE_TRANSITION,
        HIGH_VALUE_CLICK,
        S3_RESULT,
        API_CALL_OBS,
        TURNSTILE_TRIGGERED,
        TURNSTILE_VERIFIED,
    }
)

# =========================================
# Audit event types (events.yaml §audit_event_catalog.eventTypes)
# =========================================
DEF_GUARD_SCORED: str = "DEF_GUARD_SCORED"
DEF_ANALYZER_EVIDENCE_UPDATED: str = "DEF_ANALYZER_EVIDENCE_UPDATED"
DEF_PLAN_COMPUTED: str = "DEF_PLAN_COMPUTED"
DEF_ORCH_EXECUTED: str = "DEF_ORCH_EXECUTED"
DEF_INVALID_TRANSITION: str = "DEF_INVALID_TRANSITION"
DEF_THROTTLE_APPLIED: str = "DEF_THROTTLE_APPLIED"
DEF_BLOCK_DECIDED: str = "DEF_BLOCK_DECIDED"
DEF_BLOCK_ENFORCED: str = "DEF_BLOCK_ENFORCED"
DEFENSE_UNAVAILABLE: str = "DEFENSE_UNAVAILABLE"
S3_CHALLENGE_ISSUED: str = "S3_CHALLENGE_ISSUED"
S3_CHALLENGE_RESULT: str = "S3_CHALLENGE_RESULT"
S3_CHALLENGE_HALTED: str = "S3_CHALLENGE_HALTED"

AUDIT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        DEF_GUARD_SCORED,
        DEF_ANALYZER_EVIDENCE_UPDATED,
        DEF_PLAN_COMPUTED,
        DEF_ORCH_EXECUTED,
        DEF_INVALID_TRANSITION,
        DEF_THROTTLE_APPLIED,
        DEF_BLOCK_DECIDED,
        DEF_BLOCK_ENFORCED,
        DEFENSE_UNAVAILABLE,
        S3_CHALLENGE_ISSUED,
        S3_CHALLENGE_RESULT,
        S3_CHALLENGE_HALTED,
        # Runtime events also used as audit events
        TURNSTILE_TRIGGERED,
        TURNSTILE_VERIFIED,
    }
)

# =========================================
# Enum values
# =========================================
FLOW_STATE_ENUM: frozenset[str] = frozenset({"S0", "S1", "S2", "S3", "S4", "S5", "S6", "SX"})
_FLOW_ALLOWED_S1_TO_S5: frozenset[str] = frozenset({"S1", "S2", "S3", "S4", "S5"})
_FLOW_ALLOWED_S1_TO_S3: frozenset[str] = frozenset({"S1", "S2", "S3"})

EVENT_ALLOWED_FLOW_STATES: dict[str, frozenset[str]] = {
    FLOW_STATE_TRANSITION: FLOW_STATE_ENUM,
    HIGH_VALUE_CLICK: _FLOW_ALLOWED_S1_TO_S5,
    S3_RESULT: frozenset({"S3"}),
    API_CALL_OBS: _FLOW_ALLOWED_S1_TO_S5,
    TURNSTILE_TRIGGERED: _FLOW_ALLOWED_S1_TO_S3,
    TURNSTILE_VERIFIED: _FLOW_ALLOWED_S1_TO_S3,
}

HVC_SECTION_SELECT: str = "SECTION_SELECT"
HVC_SEAT_SELECT: str = "SEAT_SELECT"
HVC_HOLD_CLICK: str = "HOLD_CLICK"
HVC_PAYMENT_INIT_CLICK: str = "PAYMENT_INIT_CLICK"
HVC_CONFIRM_CLICK: str = "CONFIRM_CLICK"

HVC_TAG_ENUM: frozenset[str] = frozenset(
    {
        HVC_SECTION_SELECT,
        HVC_SEAT_SELECT,
        HVC_HOLD_CLICK,
        HVC_PAYMENT_INIT_CLICK,
        HVC_CONFIRM_CLICK,
    }
)

S3_PASS: str = "PASS"
S3_FAIL: str = "FAIL"
S3_UNKNOWN: str = "UNKNOWN"
S3_RESULT_ENUM: frozenset[str] = frozenset({S3_PASS, S3_FAIL, S3_UNKNOWN})

VERIFY_OK: str = "OK"
VERIFY_TIMEOUT: str = "TIMEOUT"
VERIFY_ERROR: str = "ERROR"
VERIFY_INVALID_TOKEN: str = "INVALID_TOKEN"
VERIFY_MISSING_TOKEN: str = "MISSING_TOKEN"

TURNSTILE_VERIFY_STATUS_ENUM: frozenset[str] = frozenset(
    {
        VERIFY_OK,
        VERIFY_TIMEOUT,
        VERIFY_ERROR,
        VERIFY_INVALID_TOKEN,
        VERIFY_MISSING_TOKEN,
    }
)

TURNSTILE_TRIGGER_ENUM: frozenset[str] = frozenset({"S1_ENTRY_CLICKED", "S2_TO_S3_PRECHECK"})
TURNSTILE_WIDGET_MODE_ENUM: frozenset[str] = frozenset(
    {"MANAGED", "INVISIBLE", "NON_INTERACTIVE"}
)
API_METHOD_ENUM: frozenset[str] = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH"})
API_CATEGORY_ENUM: frozenset[str] = frozenset({"READ", "WRITE", "HIGH_VALUE"})
S3_REASON_ENUM: frozenset[str] = frozenset(
    {
        "CHALLENGE_PASSED",
        "CHALLENGE_FAILED",
        "CHALLENGE_EXPIRED",
        "CHALLENGE_INVALID",
        "CHALLENGE_VERIFY_UNAVAILABLE",
    }
)


def validate_event_payload(event_type: str, payload: Mapping[str, Any]) -> list[str]:
    """Validate payload against L1/runtime/events.yaml payloadSchemas."""
    errors: list[str] = []

    if event_type not in RUNTIME_EVENT_TYPES:
        return [f"unknown eventType: {event_type}"]

    if event_type == FLOW_STATE_TRANSITION:
        _require_str_enum(payload, "fromState", FLOW_STATE_ENUM, errors)
        _require_str_enum(payload, "toState", FLOW_STATE_ENUM, errors)
        return errors

    if event_type == HIGH_VALUE_CLICK:
        _require_str_enum(payload, "tag", HVC_TAG_ENUM, errors)
        return errors

    if event_type == S3_RESULT:
        _require_str_enum(payload, "result", S3_RESULT_ENUM, errors)
        _optional_str_enum(payload, "reasonCode", S3_REASON_ENUM, errors)
        return errors

    if event_type == API_CALL_OBS:
        _require_str(payload, "path", errors)
        _require_str_enum(payload, "method", API_METHOD_ENUM, errors)
        _optional_str_enum(payload, "category", API_CATEGORY_ENUM, errors)
        _optional_int(payload, "statusCode", errors)
        return errors

    if event_type == TURNSTILE_TRIGGERED:
        _require_str_enum(payload, "triggerId", TURNSTILE_TRIGGER_ENUM, errors)
        _optional_str_enum(payload, "widgetMode", TURNSTILE_WIDGET_MODE_ENUM, errors)
        return errors

    if event_type == TURNSTILE_VERIFIED:
        ext = payload.get("externalScore")
        if not _is_number(ext):
            errors.append("externalScore must be float in [0,1]")
        else:
            ext_f = float(ext)
            if ext_f < 0.0 or ext_f > 1.0:
                errors.append("externalScore must be within [0,1]")
        _require_str_enum(payload, "verifyStatus", TURNSTILE_VERIFY_STATUS_ENUM, errors)
        _optional_int(payload, "verifyLatencyMs", errors)
        _optional_bool(payload, "cached", errors)
        return errors

    return errors


def validate_runtime_event_envelope(
    *,
    event_type: str,
    ts_ms: int,
    flow_state: str,
    payload: Mapping[str, Any],
) -> list[str]:
    """Validate common context + payload schema for one runtime event."""
    errors: list[str] = []
    if event_type not in RUNTIME_EVENT_TYPES:
        errors.append(f"unknown eventType: {event_type}")
    if not isinstance(ts_ms, int) or ts_ms < 0:
        errors.append("tsMs must be non-negative int")
    if flow_state not in FLOW_STATE_ENUM:
        errors.append(f"invalid flowState: {flow_state}")
    allowed_flow_states = EVENT_ALLOWED_FLOW_STATES.get(event_type)
    if allowed_flow_states is not None and flow_state not in allowed_flow_states:
        errors.append(f"flowState {flow_state} is not allowed for eventType {event_type}")
    errors.extend(validate_event_payload(event_type, payload))
    return errors


def assert_valid_event_payload(event_type: str, payload: Mapping[str, Any]) -> None:
    """Raise ValueError when payload is invalid."""
    errors = validate_event_payload(event_type, payload)
    if errors:
        raise ValueError("; ".join(errors))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not math.isnan(float(value)) and not math.isinf(float(value))


def _require_str(payload: Mapping[str, Any], key: str, errors: list[str]) -> None:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        errors.append(f"{key} must be non-empty string")


def _require_str_enum(
    payload: Mapping[str, Any],
    key: str,
    allowed: frozenset[str],
    errors: list[str],
) -> None:
    value = payload.get(key)
    if not isinstance(value, str):
        errors.append(f"{key} must be string")
        return
    if value not in allowed:
        errors.append(f"{key} has invalid value: {value}")


def _optional_str_enum(
    payload: Mapping[str, Any],
    key: str,
    allowed: frozenset[str],
    errors: list[str],
) -> None:
    if key not in payload or payload.get(key) is None:
        return
    value = payload.get(key)
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"{key} has invalid value: {value}")


def _optional_int(payload: Mapping[str, Any], key: str, errors: list[str]) -> None:
    if key not in payload or payload.get(key) is None:
        return
    if not isinstance(payload.get(key), int):
        errors.append(f"{key} must be int")


def _optional_bool(payload: Mapping[str, Any], key: str, errors: list[str]) -> None:
    if key not in payload or payload.get(key) is None:
        return
    if not isinstance(payload.get(key), bool):
        errors.append(f"{key} must be bool")
