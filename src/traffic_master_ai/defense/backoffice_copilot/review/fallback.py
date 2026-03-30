"""Rule-based review fallback for Task 6."""

from __future__ import annotations

from ..core.issues import PipelineIssue
from ..core.models import SessionAnalysis, SessionReviewResult


def build_fallback_review_result(
    session_analysis: SessionAnalysis,
    *,
    reason: str,
) -> tuple[SessionReviewResult, PipelineIssue]:
    """Build a per-session fallback result plus a warning record."""

    review_result = _resolve_fallback_label(session_analysis)
    evidence_summary = _build_fallback_evidence_summary(session_analysis, review_result)
    return (
        SessionReviewResult(
            session_id=session_analysis.session_id,
            review_result=review_result,
            evidence_summary=evidence_summary,
        ),
        PipelineIssue(
            code="llm_review_fallback_applied",
            message="Rule-based review fallback was applied for this session.",
            context={
                "session_id": session_analysis.session_id,
                "fallback_reason": reason,
                "fallback_applied": True,
            },
        ),
    )


def _resolve_fallback_label(session_analysis: SessionAnalysis) -> str:
    if session_analysis.seen_t2:
        return "SUSPICIOUS"
    if session_analysis.vqa_fail_count > 0:
        return "SUSPICIOUS"
    if session_analysis.throttle_event_count > 0:
        return "SUSPICIOUS"
    if session_analysis.latest_action == "THROTTLE":
        return "SUSPICIOUS"
    return "NORMAL"


def _build_fallback_evidence_summary(
    session_analysis: SessionAnalysis,
    review_result: str,
) -> str:
    reasons: list[str] = []
    if session_analysis.seen_t2:
        reasons.append("T2 trace was observed")
    if session_analysis.vqa_fail_count > 0:
        reasons.append("VQA failures were observed")
    if session_analysis.throttle_event_count > 0:
        reasons.append("throttle events were applied")
    if session_analysis.latest_action == "THROTTLE":
        reasons.append("the latest runtime action remained THROTTLE")

    if reasons:
        joined_reasons = ", ".join(reasons)
        if review_result == "SUSPICIOUS":
            return f"Rule-based fallback marked this session as SUSPICIOUS because {joined_reasons}."
        return f"Rule-based fallback kept this session NORMAL despite observed context: {joined_reasons}."

    if review_result == "SUSPICIOUS":
        return "Rule-based fallback marked this session as SUSPICIOUS based on session analysis signals."
    return "Rule-based fallback marked this session as NORMAL because no suspicious session-analysis signals were present."


__all__ = ["build_fallback_review_result"]
