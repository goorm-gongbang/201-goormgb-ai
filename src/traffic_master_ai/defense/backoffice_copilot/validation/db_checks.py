"""Thin validation orchestration layered over Task 2 storage validators."""

from __future__ import annotations

from collections.abc import Sequence

from ..core.issues import PipelineIssue
from ..core.models import PostReviewRunRecord, PostReviewSessionResultRecord
from ..storage.validators import (
    StorageValidationError,
    validate_run_record,
    validate_session_result_record,
)
from .report import ValidationCheckResult, ValidationReport


def validate_run_row(run_record: PostReviewRunRecord) -> ValidationCheckResult:
    """Wrap Task 2 run-row validation in a report-friendly interface."""

    check = ValidationCheckResult(
        check_name="db_checks.post_review_runs",
        metadata={"match_id": run_record.match_id},
    )
    try:
        validate_run_record(run_record)
    except StorageValidationError as exc:
        check.add_error(
            PipelineIssue(
                code="invalid_post_review_runs_row",
                message="post_review_runs row violates the fixed storage contract.",
                context={"match_id": run_record.match_id, "failure_reason": str(exc)},
            )
        )
    return check


def validate_session_row(session_record: PostReviewSessionResultRecord) -> ValidationCheckResult:
    """Wrap Task 2 session-row validation in a report-friendly interface."""

    check = ValidationCheckResult(
        check_name="db_checks.post_review_session_results",
        metadata={
            "match_id": session_record.match_id,
            "session_id": session_record.session_id,
        },
    )
    try:
        validate_session_result_record(session_record)
    except StorageValidationError as exc:
        check.add_error(
            PipelineIssue(
                code="invalid_post_review_session_results_row",
                message="post_review_session_results row violates the fixed storage contract.",
                context={
                    "match_id": session_record.match_id,
                    "session_id": session_record.session_id,
                    "failure_reason": str(exc),
                },
            )
        )
    return check


def validate_db_rows(
    *,
    run_record: PostReviewRunRecord | None = None,
    session_records: Sequence[PostReviewSessionResultRecord] = (),
) -> ValidationReport:
    """Collect row-level validation outcomes without reimplementing storage rules."""

    report = ValidationReport(
        summary={
            "run_row_present": run_record is not None,
            "session_row_count": len(session_records),
        }
    )
    if run_record is not None:
        report.add_check(validate_run_row(run_record))
    for session_record in session_records:
        report.add_check(validate_session_row(session_record))
    return report


__all__ = [
    "validate_db_rows",
    "validate_run_row",
    "validate_session_row",
]
