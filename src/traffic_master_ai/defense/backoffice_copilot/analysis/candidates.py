"""Session summary aggregation and candidate hard filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..core.issues import PipelineIssue
from ..core.models import SessionSummary
from ..core.state import AnalysisInput
from ..ingest.interpreter import InterpretedAuditEvent, interpret_analysis_input

_DEFAULT_FLOW_STATE = "UNKNOWN"
_DEFAULT_ACTION = "UNKNOWN"
_DEFAULT_TIER = "UNKNOWN"
_DEFAULT_TERMINAL_OUTCOME = "UNKNOWN"


@dataclass(slots=True, frozen=True)
class CandidateSelectionResult:
    """Task 4 outputs kept separate for later nodes."""

    session_summaries: tuple[SessionSummary, ...] = field(default_factory=tuple)
    candidate_sessions: tuple[SessionSummary, ...] = field(default_factory=tuple)
    warnings: tuple[PipelineIssue, ...] = field(default_factory=tuple)


def build_candidate_selection(analysis_input: AnalysisInput) -> CandidateSelectionResult:
    """Aggregate session summaries and derive candidate sessions."""

    session_summaries = summarize_sessions(analysis_input)
    candidate_sessions = tuple(
        summary for summary in session_summaries if is_candidate_session(summary)
    )
    warnings: list[PipelineIssue] = []
    if not candidate_sessions:
        warnings.append(
            PipelineIssue(
                code="candidate_sessions_empty",
                message="No sessions matched the Task 4 candidate hard filter.",
                context={
                    "session_summary_count": len(session_summaries),
                    "raw_audit_available": analysis_input.raw_audit_available,
                },
            )
        )

    return CandidateSelectionResult(
        session_summaries=session_summaries,
        candidate_sessions=candidate_sessions,
        warnings=tuple(warnings),
    )


def summarize_sessions(analysis_input: AnalysisInput) -> tuple[SessionSummary, ...]:
    """Summarize interpreted events by session_id in stable input order."""

    interpreted_events = interpret_analysis_input(analysis_input)
    grouped_events: dict[str, list[tuple[int, InterpretedAuditEvent]]] = {}
    session_order: list[str] = []

    for index, interpreted in enumerate(interpreted_events):
        session_id = interpreted.row.session_id
        if not session_id:
            continue
        if session_id not in grouped_events:
            grouped_events[session_id] = []
            session_order.append(session_id)
        grouped_events[session_id].append((index, interpreted))

    return tuple(
        _summarize_session(session_id=session_id, events=grouped_events[session_id])
        for session_id in session_order
    )


def is_candidate_session(summary: SessionSummary) -> bool:
    """Hard filter for Task 4 candidate sessions.

    Exclusions are evaluated first and are non-negotiable:
    - any block event recorded in the session
    - latest resolved action is BLOCK
    - latest risk tier is T3 (already handled at the highest severity)
    - session terminated as BLOCKED

    Inclusion requires at least one signal of interest:
    1. Tier signal: T1 or T2 was observed during the session, OR
    2. Protection-context signal: the defense system already applied a throttle
       or the session had a challenge failure — both indicate the session was
       flagged by runtime even when tier data in the audit log is sparse.

    This widens candidate coverage so that sessions where runtime acted
    (throttle / challenge) but tier fields are missing or ambiguous are still
    reviewed by the LLM, increasing candidate_count without loosening
    the safety exclusions.
    """
    # --- safety exclusions (always applied first) ---
    if summary.block_event_count > 0:
        return False
    if summary.latest_action == "BLOCK":
        return False
    if summary.latest_tier == "T3":
        return False
    if summary.terminal_outcome == "BLOCKED":
        return False

    # --- inclusion: tier signal (original path) ---
    has_tier_signal = summary.seen_t1 or summary.seen_t2

    # --- inclusion: protection-context signal (widened path) ---
    # A session that was throttled or failed a challenge has already been
    # identified as risky by the runtime engine; it deserves LLM review
    # regardless of whether a T1/T2 tier stamp is present in the audit window.
    has_protection_context = (
        summary.throttle_event_count >= 1
        or summary.vqa_fail_count >= 1
        or summary.latest_action == "THROTTLE"
    )

    return has_tier_signal or has_protection_context


def _summarize_session(
    *,
    session_id: str,
    events: list[tuple[int, InterpretedAuditEvent]],
) -> SessionSummary:
    seen_t1 = False
    seen_t2 = False
    block_event_count = 0
    vqa_fail_count = 0
    throttle_event_count = 0
    latest_flow_state = _DEFAULT_FLOW_STATE
    latest_action = _DEFAULT_ACTION
    latest_tier = _DEFAULT_TIER
    terminal_outcome = _DEFAULT_TERMINAL_OUTCOME
    latest_semantic_rank = (-1, -1)

    for index, interpreted in events:
        semantics = interpreted.semantics
        if semantics.latest_tier == "T1":
            seen_t1 = True
        elif semantics.latest_tier == "T2":
            seen_t2 = True

        if interpreted.row.event_type == "DEF_BLOCK_ENFORCED":
            block_event_count += 1
        if interpreted.row.event_type == "DEF_THROTTLE_APPLIED":
            throttle_event_count += 1
        if interpreted.row.event_type == "S3_CHALLENGE_RESULT" and _is_vqa_fail(interpreted):
            vqa_fail_count += 1

        if interpreted.usage == "UNUSED":
            continue

        candidate_rank = (interpreted.row.ts_ms, index)
        if candidate_rank < latest_semantic_rank:
            continue
        latest_semantic_rank = candidate_rank
        if semantics.latest_flow_state is not None:
            latest_flow_state = semantics.latest_flow_state
        if semantics.latest_action is not None:
            latest_action = semantics.latest_action
        if semantics.latest_tier is not None:
            latest_tier = semantics.latest_tier
        if semantics.terminal_outcome is not None:
            terminal_outcome = semantics.terminal_outcome

    return SessionSummary(
        session_id=session_id,
        seen_t1=seen_t1,
        seen_t2=seen_t2,
        block_event_count=block_event_count,
        vqa_fail_count=vqa_fail_count,
        throttle_event_count=throttle_event_count,
        latest_flow_state=latest_flow_state,
        latest_action=latest_action,
        latest_tier=latest_tier,
        terminal_outcome=terminal_outcome,
    )


def _is_vqa_fail(interpreted: InterpretedAuditEvent) -> bool:
    payload = interpreted.row.payload
    challenge = _nested_mapping(payload, "challenge")
    result_block = _nested_mapping(payload, "result")
    challenge_result = _read_string(challenge, "result")
    result_status = _read_string(result_block, "status")
    if challenge_result and challenge_result not in {"PASS", "OK"}:
        return True
    if result_status == "FAIL":
        return True
    return interpreted.semantics.reason_code is not None


def _nested_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return value
    return {}


def _read_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    return None


__all__ = [
    "CandidateSelectionResult",
    "build_candidate_selection",
    "is_candidate_session",
    "summarize_sessions",
]
