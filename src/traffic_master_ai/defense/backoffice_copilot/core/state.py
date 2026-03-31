"""Run input/context and graph state contracts for Backoffice Copilot."""

from __future__ import annotations

from dataclasses import dataclass, field

from .issues import PipelineIssue
from .models import (
    BackendRequest,
    BackendResponse,
    DefenseAuditEventRow,
    PostReviewRunRecord,
    PostReviewSessionResultRecord,
    SessionAnalysis,
    SessionReviewResult,
    SessionSummary,
)


@dataclass(slots=True, frozen=True)
class AnalysisInput:
    """Task 3 input bundle for downstream session analysis."""

    defense_audit_events: tuple[DefenseAuditEventRow, ...] = field(default_factory=tuple)
    raw_audit_available: bool = False


@dataclass(slots=True, frozen=True)
class PostReviewRunInput:
    """Fixed graph input contract from the spec."""

    match_id: str
    window_start_ms: int
    window_end_ms: int
    limit: int
    use_raw_audit_fallback: bool


@dataclass(slots=True, frozen=True)
class PostReviewRunContext:
    """Shared immutable run context used across tasks."""

    match_id: str
    window_start_ms: int
    window_end_ms: int
    limit: int
    use_raw_audit_fallback: bool

    @classmethod
    def from_input(cls, run_input: PostReviewRunInput) -> PostReviewRunContext:
        return cls(
            match_id=run_input.match_id,
            window_start_ms=run_input.window_start_ms,
            window_end_ms=run_input.window_end_ms,
            limit=run_input.limit,
            use_raw_audit_fallback=run_input.use_raw_audit_fallback,
        )


@dataclass(slots=True)
class PostReviewGraphState:
    """Minimal graph state shared by later tasks."""

    match_id: str
    window_start_ms: int
    window_end_ms: int
    limit: int
    use_raw_audit_fallback: bool
    analysis_input: AnalysisInput = field(default_factory=AnalysisInput)
    session_summaries: list[SessionSummary] = field(default_factory=list)
    candidate_sessions: list[SessionSummary] = field(default_factory=list)
    session_analysis_list: list[SessionAnalysis] = field(default_factory=list)
    review_results: list[SessionReviewResult] = field(default_factory=list)
    summary_text: list[str] = field(default_factory=list)
    post_review_runs_row: PostReviewRunRecord | None = None
    post_review_session_result_rows: list[PostReviewSessionResultRecord] = field(
        default_factory=list
    )
    backend_request: BackendRequest | None = None
    backend_response: BackendResponse | None = None
    warnings: list[PipelineIssue] = field(default_factory=list)
    errors: list[PipelineIssue] = field(default_factory=list)

    @classmethod
    def from_input(cls, run_input: PostReviewRunInput) -> PostReviewGraphState:
        return cls(
            match_id=run_input.match_id,
            window_start_ms=run_input.window_start_ms,
            window_end_ms=run_input.window_end_ms,
            limit=run_input.limit,
            use_raw_audit_fallback=run_input.use_raw_audit_fallback,
        )

    @property
    def run_context(self) -> PostReviewRunContext:
        return PostReviewRunContext(
            match_id=self.match_id,
            window_start_ms=self.window_start_ms,
            window_end_ms=self.window_end_ms,
            limit=self.limit,
            use_raw_audit_fallback=self.use_raw_audit_fallback,
        )
