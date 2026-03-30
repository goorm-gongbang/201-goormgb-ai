"""Semantic mapping helpers for raw defense audit rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..core.models import DefenseAuditEventRow


@dataclass(slots=True, frozen=True)
class EventSemantics:
    """Semantic interpretation derived from a raw audit row payload."""

    flow_state: str | None
    terminal_reason: str | None
    reason_code: str | None
    latest_flow_state: str | None
    latest_action: str | None
    latest_tier: str | None
    terminal_outcome: str | None


def map_event_semantics(row: DefenseAuditEventRow) -> EventSemantics:
    """Interpret semantic fields from raw payload without mutating the raw DTO."""

    flow_state = _find_string(row.payload, "flow_state", "flowState")
    terminal_reason = _find_string(row.payload, "terminal_reason", "terminalReason")
    reason_code = _find_string(row.payload, "reason_code", "reasonCode")
    latest_flow_state = _find_string(
        row.payload,
        "latest_flow_state",
        "latestFlowState",
    ) or flow_state
    latest_action = _find_string(
        row.payload,
        "latest_action",
        "latestAction",
        "action",
    )
    if latest_action is None:
        latest_action = _find_string(_nested_mapping(row.payload, "serverDecision"), "action")
    latest_tier = _find_string(
        row.payload,
        "latest_tier",
        "latestTier",
        "risk_tier",
        "riskTier",
    )
    if latest_tier is None:
        latest_tier = _find_string(_nested_mapping(row.payload, "serverDecision"), "riskTier")
    terminal_outcome = _find_string(row.payload, "terminal_outcome", "terminalOutcome")
    if terminal_outcome is None:
        terminal_outcome = _derive_terminal_outcome(latest_action=latest_action)

    return EventSemantics(
        flow_state=flow_state,
        terminal_reason=terminal_reason,
        reason_code=reason_code,
        latest_flow_state=latest_flow_state,
        latest_action=latest_action,
        latest_tier=latest_tier,
        terminal_outcome=terminal_outcome,
    )


def _derive_terminal_outcome(*, latest_action: str | None) -> str | None:
    if latest_action == "BLOCK":
        return "BLOCKED"
    if latest_action:
        return "NOT_BLOCKED"
    return None


def _nested_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return value
    return {}


def _find_string(payload: Mapping[str, Any], *keys: str) -> str | None:
    if not payload:
        return None
    for candidate_key, value in _iter_values(payload):
        if candidate_key not in keys:
            continue
        if isinstance(value, str) and value:
            return value
    return None


def _iter_values(value: Any):
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield str(key), nested
            yield from _iter_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_values(nested)


__all__ = ["EventSemantics", "map_event_semantics"]
