"""Workflow assembly exports for Backoffice Copilot."""

from .app import (
    BackofficeCopilotWorkflowApp,
    WorkflowExecutionResult,
    build_backoffice_copilot_workflow,
)
from .graph import (
    BackofficeCopilotWorkflowGraph,
    WORKFLOW_NODE_DEFINITIONS,
    WORKFLOW_NODE_ORDER,
    WorkflowNodeDefinition,
    build_workflow_graph,
)
from .nodes import BackofficeCopilotWorkflowDependencies, NodeExecutionResult

__all__ = [
    "BackofficeCopilotWorkflowApp",
    "BackofficeCopilotWorkflowDependencies",
    "BackofficeCopilotWorkflowGraph",
    "NodeExecutionResult",
    "WORKFLOW_NODE_DEFINITIONS",
    "WORKFLOW_NODE_ORDER",
    "WorkflowExecutionResult",
    "WorkflowNodeDefinition",
    "build_backoffice_copilot_workflow",
    "build_workflow_graph",
]
