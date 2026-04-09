"""Semantic mapping helpers for raw defense audit rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence

from ..core.models import DefenseAuditEventRow
from ..legacy_normalization import normalize_action, normalize_flow_state


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

    flow_state = normalize_flow_state(
        _find_string(
        row.payload,
        "flow_state",
        "flowState",
        preferred_paths=(("flow_state",), ("flowState",)),
        )
    )
    terminal_reason = _find_string(
        row.payload,
        "terminal_reason",
        "terminalReason",
        preferred_paths=(
            ("terminal_reason",),
            ("terminalReason",),
            ("result", "terminal_reason"),
            ("result", "terminalReason"),
        ),
    )
    reason_code = _find_string(
        row.payload,
        "reason_code",
        "reasonCode",
        preferred_paths=(
            ("reason_code",),
            ("reasonCode",),
            ("result", "reason_code"),
            ("result", "reasonCode"),
        ),
    )
    latest_flow_state = normalize_flow_state(
        _find_string(
        row.payload,
        "latest_flow_state",
        "latestFlowState",
        preferred_paths=(("latest_flow_state",), ("latestFlowState",)),
        )
    ) or flow_state
    latest_action = normalize_action(
        _find_string(
        row.payload,
        "latest_action",
        "latestAction",
        "action",
        preferred_paths=(
            ("latest_action",),
            ("latestAction",),
            ("serverDecision", "action"),
            ("action",),
        ),
        )
    )
    latest_tier = _find_string(
        row.payload,
        "latest_tier",
        "latestTier",
        "risk_tier",
        "riskTier",
        preferred_paths=(
            ("latest_tier",),
            ("latestTier",),
            ("serverDecision", "riskTier"),
            ("risk_tier",),
            ("riskTier",),
        ),
    )
    terminal_outcome = _find_string(
        row.payload,
        "terminal_outcome",
        "terminalOutcome",
        preferred_paths=(("terminal_outcome",), ("terminalOutcome",)),
    )
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


def _get_nested(payload: Mapping[str, Any], path: Sequence[str]) -> Any | None:
    value: Any = payload
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
        if value is None:
            return None
    return value


def _find_string(
    payload: Mapping[str, Any],
    *keys: str,
    preferred_paths: Sequence[Sequence[str]] = (),
) -> str | None:
    if not payload:
        return None
    for path in preferred_paths:
        value = _get_nested(payload, path)
        if isinstance(value, str) and value:
            return value
    for candidate_key, value in _iter_values(payload):
        if candidate_key not in keys:
            continue
        if isinstance(value, str) and value:
            return value
    return None


def _iter_values(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield str(key), nested
            yield from _iter_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_values(nested)


__all__ = ["EventSemantics", "map_event_semantics"]
