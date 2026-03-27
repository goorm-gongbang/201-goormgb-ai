"""LlmReviewInput builders for Task 6."""

from __future__ import annotations

from ..core.models import LlmReviewInput, SessionAnalysis


def build_llm_review_input(
    *,
    match_id: str,
    window_start_ms: int,
    window_end_ms: int,
    session_analysis: SessionAnalysis,
) -> LlmReviewInput:
    """Build one fixed LLM input DTO from a SessionAnalysis."""

    return LlmReviewInput(
        match_id=match_id,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        session_analysis=session_analysis,
    )


def build_llm_review_inputs(
    *,
    match_id: str,
    window_start_ms: int,
    window_end_ms: int,
    session_analysis_list: tuple[SessionAnalysis, ...] | list[SessionAnalysis],
) -> tuple[LlmReviewInput, ...]:
    """Build LLM inputs in the same order as the session analyses."""

    return tuple(
        build_llm_review_input(
            match_id=match_id,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            session_analysis=session_analysis,
        )
        for session_analysis in session_analysis_list
    )


__all__ = ["build_llm_review_input", "build_llm_review_inputs"]
