"""Session review executor for Task 6."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

LOGGER = logging.getLogger(__name__)

from ..core.issues import PipelineIssue
from ..core.models import LlmReviewInput, SessionAnalysis, SessionReviewResult
from .fallback import build_fallback_review_result
from .input_builder import build_llm_review_input
from .output_parser import LlmOutputValidationError, parse_llm_review_output

type LlmReviewAdapter = Callable[[LlmReviewInput], object]


@dataclass(slots=True, frozen=True)
class ReviewExecutionResult:
    """Task 6 outputs plus warning traceability for fallback usage."""

    review_results: tuple[SessionReviewResult, ...] = field(default_factory=tuple)
    warnings: tuple[PipelineIssue, ...] = field(default_factory=tuple)


def execute_session_reviews(
    *,
    match_id: str,
    window_start_ms: int,
    window_end_ms: int,
    session_analysis_list: tuple[SessionAnalysis, ...] | list[SessionAnalysis],
    llm_review_adapter: LlmReviewAdapter | None = None,
    max_workers: int = 4,
) -> ReviewExecutionResult:
    """Execute per-session reviews with bounded concurrency and deterministic ordering."""

    analyses = list(session_analysis_list)
    if not analyses:
        return ReviewExecutionResult()

    if max_workers <= 1 or len(analyses) == 1:
        results = [
            _execute_one_review(
                match_id=match_id,
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
                session_analysis=session_analysis,
                llm_review_adapter=llm_review_adapter,
            )
            for session_analysis in analyses
        ]
    else:
        ordered_results: list[tuple[SessionReviewResult, PipelineIssue | None] | None] = [None] * len(analyses)
        with ThreadPoolExecutor(max_workers=min(max_workers, len(analyses))) as executor:
            futures = {
                executor.submit(
                    _execute_one_review,
                    match_id=match_id,
                    window_start_ms=window_start_ms,
                    window_end_ms=window_end_ms,
                    session_analysis=session_analysis,
                    llm_review_adapter=llm_review_adapter,
                ): index
                for index, session_analysis in enumerate(analyses)
            }
            for future, index in futures.items():
                ordered_results[index] = future.result()
        results = [result for result in ordered_results if result is not None]

    review_results = tuple(result[0] for result in results)
    warnings = tuple(result[1] for result in results if result[1] is not None)
    return ReviewExecutionResult(review_results=review_results, warnings=warnings)


def _execute_one_review(
    *,
    match_id: str,
    window_start_ms: int,
    window_end_ms: int,
    session_analysis: SessionAnalysis,
    llm_review_adapter: LlmReviewAdapter | None,
) -> tuple[SessionReviewResult, PipelineIssue | None]:
    llm_input = build_llm_review_input(
        match_id=match_id,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        session_analysis=session_analysis,
    )

    if llm_review_adapter is None:
        LOGGER.warning(
            "post_review_review_fallback_applied match_id=%s window_start_ms=%s "
            "window_end_ms=%s session_id=%s fallback_reason=adapter_missing "
            "fallback_mode=deterministic degraded=true",
            match_id,
            window_start_ms,
            window_end_ms,
            session_analysis.session_id,
        )
        return build_fallback_review_result(session_analysis, reason="adapter_missing")

    try:
        raw_output = llm_review_adapter(llm_input)
        parsed_output = parse_llm_review_output(raw_output)
    except TimeoutError:
        fallback_reason = "adapter_timeout"
        LOGGER.warning(
            "post_review_review_fallback_applied match_id=%s window_start_ms=%s "
            "window_end_ms=%s session_id=%s fallback_reason=%s "
            "fallback_mode=deterministic degraded=true",
            match_id,
            window_start_ms,
            window_end_ms,
            session_analysis.session_id,
            fallback_reason,
        )
        return build_fallback_review_result(session_analysis, reason=fallback_reason)
    except LlmOutputValidationError as exc:
        fallback_reason = f"output_validation_failed:{exc}"
        LOGGER.warning(
            "post_review_review_fallback_applied match_id=%s window_start_ms=%s "
            "window_end_ms=%s session_id=%s fallback_reason=%s "
            "fallback_mode=deterministic degraded=true",
            match_id,
            window_start_ms,
            window_end_ms,
            session_analysis.session_id,
            fallback_reason,
        )
        return build_fallback_review_result(session_analysis, reason=fallback_reason)
    except Exception as exc:
        fallback_reason = f"adapter_error:{type(exc).__name__}"
        LOGGER.warning(
            "post_review_review_fallback_applied match_id=%s window_start_ms=%s "
            "window_end_ms=%s session_id=%s fallback_reason=%s "
            "fallback_mode=deterministic degraded=true",
            match_id,
            window_start_ms,
            window_end_ms,
            session_analysis.session_id,
            fallback_reason,
        )
        return build_fallback_review_result(session_analysis, reason=fallback_reason)

    return (
        SessionReviewResult(
            session_id=session_analysis.session_id,
            review_result=parsed_output.review_result,
            evidence_summary=parsed_output.evidence_summary,
        ),
        None,
    )


__all__ = ["LlmReviewAdapter", "ReviewExecutionResult", "execute_session_reviews"]
