from __future__ import annotations

from ..d0_mvp.core.enums import FlowState as D0FlowState

SEAT_MODES: frozenset[str] = frozenset({"RECOMMENDATION", "MANUAL"})

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

_TARGET_EVENT_TO_SEAT_MODE: dict[str, str] = {
    "RECOMMENDATION_BLOCKS": "RECOMMENDATION",
    "SECTION_BLOCKS": "MANUAL",
    "ASSIGN_HOLD": "RECOMMENDATION",
    "SEAT_HOLDS": "MANUAL",
}

_RUNTIME_FLOW_STATE_TO_SEAT_MODE: dict[str, str] = {
    "F3R": "RECOMMENDATION",
    "F3M": "MANUAL",
    "F4R": "RECOMMENDATION",
    "F4M": "MANUAL",
}

_RUNTIME_FLOW_STATE_ORDER: dict[str, int] = {
    "F0": 0,
    "F1": 1,
    "F2": 2,
    "F3": 3,
    "F3R": 3,
    "F3M": 3,
    "F4": 4,
    "F4R": 4,
    "F4M": 4,
    "FX": 5,
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


def normalize_seat_mode(value: str | None, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    normalized = value.strip().upper()
    if not normalized:
        return default
    if normalized in SEAT_MODES:
        return normalized
    return default


def runtime_flow_state_to_seat_mode(value: str | None) -> str | None:
    normalized = normalize_runtime_flow_state(value, default=None)
    if normalized is None:
        return None
    return _RUNTIME_FLOW_STATE_TO_SEAT_MODE.get(normalized)


def target_event_to_seat_mode(event_type: str) -> str | None:
    normalized = str(event_type or "").strip().upper()
    return _TARGET_EVENT_TO_SEAT_MODE.get(normalized)


def d0_flow_state_to_runtime_with_seat_mode(
    value: D0FlowState | str | None,
    *,
    seat_mode: str | None = None,
) -> str:
    base_flow_state = d0_flow_state_to_runtime(value)
    normalized_seat_mode = normalize_seat_mode(seat_mode, default=None)
    if base_flow_state == "F3":
        if normalized_seat_mode == "RECOMMENDATION":
            return "F3R"
        if normalized_seat_mode == "MANUAL":
            return "F3M"
    if base_flow_state == "F4":
        if normalized_seat_mode == "RECOMMENDATION":
            return "F4R"
        if normalized_seat_mode == "MANUAL":
            return "F4M"
    return base_flow_state


def merge_runtime_flow_state(current: str | None, candidate: str | None) -> str:
    normalized_candidate = normalize_runtime_flow_state(candidate, default="F0") or "F0"
    normalized_current = normalize_runtime_flow_state(current, default=None)
    if normalized_current is None:
        return normalized_candidate

    current_order = _RUNTIME_FLOW_STATE_ORDER.get(normalized_current, 0)
    candidate_order = _RUNTIME_FLOW_STATE_ORDER.get(normalized_candidate, 0)
    if current_order > candidate_order:
        return normalized_current
    if current_order < candidate_order:
        return normalized_candidate

    if normalized_current in {"F3R", "F3M"} and normalized_candidate == "F3":
        return normalized_current
    if normalized_current in {"F4R", "F4M"} and normalized_candidate == "F4":
        return normalized_current
    return normalized_candidate


def target_event_to_runtime_flow_state(event_type: str) -> str:
    normalized = str(event_type or "").strip().upper()
    return _TARGET_EVENT_TO_RUNTIME_FLOW_STATE.get(normalized, "F0")


__all__ = [
    "RUNTIME_FLOW_STATES",
    "d0_flow_state_to_runtime",
    "d0_flow_state_to_runtime_with_seat_mode",
    "merge_runtime_flow_state",
    "normalize_runtime_flow_state",
    "normalize_seat_mode",
    "runtime_flow_state_to_d0",
    "runtime_flow_state_to_seat_mode",
    "target_event_to_seat_mode",
    "target_event_to_runtime_flow_state",
]
