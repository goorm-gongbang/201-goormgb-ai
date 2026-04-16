"""Window summary input assembly for Task 7."""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..core.models import SessionAnalysis, SessionReviewResult


def build_window_summary_input(
    *,
    match_id: str,
    window_start_ms: int,
    window_end_ms: int,
    review_results: tuple[SessionReviewResult, ...] | list[SessionReviewResult],
    session_analysis_list: tuple[SessionAnalysis, ...] | list[SessionAnalysis],
) -> dict[str, object]:
    """Assemble a compact, run-level summary input from prior task outputs."""

    review_list = list(review_results)
    analysis_list = list(session_analysis_list)
    suspicious_session_ids = {
        result.session_id for result in review_list if result.review_result == "SUSPICIOUS"
    }
    suspicious_analyses = [
        analysis for analysis in analysis_list if analysis.session_id in suspicious_session_ids
    ]

    signal_counter: Counter[str] = Counter()
    for analysis in suspicious_analyses:
        signal_counter.update(signal for signal in analysis.suspicious_signals if signal)

    top_signals = [
        {"signal": signal, "count": count}
        for signal, count in signal_counter.most_common(3)
    ]

    throttle_total = sum(a.throttle_event_count for a in analysis_list)
    challenge_fail_total = sum(a.vqa_fail_count for a in analysis_list)
    tier_breakdown = dict(Counter(a.latest_tier for a in analysis_list))
    action_breakdown = dict(Counter(a.latest_action for a in analysis_list))

    return {
        "match_id": match_id,
        "window_start_ms": window_start_ms,
        "window_end_ms": window_end_ms,
        "candidate_count": len(analysis_list),
        "reviewed_count": len(review_list),
        "suspicious_count": sum(
            1 for result in review_list if result.review_result == "SUSPICIOUS"
        ),
        "normal_count": sum(1 for result in review_list if result.review_result == "NORMAL"),
        "needs_raw_fallback_count": sum(
            1 for analysis in analysis_list if analysis.needs_raw_fallback
        ),
        "top_signals": top_signals,
        "throttle_total": throttle_total,
        "challenge_fail_total": challenge_fail_total,
        "tier_breakdown": tier_breakdown,
        "action_breakdown": action_breakdown,
        "session_results": [
            {
                "session_id": result.session_id,
                "review_result": result.review_result,
                "evidence_summary": result.evidence_summary,
            }
            for result in review_list
        ],
    }


__all__ = ["build_window_summary_input"]
