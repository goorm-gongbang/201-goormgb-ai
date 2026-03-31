"""Thin workflow node wrappers for the Backoffice Copilot pipeline."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from ..analysis import DecisionAuditRowProvider
from ..analysis.candidates import build_candidate_selection
from ..analysis.fallback import DEFAULT_RAW_FALLBACK_LIMIT
from ..analysis.session_analysis import build_session_analysis_list
from ..core.issues import PipelineIssue
from ..core.models import RunStatus
from ..core.state import PostReviewGraphState, PostReviewRunInput
from ..ingest import load_analysis_input
from ..output import BackendRequestAdapter, OutputStageResult, build_export_artifacts, execute_output_stage
from ..review.executor import LlmReviewAdapter, execute_session_reviews
from ..storage.repository import PostReviewWriteRepository
from ..summary.window_summary import WindowSummaryAdapter, generate_summary_text
from ..validation import ResolvedValidationOutcome, ValidationContext, resolve_run_validation


@dataclass(slots=True, frozen=True)
class BackofficeCopilotWorkflowDependencies:
    """External resources and adapters needed by the fixed six-node workflow."""

    audit_events_jsonl_path: str | Path
    repository: PostReviewWriteRepository
    conflict_policy: PkConflictPolicy | str
    raw_fallback_provider: DecisionAuditRowProvider | None = None
    llm_review_adapter: LlmReviewAdapter | None = None
    summary_adapter: WindowSummaryAdapter | None = None
    backend_adapter: BackendRequestAdapter | None = None
    export_dir: str | Path | None = None
    session_analysis_max_workers: int = 4
    review_max_workers: int = 4
    raw_fallback_limit: int = DEFAULT_RAW_FALLBACK_LIMIT
    repository_ready: bool = True
    output_now: datetime | None = None


@dataclass(slots=True, frozen=True)
class NodeExecutionResult:
    """Uniform node wrapper output for workflow assembly."""

    state: PostReviewGraphState
    validation_outcome: ResolvedValidationOutcome | None = None


def node_1_input_collection(
    state: PostReviewGraphState,
    dependencies: BackofficeCopilotWorkflowDependencies,
) -> NodeExecutionResult:
    """Node 1. Load raw audit input only."""

    state.analysis_input = load_analysis_input(
        dependencies.audit_events_jsonl_path,
        run_input=_to_run_input(state),
    )
    return NodeExecutionResult(state=state)


def node_2_candidate_selection(
    state: PostReviewGraphState,
    dependencies: BackofficeCopilotWorkflowDependencies,
) -> NodeExecutionResult:
    """Node 2. Build session summaries and candidate subset."""

    del dependencies
    selection = build_candidate_selection(state.analysis_input)
    state.session_summaries = list(selection.session_summaries)
    state.candidate_sessions = list(selection.candidate_sessions)
    state.warnings.extend(selection.warnings)
    return NodeExecutionResult(state=state)


def node_3_session_analysis(
    state: PostReviewGraphState,
    dependencies: BackofficeCopilotWorkflowDependencies,
) -> NodeExecutionResult:
    """Node 3. Build per-session analysis objects."""

    state.session_analysis_list = list(
        build_session_analysis_list(
            state.candidate_sessions,
            state.analysis_input,
            window_start_ms=state.window_start_ms,
            window_end_ms=state.window_end_ms,
            raw_fallback_provider=dependencies.raw_fallback_provider,
            max_workers=dependencies.session_analysis_max_workers,
            raw_fallback_limit=dependencies.raw_fallback_limit,
        )
    )
    return NodeExecutionResult(state=state)


def node_4_review(
    state: PostReviewGraphState,
    dependencies: BackofficeCopilotWorkflowDependencies,
) -> NodeExecutionResult:
    """Node 4. Execute session reviews without changing summary or persistence logic."""

    review_result = execute_session_reviews(
        match_id=state.match_id,
        window_start_ms=state.window_start_ms,
        window_end_ms=state.window_end_ms,
        session_analysis_list=state.session_analysis_list,
        llm_review_adapter=dependencies.llm_review_adapter,
        max_workers=dependencies.review_max_workers,
    )
    state.review_results = list(review_result.review_results)
    state.warnings.extend(review_result.warnings)
    return NodeExecutionResult(state=state)


def node_5_summary(
    state: PostReviewGraphState,
    dependencies: BackofficeCopilotWorkflowDependencies,
) -> NodeExecutionResult:
    """Node 5. Generate the run-level three-line summary only."""

    summary_result = generate_summary_text(
        match_id=state.match_id,
        window_start_ms=state.window_start_ms,
        window_end_ms=state.window_end_ms,
        review_results=state.review_results,
        session_analysis_list=state.session_analysis_list,
        summary_adapter=dependencies.summary_adapter,
    )
    state.summary_text = list(summary_result.summary_text)
    state.warnings.extend(summary_result.warnings)
    return NodeExecutionResult(state=state)


def node_6_output_delivery(
    state: PostReviewGraphState,
    dependencies: BackofficeCopilotWorkflowDependencies,
) -> NodeExecutionResult:
    """Node 6. Persist, deliver, validate, and finalize issue propagation."""

    try:
        output_result = execute_output_stage(
            repository=dependencies.repository,
            match_id=state.match_id,
            window_start_ms=state.window_start_ms,
            window_end_ms=state.window_end_ms,
            candidate_sessions=state.candidate_sessions,
            review_results=state.review_results,
            session_analysis_list=state.session_analysis_list,
            summary_text=state.summary_text,
            backend_adapter=dependencies.backend_adapter,
            export_dir=dependencies.export_dir,
            run_status="SUCCESS",
            now=dependencies.output_now,
        )
    except Exception as exc:
        validation_outcome = resolve_run_validation(
            ValidationContext(
                run_input=state.run_context,
                conflict_policy=dependencies.conflict_policy,
                output_error=exc,
                repository_ready=dependencies.repository_ready,
                upstream_warnings=tuple(state.warnings),
            )
        )
        state.warnings = list(validation_outcome.warnings)
        state.errors = list(validation_outcome.errors)
        return NodeExecutionResult(state=state, validation_outcome=validation_outcome)

    validation_outcome = resolve_run_validation(
        ValidationContext(
            run_input=state.run_context,
            conflict_policy=dependencies.conflict_policy,
            output_result=output_result,
            repository_ready=dependencies.repository_ready,
            upstream_warnings=tuple(state.warnings),
        )
    )
    output_result, validation_outcome = _finalize_output_status(
        output_result=output_result,
        validation_outcome=validation_outcome,
        dependencies=dependencies,
    )
    state.post_review_runs_row = output_result.post_review_runs_row
    state.post_review_session_result_rows = list(output_result.post_review_session_result_rows)
    state.backend_request = output_result.backend_request
    state.backend_response = output_result.backend_response
    state.warnings = list(validation_outcome.warnings)
    state.errors = list(validation_outcome.errors)
    return NodeExecutionResult(state=state, validation_outcome=validation_outcome)


def _finalize_output_status(
    *,
    output_result: OutputStageResult,
    validation_outcome: ResolvedValidationOutcome,
    dependencies: BackofficeCopilotWorkflowDependencies,
) -> tuple[OutputStageResult, ResolvedValidationOutcome]:
    """Persist the final run status after Task 9b and keep exports row-based."""

    if output_result.post_review_runs_row.status == validation_outcome.final_status:
        return output_result, validation_outcome

    updated_run_row = replace(
        output_result.post_review_runs_row,
        status=validation_outcome.final_status,
        updated_at=dependencies.output_now or datetime.now(UTC),
    )
    try:
        dependencies.repository.save_run(updated_run_row)
    except Exception as exc:
        return output_result, _merge_validation_outcome(
            validation_outcome,
            errors=(
                PipelineIssue(
                    code="run_status_persistence_failed",
                    message="Final run status could not be persisted after Task 9b validation.",
                    context={
                        "match_id": updated_run_row.match_id,
                        "resolved_status": validation_outcome.final_status,
                        "failure_reason": f"{type(exc).__name__}: {exc}",
                    },
                ),
            ),
            final_status="FAILED",
        )

    export_artifacts = output_result.export_artifacts
    export_warnings: tuple[PipelineIssue, ...] = ()
    if export_artifacts is not None or dependencies.export_dir is not None:
        try:
            export_artifacts = build_export_artifacts(
                run_row=updated_run_row,
                session_rows=output_result.post_review_session_result_rows,
                output_dir=dependencies.export_dir,
            )
        except Exception as exc:
            export_artifacts = None
            export_warnings = (
                PipelineIssue(
                    code="post_review_export_failed",
                    message="Export regeneration failed after final run status persistence completed.",
                    context={
                        "match_id": updated_run_row.match_id,
                        "failure_reason": f"{type(exc).__name__}: {exc}",
                    },
                ),
            )

    next_output_result = replace(
        output_result,
        post_review_runs_row=updated_run_row,
        export_artifacts=export_artifacts,
        warnings=output_result.warnings + export_warnings,
    )
    if not export_warnings:
        return next_output_result, validation_outcome
    return next_output_result, _merge_validation_outcome(validation_outcome, warnings=export_warnings)


def _merge_validation_outcome(
    outcome: ResolvedValidationOutcome,
    *,
    warnings: tuple[PipelineIssue, ...] = (),
    errors: tuple[PipelineIssue, ...] = (),
    final_status: RunStatus | None = None,
) -> ResolvedValidationOutcome:
    merged_warnings = outcome.warnings + warnings
    merged_errors = outcome.errors + errors
    resolved_status = final_status or outcome.final_status
    report = outcome.report
    report.summary.update(
        {
            "final_status": resolved_status,
            "final_warning_codes": [issue.code for issue in merged_warnings],
            "final_error_codes": [issue.code for issue in merged_errors],
        }
    )
    return ResolvedValidationOutcome(
        final_status=resolved_status,
        report=report,
        warnings=merged_warnings,
        errors=merged_errors,
    )


def _to_run_input(state: PostReviewGraphState) -> PostReviewRunInput:
    return PostReviewRunInput(
        match_id=state.match_id,
        window_start_ms=state.window_start_ms,
        window_end_ms=state.window_end_ms,
        limit=state.limit,
        use_raw_audit_fallback=state.use_raw_audit_fallback,
    )


__all__ = [
    "BackofficeCopilotWorkflowDependencies",
    "NodeExecutionResult",
    "node_1_input_collection",
    "node_2_candidate_selection",
    "node_3_session_analysis",
    "node_4_review",
    "node_5_summary",
    "node_6_output_delivery",
]
