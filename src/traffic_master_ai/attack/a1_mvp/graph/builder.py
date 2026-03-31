from __future__ import annotations

from langgraph.graph import END, StateGraph

from ..state import AgentState
from .context import AgentContext
from .nodes import (
    node_accept_recommend,
    node_init,
    node_payment,
    node_pre_entry,
    node_queue,
    node_recommend,
    node_security,
    node_section_map,
    node_seat_map,
    node_terminal,
)
from .routes import route_by_flow_state


def build_graph() -> StateGraph:
    g: StateGraph = StateGraph(state_schema=AgentState, context_schema=AgentContext)

    g.add_node("init", node_init)
    g.add_node("pre_entry", node_pre_entry)
    g.add_node("queue", node_queue)
    g.add_node("security", node_security)
    g.add_node("section_map", node_section_map)
    g.add_node("seat_map", node_seat_map)
    g.add_node("recommend", node_recommend)
    g.add_node("accept_recommend", node_accept_recommend)
    g.add_node("payment", node_payment)
    g.add_node("terminal", node_terminal)

    g.set_entry_point("init")

    # Conditional routing for all nodes based on FlowState.
    mapping = {
        "init": "init",
        "pre_entry": "pre_entry",
        "queue": "queue",
        "security": "security",
        "section_map": "section_map",
        "seat_map": "seat_map",
        "recommend": "recommend",
        "accept_recommend": "accept_recommend",
        "payment": "payment",
        "terminal": "terminal",
    }

    for src in [
        "init",
        "pre_entry",
        "queue",
        "security",
        "section_map",
        "seat_map",
        "recommend",
        "accept_recommend",
        "payment",
    ]:
        g.add_conditional_edges(src, route_by_flow_state, mapping)

    g.add_edge("terminal", END)

    return g


def compile_app():
    return build_graph().compile()

