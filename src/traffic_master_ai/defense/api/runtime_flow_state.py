from __future__ import annotations

from ..d0_mvp.core.enums import FlowState as D0FlowState

RUNTIME_FLOW_STATES: frozenset[str] = frozenset(
    {
        "F0",
        "F1",
        "F2",
        "F3",
        "F3R",
        "F3M",
        "F4",
        "F4R",
        "F4M",
        "FX",
    }
)

_LEGACY_TO_RUNTIME_FLOW_STATE: dict[str, str] = {
    "S0": "F0",
    "S1": "F1",
    "S2": "F1",
    "S3": "F2",
    "S4": "F3",
    "S4R": "F3R",
    "S5": "F4",
    "S5R": "F4R",
    "S6": "FX",
    "SX": "FX",
}

_RUNTIME_TO_D0_FLOW_STATE: dict[str, D0FlowState] = {
    "F0": D0FlowState.S0,
    "F1": D0FlowState.S2,
    "F2": D0FlowState.S3,
    "F3": D0FlowState.S4,
    "F3R": D0FlowState.S4,
    "F3M": D0FlowState.S4,
    "F4": D0FlowState.S5,
    "F4R": D0FlowState.S5,
    "F4M": D0FlowState.S5,
    "FX": D0FlowState.SX,
}

_D0_TO_RUNTIME_FLOW_STATE: dict[D0FlowState, str] = {
    D0FlowState.S0: "F0",
    D0FlowState.S1: "F1",
    D0FlowState.S2: "F1",
    D0FlowState.S3: "F2",
    D0FlowState.S4: "F3",
    D0FlowState.S5: "F4",
    D0FlowState.S6: "FX",
    D0FlowState.SX: "FX",
}

_TARGET_EVENT_TO_RUNTIME_FLOW_STATE: dict[str, str] = {
    "QUEUE_ENTER": "F1",
    "SEAT_ENTRY": "F2",
    "RECOMMENDATION_BLOCKS": "F3R",
    "SECTION_BLOCKS": "F3M",
    "ASSIGN_HOLD": "F4R",
    "SEAT_HOLDS": "F4M",
}


def normalize_runtime_flow_state(value: str | None, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    normalized = value.strip().upper()
    if not normalized:
        return default
    if normalized in RUNTIME_FLOW_STATES:
        return normalized
    return _LEGACY_TO_RUNTIME_FLOW_STATE.get(normalized, default)


def runtime_flow_state_to_d0(value: str | None) -> D0FlowState:
    normalized = normalize_runtime_flow_state(value, default="F0") or "F0"
    return _RUNTIME_TO_D0_FLOW_STATE.get(normalized, D0FlowState.S0)


def d0_flow_state_to_runtime(value: D0FlowState | str | None) -> str:
    if isinstance(value, D0FlowState):
        return _D0_TO_RUNTIME_FLOW_STATE.get(value, "F0")
    try:
        return _D0_TO_RUNTIME_FLOW_STATE[D0FlowState(str(value or "").strip().upper())]
    except ValueError:
        return "F0"


def target_event_to_runtime_flow_state(event_type: str) -> str:
    normalized = str(event_type or "").strip().upper()
    return _TARGET_EVENT_TO_RUNTIME_FLOW_STATE.get(normalized, "F0")


__all__ = [
    "RUNTIME_FLOW_STATES",
    "d0_flow_state_to_runtime",
    "normalize_runtime_flow_state",
    "runtime_flow_state_to_d0",
    "target_event_to_runtime_flow_state",
]
