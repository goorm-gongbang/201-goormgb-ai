"""LLM output parser and validator for Task 6."""

from __future__ import annotations

import json
from typing import Mapping

from ..core.models import LlmReviewOutput


class LlmOutputValidationError(ValueError):
    """Raised when an LLM response violates the fixed output contract."""


def parse_llm_review_output(raw_output: object) -> LlmReviewOutput:
    """Parse and validate a provider response into the fixed DTO."""

    if isinstance(raw_output, LlmReviewOutput):
        payload: Mapping[str, object] = {
            "review_result": raw_output.review_result,
            "evidence_summary": raw_output.evidence_summary,
        }
    elif isinstance(raw_output, str):
        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise LlmOutputValidationError("LLM output must be valid JSON when returned as text.") from exc
        if not isinstance(parsed, Mapping):
            raise LlmOutputValidationError("LLM output JSON must decode to an object.")
        payload = parsed
    elif isinstance(raw_output, Mapping):
        payload = raw_output
    else:
        raise LlmOutputValidationError("LLM output must be a mapping, JSON object string, or LlmReviewOutput.")

    review_result = payload.get("review_result")
    if review_result not in {"NORMAL", "SUSPICIOUS"}:
        raise LlmOutputValidationError("review_result must be NORMAL or SUSPICIOUS.")

    evidence_summary = payload.get("evidence_summary")
    if not isinstance(evidence_summary, str) or not evidence_summary.strip():
        raise LlmOutputValidationError("evidence_summary must be a non-empty string.")

    return LlmReviewOutput(
        review_result=review_result,
        evidence_summary=evidence_summary.strip(),
    )


__all__ = ["LlmOutputValidationError", "parse_llm_review_output"]
