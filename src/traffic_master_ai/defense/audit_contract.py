from __future__ import annotations

import re
from typing import Any, Mapping

CANONICAL_AUDIT_REQUIRED_FIELDS: tuple[str, ...] = (
    "ts_ms",
    "session_id",
    "event_type",
    "raw_payload",
)
CANONICAL_AUDIT_OPTIONAL_FIELDS: tuple[str, ...] = (
    "trace_id",
    "request_id",
    "correlation_id",
    "challenge_id",
    "flow_state",
    "risk_tier",
    "action",
    "reason_code",
    "policy_version",
)
CANONICAL_AUDIT_TOP_LEVEL_FIELDS: frozenset[str] = frozenset(
    CANONICAL_AUDIT_REQUIRED_FIELDS + CANONICAL_AUDIT_OPTIONAL_FIELDS
)

_LEGACY_TOP_LEVEL_ALIASES: dict[str, tuple[str, ...]] = {
    "ts_ms": ("ts_ms", "tsMs"),
    "session_id": ("session_id", "sessionId"),
    "event_type": ("event_type", "eventType"),
    "trace_id": ("trace_id", "traceId"),
    "request_id": ("request_id", "requestId"),
    "correlation_id": ("correlation_id", "correlationId"),
    "challenge_id": ("challenge_id", "challengeId"),
    "flow_state": ("flow_state", "flowState"),
    "risk_tier": ("risk_tier", "riskTier", "defense_tier", "defenseTier"),
    "action": ("action",),
    "reason_code": ("reason_code", "reasonCode"),
    "policy_version": ("policy_version", "policyVersion"),
}
_CANONICAL_GROUP_KEYS: tuple[str, ...] = (
    "request_meta",
    "result",
    "dedup",
    "throttle",
    "block",
    "challenge",
    "turnstile",
    "guard",
    "analyzer",
    "planner",
    "orchestrator",
    "langsmith",
    "server_decision",
)
_CAMEL_PATTERN_1 = re.compile("(.)([A-Z][a-z]+)")
_CAMEL_PATTERN_2 = re.compile("([a-z0-9])([A-Z])")


def build_canonical_audit_row(
    *,
    ts_ms: int,
    session_id: str,
    event_type: str,
    raw_payload: Mapping[str, Any] | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    challenge_id: str | None = None,
    flow_state: str | None = None,
    risk_tier: str | None = None,
    action: str | None = None,
    reason_code: str | None = None,
    policy_version: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "ts_ms": ts_ms,
        "session_id": session_id,
        "event_type": event_type,
        "raw_payload": _sanitize_mapping(raw_payload or {}),
    }
    for key, value in (
        ("trace_id", trace_id),
        ("request_id", request_id),
        ("correlation_id", correlation_id),
        ("challenge_id", challenge_id),
        ("flow_state", flow_state),
        ("risk_tier", risk_tier),
        ("action", action),
        ("reason_code", reason_code),
        ("policy_version", policy_version),
    ):
        if value is not None:
            row[key] = value
    return validate_canonical_audit_row(row)


def validate_canonical_audit_row(row: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ValueError("canonical audit row must be a mapping.")

    unknown_keys = sorted(str(key) for key in row.keys() if str(key) not in CANONICAL_AUDIT_TOP_LEVEL_FIELDS)
    if unknown_keys:
        raise ValueError("unknown canonical audit top-level fields: " + ", ".join(unknown_keys))

    ts_ms = row.get("ts_ms")
    if not isinstance(ts_ms, int) or isinstance(ts_ms, bool) or ts_ms < 0:
        raise ValueError("ts_ms must be a non-negative int.")

    session_id = row.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be a non-empty string.")

    event_type = row.get("event_type")
    if not isinstance(event_type, str) or not event_type:
        raise ValueError("event_type must be a non-empty string.")

    raw_payload = row.get("raw_payload")
    if not isinstance(raw_payload, Mapping):
        raise ValueError("raw_payload must be an object.")

    sanitized: dict[str, Any] = {
        "ts_ms": ts_ms,
        "session_id": session_id,
        "event_type": event_type,
        "raw_payload": _sanitize_mapping(raw_payload),
    }
    for field_name in CANONICAL_AUDIT_OPTIONAL_FIELDS:
        value = row.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must be a non-empty string when present.")
        sanitized[field_name] = value
    return sanitized


def normalize_audit_row(
    row: Mapping[str, Any],
    *,
    allow_legacy: bool = True,
) -> dict[str, Any]:
    if _looks_like_canonical(row):
        return validate_canonical_audit_row(row)
    if not allow_legacy:
        raise ValueError("canonical audit row must use the unified snake_case contract.")
    return _normalize_legacy_audit_row(row)


def build_warehouse_audit_row(row: Mapping[str, Any]) -> dict[str, Any]:
    canonical = normalize_audit_row(row)
    raw_payload = _sanitize_mapping(canonical["raw_payload"])
    request_meta = _mapping_from_payload(raw_payload, "request_meta")
    result = _mapping_from_payload(raw_payload, "result")
    server_decision = _mapping_from_payload(raw_payload, "server_decision")

    if canonical.get("correlation_id") and "correlationId" not in request_meta:
        request_meta["correlationId"] = canonical["correlation_id"]
    if canonical.get("reason_code") and "reasonCode" not in result:
        result["reasonCode"] = canonical["reason_code"]
    if canonical.get("risk_tier") and "riskTier" not in server_decision:
        server_decision["riskTier"] = canonical["risk_tier"]
    if canonical.get("action") and "action" not in server_decision:
        server_decision["action"] = canonical["action"]
    if canonical.get("policy_version") and "policyVersion" not in server_decision:
        server_decision["policyVersion"] = canonical["policy_version"]

    warehouse_row: dict[str, Any] = dict(canonical)
    warehouse_row["tsMs"] = canonical["ts_ms"]
    warehouse_row["sessionId"] = canonical["session_id"]
    warehouse_row["eventType"] = canonical["event_type"]
    if canonical.get("trace_id") is not None:
        warehouse_row["traceId"] = canonical["trace_id"]
    if canonical.get("request_id") is not None:
        warehouse_row["requestId"] = canonical["request_id"]
    if canonical.get("flow_state") is not None:
        warehouse_row["flowState"] = canonical["flow_state"]
    if canonical.get("challenge_id") is not None:
        warehouse_row["challengeId"] = canonical["challenge_id"]
    warehouse_row["requestMeta"] = request_meta
    warehouse_row["result"] = result
    warehouse_row["serverDecision"] = server_decision

    for key in _CANONICAL_GROUP_KEYS:
        warehouse_row[_snake_to_camel(key)] = _mapping_from_payload(raw_payload, key)

    warehouse_row["dedup_isDuplicate"] = bool(_nested_get(warehouse_row, "dedup", "isDuplicate", default=False))
    warehouse_row["result_httpStatus"] = _nested_get(warehouse_row, "result", "httpStatus")
    warehouse_row["result_reasonCode"] = _nested_get(warehouse_row, "result", "reasonCode")
    warehouse_row["turnstile_verifyStatus"] = _nested_get(warehouse_row, "turnstile", "verifyStatus")
    warehouse_row["challenge_result"] = _nested_get(warehouse_row, "challenge", "result")
    warehouse_row["throttle_delayMs"] = _nested_get(warehouse_row, "throttle", "delayMs")
    warehouse_row["throttle_endpointPath"] = _nested_get(warehouse_row, "throttle", "endpointPath")
    return warehouse_row


def _looks_like_canonical(row: Mapping[str, Any]) -> bool:
    return all(field_name in row for field_name in CANONICAL_AUDIT_REQUIRED_FIELDS)


def _normalize_legacy_audit_row(row: Mapping[str, Any]) -> dict[str, Any]:
    ts_ms = _required_int(row, "ts_ms")
    session_id = _required_text(row, "session_id")
    event_type = _required_text(row, "event_type")
    trace_id = _optional_text(row, "trace_id")
    request_id = _optional_text(row, "request_id")
    correlation_id = _optional_text(row, "correlation_id")
    challenge_id = _optional_text(row, "challenge_id") or _nested_optional_text(row, ("challenge", "challengeId"))
    flow_state = _optional_text(row, "flow_state")
    risk_tier = _optional_text(row, "risk_tier") or _nested_optional_text(row, ("serverDecision", "riskTier"))
    action = _optional_text(row, "action") or _nested_optional_text(row, ("serverDecision", "action"))
    reason_code = _optional_text(row, "reason_code") or _nested_optional_text(row, ("result", "reasonCode"))
    policy_version = _optional_text(row, "policy_version") or _nested_optional_text(row, ("serverDecision", "policyVersion"))

    request_meta = row.get("requestMeta")
    if correlation_id is None and isinstance(request_meta, Mapping):
        raw_correlation = request_meta.get("correlationId")
        if isinstance(raw_correlation, str) and raw_correlation:
            correlation_id = raw_correlation

    raw_payload: dict[str, Any] = {}
    payload = row.get("payload")
    if isinstance(payload, Mapping):
        raw_payload.update(_sanitize_mapping(payload))

    legacy_skip_keys = {
        alias
        for aliases in _LEGACY_TOP_LEVEL_ALIASES.values()
        for alias in aliases
    }
    legacy_skip_keys.update({"payload"})
    for key, value in row.items():
        key_text = str(key)
        if key_text in legacy_skip_keys:
            continue
        raw_payload[_camel_to_snake(key_text)] = _normalize_payload_value(value)

    if request_id is None and trace_id is not None:
        request_id = trace_id

    return build_canonical_audit_row(
        ts_ms=ts_ms,
        session_id=session_id,
        event_type=event_type,
        raw_payload=raw_payload,
        trace_id=trace_id,
        request_id=request_id,
        correlation_id=correlation_id,
        challenge_id=challenge_id,
        flow_state=flow_state,
        risk_tier=risk_tier,
        action=action,
        reason_code=reason_code,
        policy_version=policy_version,
    )


def _required_int(row: Mapping[str, Any], field_name: str) -> int:
    for alias in _LEGACY_TOP_LEVEL_ALIASES[field_name]:
        value = row.get(alias)
        if value is None:
            continue
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        break
    raise ValueError(f"{field_name} must be a non-negative int.")


def _required_text(row: Mapping[str, Any], field_name: str) -> str:
    value = _optional_text(row, field_name)
    if value is None:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value


def _optional_text(row: Mapping[str, Any], field_name: str) -> str | None:
    for alias in _LEGACY_TOP_LEVEL_ALIASES[field_name]:
        value = row.get(alias)
        if value is None:
            continue
        if isinstance(value, str) and value:
            return value
        break
    return None


def _nested_optional_text(row: Mapping[str, Any], path: tuple[str, ...]) -> str | None:
    current: Any = row
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
        if current is None:
            return None
    if isinstance(current, str) and current:
        return current
    return None


def _sanitize_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {_camel_to_snake(str(key)): _normalize_payload_value(value) for key, value in mapping.items()}


def _normalize_payload_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return { _camel_to_snake(str(key)): _normalize_payload_value(nested) for key, nested in value.items() }
    if isinstance(value, list):
        return [_normalize_payload_value(item) for item in value]
    return value


def _mapping_from_payload(raw_payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = raw_payload.get(key)
    if not isinstance(value, Mapping):
        return {}
    return _camelize_mapping(value)


def _camelize_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return { _snake_to_camel(str(key)): _camelize_value(value) for key, value in mapping.items() }


def _camelize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _camelize_mapping(value)
    if isinstance(value, list):
        return [_camelize_value(item) for item in value]
    return value


def _camel_to_snake(value: str) -> str:
    first_pass = _CAMEL_PATTERN_1.sub(r"\1_\2", value)
    return _CAMEL_PATTERN_2.sub(r"\1_\2", first_pass).replace("-", "_").lower()


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail if part)


def _nested_get(data: Mapping[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


__all__ = [
    "CANONICAL_AUDIT_OPTIONAL_FIELDS",
    "CANONICAL_AUDIT_REQUIRED_FIELDS",
    "CANONICAL_AUDIT_TOP_LEVEL_FIELDS",
    "build_canonical_audit_row",
    "build_warehouse_audit_row",
    "normalize_audit_row",
    "validate_canonical_audit_row",
]
