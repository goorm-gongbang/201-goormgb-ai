"""Final run-status resolution for Task 9b."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.issues import PipelineIssue
from ..core.models import RunStatus
from .checks import ValidationContext, run_completed_output_checks
from .report import ValidationReport


@dataclass(slots=True, frozen=True)
class ResolvedValidationOutcome:
    """Finalized validation output consumed by later workflow wiring."""

    final_status: RunStatus
    report: ValidationReport
    warnings: tuple[PipelineIssue, ...]
    errors: tuple[PipelineIssue, ...]


def resolve_run_validation(context: ValidationContext) -> ResolvedValidationOutcome:
    """Resolve SUCCESS/PARTIAL_SUCCESS/FAILED from Task 8 outputs and Task 9a checks."""

    report = run_completed_output_checks(context)
    finalized_warnings = _deduplicate_issues(report.warnings)
    finalized_errors = _deduplicate_issues(report.errors)
    final_status: RunStatus
    if finalized_errors:
        final_status = "FAILED"
    elif any(check.status_impact == "partial" and check.warnings for check in report.checks):
        final_status = "PARTIAL_SUCCESS"
    else:
        final_status = "SUCCESS"

    report.summary.update(
        {
            "final_status": final_status,
            "final_warning_codes": [issue.code for issue in finalized_warnings],
            "final_error_codes": [issue.code for issue in finalized_errors],
        }
    )
    return ResolvedValidationOutcome(
        final_status=final_status,
        report=report,
        warnings=tuple(finalized_warnings),
        errors=tuple(finalized_errors),
    )


def _deduplicate_issues(issues: list[PipelineIssue]) -> list[PipelineIssue]:
    deduplicated: list[PipelineIssue] = []
    seen: set[tuple[str, str, object]] = set()
    for issue in issues:
        context_key = _normalize_for_hash(issue.context)
        issue_key = (issue.code, issue.message, context_key)
        if issue_key in seen:
            continue
        seen.add(issue_key)
        deduplicated.append(issue)
    return deduplicated


def _normalize_for_hash(value: object) -> object:
    if isinstance(value, dict):
        return tuple(sorted((str(key), _normalize_for_hash(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_normalize_for_hash(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_normalize_for_hash(item) for item in value)
    return value


__all__ = ["ResolvedValidationOutcome", "resolve_run_validation"]
