"""Fixed six-node workflow assembly for Backoffice Copilot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..core.state import PostReviewGraphState
from .nodes import (
    BackofficeCopilotWorkflowDependencies,
    NodeExecutionResult,
    node_1_input_collection,
    node_2_candidate_selection,
    node_3_session_analysis,
    node_4_review,
    node_5_summary,
    node_6_output_delivery,
)

type WorkflowNodeHandler = Callable[
    [PostReviewGraphState, BackofficeCopilotWorkflowDependencies],
    NodeExecutionResult,
]


@dataclass(slots=True, frozen=True)
class WorkflowNodeDefinition:
    """One fixed workflow node definition."""

    name: str
    handler: WorkflowNodeHandler


WORKFLOW_NODE_DEFINITIONS: tuple[WorkflowNodeDefinition, ...] = (
    WorkflowNodeDefinition("node_1_input_collection", node_1_input_collection),
    WorkflowNodeDefinition("node_2_candidate_selection", node_2_candidate_selection),
    WorkflowNodeDefinition("node_3_session_analysis", node_3_session_analysis),
    WorkflowNodeDefinition("node_4_review", node_4_review),
    WorkflowNodeDefinition("node_5_summary", node_5_summary),
    WorkflowNodeDefinition("node_6_output_delivery", node_6_output_delivery),
)
WORKFLOW_NODE_ORDER: tuple[str, ...] = tuple(node.name for node in WORKFLOW_NODE_DEFINITIONS)


@dataclass(slots=True, frozen=True)
class BackofficeCopilotWorkflowGraph:
    """Equivalent graph assembly used when LangGraph is not available."""

    nodes: tuple[WorkflowNodeDefinition, ...] = WORKFLOW_NODE_DEFINITIONS

    def __post_init__(self) -> None:
        node_names = tuple(node.name for node in self.nodes)
        if node_names != WORKFLOW_NODE_ORDER:
            raise ValueError("Workflow nodes must keep the fixed six-node order from the spec.")
        if len(self.nodes) != 6:
            raise ValueError("Workflow node count must remain exactly 6.")


def build_workflow_graph() -> BackofficeCopilotWorkflowGraph:
    """Build the fixed six-node graph definition."""

    return BackofficeCopilotWorkflowGraph()


__all__ = [
    "BackofficeCopilotWorkflowGraph",
    "WORKFLOW_NODE_DEFINITIONS",
    "WORKFLOW_NODE_ORDER",
    "WorkflowNodeDefinition",
    "build_workflow_graph",
]
