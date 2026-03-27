"""Three-line window summary generation for Task 7."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from ..core.issues import PipelineIssue
from ..core.models import SessionAnalysis, SessionReviewResult
from ..storage.validators import StorageValidationError, validate_summary_text_json
from .fallback import build_fallback_summary_text
from .input_builder import build_window_summary_input

type WindowSummaryAdapter = Callable[[Mapping[str, object]], object]


class SummaryOutputValidationError(ValueError):
    """Raised when summary output violates the fixed three-line contract."""


@dataclass(slots=True, frozen=True)
class SummaryGenerationResult:
    """Task 7 output plus warning traceability for fallback usage."""

    summary_text: tuple[str, str, str]
    warnings: tuple[PipelineIssue, ...] = field(default_factory=tuple)


def generate_summary_text(
    *,
    match_id: str,
    window_start_ms: int,
    window_end_ms: int,
    review_results: tuple[SessionReviewResult, ...] | list[SessionReviewResult],
    session_analysis_list: tuple[SessionAnalysis, ...] | list[SessionAnalysis],
    summary_adapter: WindowSummaryAdapter | None = None,
) -> SummaryGenerationResult:
    """Generate a validated three-line summary with fallback."""

    summary_input = build_window_summary_input(
        match_id=match_id,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        review_results=review_results,
        session_analysis_list=session_analysis_list,
    )

    if summary_adapter is None:
        return SummaryGenerationResult(
            summary_text=build_fallback_summary_text(summary_input),
            warnings=(
                PipelineIssue(
                    code="window_summary_fallback_applied",
                    message="Template fallback summary was applied because no summary adapter was configured.",
                    context={"fallback_reason": "adapter_missing", "fallback_applied": True},
                ),
            ),
        )

    try:
        raw_output = summary_adapter(summary_input)
        summary_text = parse_summary_text(raw_output)
    except Exception as exc:
        fallback_reason = _classify_summary_failure(exc)
        return SummaryGenerationResult(
            summary_text=build_fallback_summary_text(summary_input),
            warnings=(
                PipelineIssue(
                    code="window_summary_fallback_applied",
                    message="Template fallback summary was applied after summary generation failed.",
                    context={
                        "fallback_reason": fallback_reason,
                        "fallback_applied": True,
                    },
                ),
            ),
        )

    return SummaryGenerationResult(summary_text=summary_text)


def parse_summary_text(raw_output: object) -> tuple[str, str, str]:
    """Parse a provider response into the fixed three-line summary contract."""

    if isinstance(raw_output, str):
        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise SummaryOutputValidationError("Summary output text must be valid JSON.") from exc
        return parse_summary_text(parsed)

    if isinstance(raw_output, Mapping):
        if "summary_text" not in raw_output:
            raise SummaryOutputValidationError("Summary output mapping must contain summary_text.")
        return _validate_summary_sequence(raw_output["summary_text"])

    if isinstance(raw_output, Sequence) and not isinstance(raw_output, (str, bytes, bytearray)):
        return _validate_summary_sequence(raw_output)

    raise SummaryOutputValidationError(
        "Summary output must be a sequence of strings, JSON object string, or mapping."
    )


def _validate_summary_sequence(raw_lines: object) -> tuple[str, str, str]:
    if not isinstance(raw_lines, Sequence) or isinstance(raw_lines, (str, bytes, bytearray)):
        raise SummaryOutputValidationError("summary_text must be a sequence of strings.")

    try:
        validated_lines = tuple(validate_summary_text_json(list(raw_lines)))
    except StorageValidationError as exc:
        raise SummaryOutputValidationError(str(exc)) from exc
    if len(validated_lines) != 3:
        raise SummaryOutputValidationError("summary_text must contain exactly three lines.")
    return validated_lines[0], validated_lines[1], validated_lines[2]


def _classify_summary_failure(exc: Exception) -> str:
    if isinstance(exc, SummaryOutputValidationError):
        return f"output_validation_failed:{exc}"
    if isinstance(exc, TimeoutError):
        return "adapter_timeout"
    return f"adapter_error:{type(exc).__name__}"


__all__ = [
    "SummaryGenerationResult",
    "SummaryOutputValidationError",
    "WindowSummaryAdapter",
    "generate_summary_text",
    "parse_summary_text",
]
