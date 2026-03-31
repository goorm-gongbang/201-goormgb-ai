"""DB-first row assembly and persistence orchestration for Task 8."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..core.issues import PipelineIssue
from ..core.models import (
    BackendRequest,
    BackendResponse,
    PostReviewRunRecord,
    PostReviewSessionResultRecord,
    SessionAnalysis,
    SessionReviewResult,
)
from ..storage import (
    PostReviewWriteRepository,
    validate_run_record,
    validate_session_result_record,
    validate_summary_text_json,
)
from .backend_adapter import (
    BackendDeliveryResult,
    BackendRequestAdapter,
    build_backend_request,
    deliver_backend_request,
)
from .exporter import ExportArtifacts, build_export_artifacts


@dataclass(slots=True, frozen=True)
class OutputStageResult:
    """Task 8 outputs kept explicit for graph-state integration."""

    post_review_runs_row: PostReviewRunRecord
    post_review_session_result_rows: tuple[PostReviewSessionResultRecord, ...]
    backend_request: BackendRequest | None
    backend_response: BackendResponse | None
    export_artifacts: ExportArtifacts | None = None
    warnings: tuple[PipelineIssue, ...] = field(default_factory=tuple)


def execute_output_stage(
    *,
    repository: PostReviewWriteRepository,
    match_id: str,
    window_start_ms: int,
    window_end_ms: int,
    candidate_sessions: tuple[object, ...] | list[object],
    review_results: tuple[SessionReviewResult, ...] | list[SessionReviewResult],
    session_analysis_list: tuple[SessionAnalysis, ...] | list[SessionAnalysis],
    summary_text: tuple[str, str, str] | list[str],
    backend_adapter: BackendRequestAdapter | None = None,
    export_dir: str | Path | None = None,
    run_status: str = "SUCCESS",
    now: datetime | None = None,
) -> OutputStageResult:
    """Persist rows first, then deliver suspicious payload, then emit DB-based exports."""

    run_row = build_post_review_run_record(
        match_id=match_id,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        candidate_sessions=candidate_sessions,
        review_results=review_results,
        summary_text=summary_text,
        status=run_status,
        now=now,
    )
    session_rows = build_post_review_session_result_rows(
        match_id=match_id,
        review_results=review_results,
        session_analysis_list=session_analysis_list,
        now=now,
    )

    repository.save_bundle(run_row, session_rows)

    backend_request = build_backend_request(
        match_id=match_id,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        session_rows=session_rows,
    )
    delivery_result = deliver_backend_request(
        backend_request=backend_request,
        session_rows=session_rows,
        backend_adapter=backend_adapter,
        now=now,
    )
    if delivery_result.session_rows != session_rows:
        repository.save_session_results(delivery_result.session_rows)

    export_artifacts: ExportArtifacts | None = None
    export_warnings: tuple[PipelineIssue, ...] = ()
    try:
        export_artifacts = build_export_artifacts(
            run_row=run_row,
            session_rows=delivery_result.session_rows,
            output_dir=export_dir,
        )
    except Exception as exc:
        export_warnings = (
            PipelineIssue(
                code="post_review_export_failed",
                message="Export generation failed after DB-first persistence completed.",
                context={
                    "match_id": match_id,
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                },
            ),
        )

    return OutputStageResult(
        post_review_runs_row=run_row,
        post_review_session_result_rows=delivery_result.session_rows,
        backend_request=delivery_result.backend_request,
        backend_response=delivery_result.backend_response,
        export_artifacts=export_artifacts,
        warnings=delivery_result.warnings + export_warnings,
    )


def build_post_review_run_record(
    *,
    match_id: str,
    window_start_ms: int,
    window_end_ms: int,
    candidate_sessions: tuple[object, ...] | list[object],
    review_results: tuple[SessionReviewResult, ...] | list[SessionReviewResult],
    summary_text: tuple[str, str, str] | list[str],
    status: str = "SUCCESS",
    now: datetime | None = None,
) -> PostReviewRunRecord:
    """Assemble a run-level DB row from completed Task 6/7 outputs."""

    validated_summary = validate_summary_text_json(list(summary_text))
    suspicious_count = sum(1 for result in review_results if result.review_result == "SUSPICIOUS")
    timestamp = now or datetime.now(UTC)
    run_row = PostReviewRunRecord(
        match_id=match_id,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        candidate_count=len(candidate_sessions),
        suspicious_count=suspicious_count,
        summary_text_json=validated_summary,
        status=status,
        created_at=timestamp,
        updated_at=timestamp,
    )
    validate_run_record(run_row)
    return run_row


def build_post_review_session_result_rows(
    *,
    match_id: str,
    review_results: tuple[SessionReviewResult, ...] | list[SessionReviewResult],
    session_analysis_list: tuple[SessionAnalysis, ...] | list[SessionAnalysis],
    now: datetime | None = None,
) -> tuple[PostReviewSessionResultRecord, ...]:
    """Assemble session-level DB rows from Task 5 and Task 6 outputs."""

    analysis_by_session_id = {analysis.session_id: analysis for analysis in session_analysis_list}
    timestamp = now or datetime.now(UTC)
    session_rows: list[PostReviewSessionResultRecord] = []

    for review_result in review_results:
        session_analysis = analysis_by_session_id.get(review_result.session_id)
        if session_analysis is None:
            raise ValueError(
                f"session_analysis_list is missing session_id={review_result.session_id!r} required for persistence."
            )
        row = PostReviewSessionResultRecord(
            match_id=match_id,
            session_id=review_result.session_id,
            review_result=review_result.review_result,
            evidence_summary=review_result.evidence_summary,
            session_analysis_json=session_analysis,
            backend_delivery_status="PENDING",
            created_at=timestamp,
            updated_at=timestamp,
        )
        validate_session_result_record(row)
        session_rows.append(row)

    return tuple(session_rows)


__all__ = [
    "OutputStageResult",
    "build_post_review_run_record",
    "build_post_review_session_result_rows",
    "execute_output_stage",
]
