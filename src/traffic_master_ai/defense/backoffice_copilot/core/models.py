"""Shared in-memory DTOs for Backoffice Copilot post-review tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

type ReviewResult = Literal["NORMAL", "SUSPICIOUS"]
type RunStatus = Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
type BackendDeliveryStatus = Literal["PENDING", "SENT", "FAILED"]

DEFAULT_REVIEW_LABELS: tuple[ReviewResult, ReviewResult] = ("NORMAL", "SUSPICIOUS")
DEFAULT_REVIEW_REQUIRED_FIELDS: tuple[str, str] = ("review_result", "evidence_summary")


@dataclass(slots=True)
class DefenseAuditEventRow:
    """Minimal raw row contract.

    Semantic mapping outputs must not be mixed into this DTO.
    """

    ts_ms: int
    trace_id: str
    session_id: str
    event_type: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class SessionSummary:
    """In-memory summary used by candidate extraction."""

    session_id: str
    seen_t1: bool
    seen_t2: bool
    block_event_count: int
    vqa_fail_count: int
    throttle_event_count: int
    latest_flow_state: str
    latest_action: str
    latest_tier: str
    terminal_outcome: str
    challenge_issue_count: int = 0
    challenge_verified_count: int = 0


@dataclass(slots=True)
class SessionAnalysis:
    """In-memory session analysis assembled after candidate extraction."""

    session_id: str
    latest_flow_state: str
    latest_action: str
    latest_tier: str
    terminal_outcome: str
    seen_t1: bool
    seen_t2: bool
    vqa_fail_count: int
    throttle_event_count: int
    suspicious_signals: list[str] = field(default_factory=list)
    timeline_summary: list[str] = field(default_factory=list)
    needs_raw_fallback: bool = False


@dataclass(slots=True)
class LlmReviewTask:
    """Fixed task envelope for per-session review prompts."""

    labels: tuple[ReviewResult, ...] = DEFAULT_REVIEW_LABELS
    required_fields: tuple[str, ...] = DEFAULT_REVIEW_REQUIRED_FIELDS


@dataclass(slots=True)
class LlmReviewInput:
    """LLM input DTO for one session analysis."""

    match_id: str
    window_start_ms: int
    window_end_ms: int
    session_analysis: SessionAnalysis
    task: LlmReviewTask = field(default_factory=LlmReviewTask)


@dataclass(slots=True)
class LlmReviewOutput:
    """LLM output DTO for one session."""

    review_result: ReviewResult
    evidence_summary: str


@dataclass(slots=True)
class SessionReviewResult:
    """Session-scoped review output stored in graph state."""

    session_id: str
    review_result: ReviewResult
    evidence_summary: str


@dataclass(slots=True)
class BackendCandidate:
    """Suspicious-only backend candidate item."""

    session_id: str
    review_result: ReviewResult
    reason_summary: str


@dataclass(slots=True)
class BackendRequest:
    """Backend adapter request DTO."""

    match_id: str
    window_start_ms: int
    window_end_ms: int
    suspicious_count: int
    candidates: list[BackendCandidate] = field(default_factory=list)


@dataclass(slots=True)
class BackendResponse:
    """Backend adapter response DTO."""

    match_id: str
    accepted_count: int
    rejected_count: int
    status: str
    received_at: str


@dataclass(slots=True)
class PostReviewRunRecord:
    """Thin run-level record DTO for Node 6 outputs."""

    match_id: str
    window_start_ms: int
    window_end_ms: int
    candidate_count: int
    suspicious_count: int
    summary_text_json: list[str]
    status: RunStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class PostReviewSessionResultRecord:
    """Thin session-level record DTO for Node 6 outputs."""

    match_id: str
    session_id: str
    review_result: ReviewResult
    evidence_summary: str
    session_analysis_json: SessionAnalysis
    backend_delivery_status: BackendDeliveryStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None
