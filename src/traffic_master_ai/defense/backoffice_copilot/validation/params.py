"""Minimal graph-input validation skeleton for Task 9a."""

from __future__ import annotations

from collections.abc import Mapping

from ..core.issues import PipelineIssue
from ..core.state import PostReviewRunContext, PostReviewRunInput
from .report import ValidationCheckResult


def validate_run_input_params(
    run_input: PostReviewRunInput | PostReviewRunContext | Mapping[str, object],
) -> ValidationCheckResult:
    """Validate fixed graph input fields without interpreting runtime outcomes."""

    payload = _normalize_run_input(run_input)
    check = ValidationCheckResult(
        check_name="params.run_input",
        metadata={"validated_fields": tuple(payload.keys())},
    )

    match_id = payload.get("match_id")
    if not isinstance(match_id, str) or not match_id:
        check.add_error(
            PipelineIssue(
                code="invalid_run_input_match_id",
                message="match_id must be a non-empty string.",
            )
        )

    window_start_ms = payload.get("window_start_ms")
    if not _is_plain_int(window_start_ms):
        check.add_error(
            PipelineIssue(
                code="invalid_run_input_window_start_ms",
                message="window_start_ms must be an int.",
            )
        )

    window_end_ms = payload.get("window_end_ms")
    if not _is_plain_int(window_end_ms):
        check.add_error(
            PipelineIssue(
                code="invalid_run_input_window_end_ms",
                message="window_end_ms must be an int.",
            )
        )

    if _is_plain_int(window_start_ms) and _is_plain_int(window_end_ms) and window_end_ms < window_start_ms:
        check.add_error(
            PipelineIssue(
                code="invalid_run_input_window_range",
                message="window_end_ms must be greater than or equal to window_start_ms.",
                context={
                    "window_start_ms": window_start_ms,
                    "window_end_ms": window_end_ms,
                },
            )
        )

    limit = payload.get("limit")
    if not _is_plain_int(limit):
        check.add_error(
            PipelineIssue(
                code="invalid_run_input_limit_type",
                message="limit must be an int.",
            )
        )
    elif limit <= 0:
        check.add_error(
            PipelineIssue(
                code="invalid_run_input_limit_range",
                message="limit must be greater than 0.",
                context={"limit": limit},
            )
        )

    use_raw_audit_fallback = payload.get("use_raw_audit_fallback")
    if not isinstance(use_raw_audit_fallback, bool):
        check.add_error(
            PipelineIssue(
                code="invalid_run_input_use_raw_audit_fallback",
                message="use_raw_audit_fallback must be a bool.",
            )
        )

    return check


def _normalize_run_input(
    run_input: PostReviewRunInput | PostReviewRunContext | Mapping[str, object],
) -> Mapping[str, object]:
    if isinstance(run_input, (PostReviewRunInput, PostReviewRunContext)):
        return {
            "match_id": run_input.match_id,
            "window_start_ms": run_input.window_start_ms,
            "window_end_ms": run_input.window_end_ms,
            "limit": run_input.limit,
            "use_raw_audit_fallback": run_input.use_raw_audit_fallback,
        }
    if isinstance(run_input, Mapping):
        return run_input
    raise TypeError("run_input must be PostReviewRunInput, PostReviewRunContext, or a mapping.")


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


__all__ = ["validate_run_input_params"]
