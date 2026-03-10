from __future__ import annotations

from ..state import AgentState
from traffic_master_ai.common.models.states import FlowState


def route_by_flow_state(state: AgentState) -> str:
    """Route to the next node based on the current FlowState."""
    fs = state.flow_state
    if fs == FlowState.S0:
        return "init"
    if fs == FlowState.S1:
        return "pre_entry"
    if fs == FlowState.S2:
        return "queue"
    if fs == FlowState.S3:
        return "security"
    if fs == FlowState.S4:
        return "section_map"
    if fs == FlowState.S4R:
        return "recommend"
    if fs == FlowState.S5:
        return "seat_map"
    if fs == FlowState.S5R:
        return "accept_recommend"
    if fs == FlowState.S6:
        return "payment"
    if fs == FlowState.SX:
        return "terminal"
    return "terminal"

