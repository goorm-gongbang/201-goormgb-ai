"""Executable workflow entrypoint for Backoffice Copilot."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.issues import PipelineIssue
from ..core.models import RunStatus
from ..core.state import PostReviewGraphState, PostReviewRunInput
from ..validation import ResolvedValidationOutcome, validate_run_input_params
from .graph import BackofficeCopilotWorkflowGraph, build_workflow_graph
from .nodes import BackofficeCopilotWorkflowDependencies


@dataclass(slots=True, frozen=True)
class WorkflowExecutionResult:
    """Workflow invocation output with final state and execution trace."""

    state: PostReviewGraphState
    node_history: tuple[str, ...]
    final_status: RunStatus
    validation_outcome: ResolvedValidationOutcome | None = None


@dataclass(slots=True)
class BackofficeCopilotWorkflowApp:
    """Thin sequential app that preserves the fixed six-node graph contract."""

    dependencies: BackofficeCopilotWorkflowDependencies
    graph: BackofficeCopilotWorkflowGraph

    def invoke(self, run_input: PostReviewRunInput) -> WorkflowExecutionResult:
        """Run the fixed workflow from graph input to final state."""

        state = PostReviewGraphState.from_input(run_input)
        input_check = validate_run_input_params(run_input)
        if input_check.has_errors:
            state.errors.extend(input_check.errors)
            return WorkflowExecutionResult(
                state=state,
                node_history=(),
                final_status="FAILED",
            )

        node_history: list[str] = []
        validation_outcome: ResolvedValidationOutcome | None = None
        for node in self.graph.nodes:
            try:
                node_result = node.handler(state, self.dependencies)
            except Exception as exc:
                state.errors.append(
                    PipelineIssue(
                        code="workflow_node_failed",
                        message="Workflow node execution failed.",
                        context={
                            "node_name": node.name,
                            "failure_reason": f"{type(exc).__name__}: {exc}",
                        },
                    )
                )
                return WorkflowExecutionResult(
                    state=state,
                    node_history=tuple(node_history),
                    final_status="FAILED",
                    validation_outcome=validation_outcome,
                )

            state = node_result.state
            node_history.append(node.name)
            if node_result.validation_outcome is not None:
                validation_outcome = node_result.validation_outcome

        final_status: RunStatus
        if validation_outcome is not None:
            final_status = validation_outcome.final_status
        elif state.errors:
            final_status = "FAILED"
        else:
            final_status = "SUCCESS"
        return WorkflowExecutionResult(
            state=state,
            node_history=tuple(node_history),
            final_status=final_status,
            validation_outcome=validation_outcome,
        )


def build_backoffice_copilot_workflow(
    dependencies: BackofficeCopilotWorkflowDependencies,
) -> BackofficeCopilotWorkflowApp:
    """Build the executable workflow app with the fixed six-node graph."""

    return BackofficeCopilotWorkflowApp(
        dependencies=dependencies,
        graph=build_workflow_graph(),
    )


__all__ = [
    "BackofficeCopilotWorkflowApp",
    "WorkflowExecutionResult",
    "build_backoffice_copilot_workflow",
]
