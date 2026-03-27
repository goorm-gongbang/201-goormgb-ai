"""Task 9b validation checks built on top of the Task 9a skeleton."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from io import StringIO
from typing import Mapping

from ..core.issues import PipelineIssue
from ..core.models import PostReviewSessionResultRecord
from ..core.state import PostReviewRunContext, PostReviewRunInput
from ..output.exporter import ExportArtifacts
from ..output.persistence import OutputStageResult
from ..storage.repository import PkConflictPolicy
from .allowed_values import validate_allowed_value
from .db_checks import validate_db_rows
from .params import validate_run_input_params
from .report import ValidationCheckResult, ValidationReport

type RunInputLike = PostReviewRunInput | PostReviewRunContext | Mapping[str, object]

_RESOLVED_CHECKS = {
    "final_run_status_resolution",
    "stage_outcome_interpretation",
    "backend_delivery_outcome_interpretation",
    "export_policy_finalization",
}


@dataclass(slots=True, frozen=True)
class ValidationContext:
    """Task 9b validation inputs derived from Task 8 outputs."""

    run_input: RunInputLike
    conflict_policy: PkConflictPolicy | str | None
    output_result: OutputStageResult | None = None
    output_error: Exception | None = None
    repository_ready: bool = True
    upstream_warnings: tuple[PipelineIssue, ...] = field(default_factory=tuple)


def run_completed_output_checks(context: ValidationContext) -> ValidationReport:
    """Finalize Task 9a skeleton checks against Task 8 output-stage results."""

    report = ValidationReport(
        summary={
            "repository_ready": context.repository_ready,
            "has_output_result": context.output_result is not None,
            "has_output_error": context.output_error is not None,
        }
    )
    report.add_check(validate_run_input_params(context.run_input))
    report.add_check(
        validate_pre_run_checks(
            conflict_policy=context.conflict_policy,
            repository_ready=context.repository_ready,
        )
    )

    if context.output_error is not None:
        report.add_check(validate_db_failure(context.output_error))
        return _finalize_report_metadata(report)

    if context.output_result is None:
        report.add_check(
            _error_check(
                check_name="stages.output_presence",
                code="missing_output_stage_result",
                message="Task 8 output result is required to finalize run validation.",
                context={},
            )
        )
        return _finalize_report_metadata(report)

    output_result = context.output_result
    report.merge(
        validate_db_rows(
            run_record=output_result.post_review_runs_row,
            session_records=output_result.post_review_session_result_rows,
        )
    )
    report.add_check(validate_db_stage(output_result))
    report.add_check(validate_backend_stage(output_result))
    report.add_check(validate_export_stage(output_result))
    report.add_check(
        validate_fallback_stage(
            session_rows=output_result.post_review_session_result_rows,
            stage_warnings=output_result.warnings,
            upstream_warnings=context.upstream_warnings,
        )
    )
    return _finalize_report_metadata(report)


def validate_pre_run_checks(
    *,
    conflict_policy: PkConflictPolicy | str | None,
    repository_ready: bool,
) -> ValidationCheckResult:
    """Complete the pre-run checks left open in Task 9a."""

    check = ValidationCheckResult(check_name="pre_run.configuration")
    if not repository_ready:
        check.add_error(
            PipelineIssue(
                code="repository_not_ready",
                message="PostgreSQL repository must be ready before run validation can succeed.",
            )
        )
    if conflict_policy is None:
        check.add_error(
            PipelineIssue(
                code="missing_pk_conflict_policy",
                message="PK conflict policy must be declared before execution.",
            )
        )
        return check

    policy_value = conflict_policy.value if isinstance(conflict_policy, PkConflictPolicy) else conflict_policy
    if policy_value not in {policy.value for policy in PkConflictPolicy}:
        check.add_error(
            PipelineIssue(
                code="invalid_pk_conflict_policy",
                message="PK conflict policy must be fail_fast or upsert.",
                context={"received_value": policy_value},
            )
        )
    else:
        check.metadata["conflict_policy"] = policy_value
    return check


def validate_db_failure(output_error: Exception) -> ValidationCheckResult:
    """Treat DB-stage failure as a fatal run failure."""

    check = ValidationCheckResult(check_name="stages.db_persistence")
    check.add_error(
        PipelineIssue(
            code="db_persistence_failed",
            message="DB-first persistence failed and the run must be marked FAILED.",
            context={"failure_reason": f"{type(output_error).__name__}: {output_error}"},
        )
    )
    return check


def validate_db_stage(output_result: OutputStageResult) -> ValidationCheckResult:
    """Validate run/session row consistency after Task 8 row assembly."""

    run_row = output_result.post_review_runs_row
    session_rows = output_result.post_review_session_result_rows
    check = ValidationCheckResult(
        check_name="stages.db_persistence",
        metadata={
            "match_id": run_row.match_id,
            "session_row_count": len(session_rows),
        },
    )

    suspicious_row_count = sum(1 for row in session_rows if row.review_result == "SUSPICIOUS")
    if run_row.suspicious_count != suspicious_row_count:
        check.add_error(
            PipelineIssue(
                code="run_row_suspicious_count_mismatch",
                message="Run row suspicious_count must match the number of SUSPICIOUS session rows.",
                context={
                    "match_id": run_row.match_id,
                    "run_row_suspicious_count": run_row.suspicious_count,
                    "session_row_suspicious_count": suspicious_row_count,
                },
            )
        )

    if run_row.candidate_count < run_row.suspicious_count:
        check.add_error(
            PipelineIssue(
                code="run_row_candidate_count_mismatch",
                message="candidate_count must be greater than or equal to suspicious_count.",
                context={
                    "match_id": run_row.match_id,
                    "candidate_count": run_row.candidate_count,
                    "suspicious_count": run_row.suspicious_count,
                },
            )
        )

    for row in session_rows:
        if row.match_id != run_row.match_id:
            check.add_error(
                PipelineIssue(
                    code="session_row_match_id_mismatch",
                    message="Every session row must use the same match_id as the run row.",
                    context={
                        "run_match_id": run_row.match_id,
                        "session_id": row.session_id,
                        "session_match_id": row.match_id,
                    },
                )
            )
    return check


def validate_backend_stage(output_result: OutputStageResult) -> ValidationCheckResult:
    """Validate suspicious-only delivery and backend_delivery_status updates."""

    session_rows = output_result.post_review_session_result_rows
    suspicious_rows = [row for row in session_rows if row.review_result == "SUSPICIOUS"]
    normal_rows = [row for row in session_rows if row.review_result == "NORMAL"]
    backend_request = output_result.backend_request
    backend_response = output_result.backend_response
    stage_warnings = [warning for warning in output_result.warnings if warning.code == "backend_delivery_failed"]
    check = ValidationCheckResult(
        check_name="stages.backend_delivery",
        status_impact="partial" if stage_warnings else "none",
        metadata={"suspicious_row_count": len(suspicious_rows)},
    )

    if backend_request is None:
        if suspicious_rows:
            check.add_error(
                PipelineIssue(
                    code="missing_backend_request_for_suspicious_rows",
                    message="SUSPICIOUS session rows require a backend request DTO.",
                    context={"suspicious_row_count": len(suspicious_rows)},
                )
            )
        if backend_response is not None:
            check.add_error(
                PipelineIssue(
                    code="unexpected_backend_response_without_request",
                    message="backend_response cannot exist when backend_request is missing.",
                )
            )
        return check

    if backend_request.suspicious_count != len(suspicious_rows):
        check.add_error(
            PipelineIssue(
                code="backend_request_suspicious_count_mismatch",
                message="backend_request.suspicious_count must match the number of SUSPICIOUS rows.",
                context={
                    "request_suspicious_count": backend_request.suspicious_count,
                    "session_row_suspicious_count": len(suspicious_rows),
                },
            )
        )

    suspicious_session_ids = {row.session_id for row in suspicious_rows}
    request_session_ids = {candidate.session_id for candidate in backend_request.candidates}
    if request_session_ids != suspicious_session_ids:
        check.add_error(
            PipelineIssue(
                code="backend_request_session_set_mismatch",
                message="backend_request candidates must exactly match SUSPICIOUS session rows.",
                context={
                    "request_session_ids": sorted(request_session_ids),
                    "suspicious_session_ids": sorted(suspicious_session_ids),
                },
            )
        )

    for candidate in backend_request.candidates:
        if candidate.review_result != "SUSPICIOUS":
            check.add_error(
                PipelineIssue(
                    code="backend_request_includes_non_suspicious_candidate",
                    message="backend_request must not include NORMAL sessions.",
                    context={"session_id": candidate.session_id, "review_result": candidate.review_result},
                )
            )

    for row in suspicious_rows:
        allowed_value_check = validate_allowed_value("backend_delivery_status", row.backend_delivery_status)
        check.errors.extend(allowed_value_check.errors)
        if row.backend_delivery_status == "PENDING":
            check.add_error(
                PipelineIssue(
                    code="pending_backend_delivery_status_after_attempt",
                    message="SUSPICIOUS rows must not remain PENDING after backend delivery is attempted.",
                    context={"session_id": row.session_id},
                )
            )
    if not check.has_errors and any(row.backend_delivery_status == "FAILED" for row in suspicious_rows):
        check.status_impact = "partial"
        if not stage_warnings:
            check.add_warning(
                PipelineIssue(
                    code="backend_delivery_partial_failure",
                    message="One or more SUSPICIOUS rows were persisted but backend delivery did not complete successfully.",
                    context={
                        "failed_session_ids": [
                            row.session_id
                            for row in suspicious_rows
                            if row.backend_delivery_status == "FAILED"
                        ]
                    },
                )
            )

    for row in normal_rows:
        if row.backend_delivery_status != "PENDING":
            check.add_error(
                PipelineIssue(
                    code="normal_session_delivery_status_mutated",
                    message="NORMAL rows must keep backend_delivery_status=PENDING because delivery is suspicious-only.",
                    context={
                        "session_id": row.session_id,
                        "backend_delivery_status": row.backend_delivery_status,
                    },
                )
            )

    if backend_response is not None and backend_response.match_id != backend_request.match_id:
        check.add_error(
            PipelineIssue(
                code="backend_response_match_id_mismatch",
                message="backend_response.match_id must match backend_request.match_id.",
                context={
                    "request_match_id": backend_request.match_id,
                    "response_match_id": backend_response.match_id,
                },
            )
        )

    for warning in stage_warnings:
        check.add_warning(warning)
    return check


def validate_export_stage(output_result: OutputStageResult) -> ValidationCheckResult:
    """Validate DB-based export payloads without reimplementing export generation."""

    run_row = output_result.post_review_runs_row
    session_rows = output_result.post_review_session_result_rows
    suspicious_rows = [row for row in session_rows if row.review_result == "SUSPICIOUS"]
    stage_warnings = [warning for warning in output_result.warnings if warning.code == "post_review_export_failed"]
    check = ValidationCheckResult(
        check_name="stages.export",
        status_impact="partial" if stage_warnings else "none",
        metadata={"suspicious_row_count": len(suspicious_rows)},
    )

    export_artifacts = output_result.export_artifacts
    if export_artifacts is None:
        if stage_warnings:
            for warning in stage_warnings:
                check.add_warning(warning)
        else:
            check.status_impact = "partial"
            check.add_warning(
                PipelineIssue(
                    code="missing_export_artifacts",
                    message="Export artifacts are missing after DB persistence completed.",
                    context={"match_id": run_row.match_id},
                )
            )
        return check

    summary_json = export_artifacts.summary_json
    expected_summary = {
        "match_id": run_row.match_id,
        "window_start_ms": run_row.window_start_ms,
        "window_end_ms": run_row.window_end_ms,
        "total_candidate_sessions": run_row.candidate_count,
        "suspicious_count": run_row.suspicious_count,
        "summary_text": list(run_row.summary_text_json),
        "status": run_row.status,
    }
    if summary_json != expected_summary:
        check.status_impact = "partial"
        check.add_warning(
            PipelineIssue(
                code="summary_export_mismatch",
                message="summary.json content must match the persisted run row.",
                context={"match_id": run_row.match_id},
            )
        )

    try:
        parsed_jsonl_rows = [_parse_jsonl_line(line) for line in export_artifacts.suspicious_sessions_jsonl]
    except ValueError as exc:
        check.status_impact = "partial"
        check.add_warning(
            PipelineIssue(
                code="suspicious_jsonl_parse_failed",
                message="suspicious_sessions.jsonl could not be validated against persisted DB rows.",
                context={"failure_reason": str(exc)},
            )
        )
        return check
    if len(parsed_jsonl_rows) != len(suspicious_rows):
        check.status_impact = "partial"
        check.add_warning(
            PipelineIssue(
                code="suspicious_jsonl_count_mismatch",
                message="suspicious_sessions.jsonl row count must match persisted SUSPICIOUS rows.",
                context={
                    "export_row_count": len(parsed_jsonl_rows),
                    "suspicious_row_count": len(suspicious_rows),
                },
            )
        )

    parsed_csv_rows = list(csv.DictReader(StringIO(export_artifacts.suspicious_sessions_csv)))
    if len(parsed_csv_rows) != len(suspicious_rows):
        check.status_impact = "partial"
        check.add_warning(
            PipelineIssue(
                code="suspicious_csv_count_mismatch",
                message="suspicious_sessions.csv row count must match persisted SUSPICIOUS rows.",
                context={
                    "export_row_count": len(parsed_csv_rows),
                    "suspicious_row_count": len(suspicious_rows),
                },
            )
        )

    suspicious_session_ids = {row.session_id for row in suspicious_rows}
    for export_row in parsed_jsonl_rows:
        if export_row.get("review_result") != "SUSPICIOUS":
            check.status_impact = "partial"
            check.add_warning(
                PipelineIssue(
                    code="suspicious_export_contains_non_suspicious_row",
                    message="Suspicious exports must contain only SUSPICIOUS rows.",
                    context={"session_id": export_row.get("session_id")},
                )
            )
            break
        if export_row.get("session_id") not in suspicious_session_ids:
            check.status_impact = "partial"
            check.add_warning(
                PipelineIssue(
                    code="suspicious_export_session_set_mismatch",
                    message="Suspicious exports must match persisted SUSPICIOUS session rows.",
                    context={"session_id": export_row.get("session_id")},
                )
            )
            break

    return check


def validate_fallback_stage(
    *,
    session_rows: tuple[PostReviewSessionResultRecord, ...],
    stage_warnings: tuple[PipelineIssue, ...],
    upstream_warnings: tuple[PipelineIssue, ...],
) -> ValidationCheckResult:
    """Finalize fallback-related warnings without promoting them to fatal by default."""

    fallback_warnings = [
        warning
        for warning in (*upstream_warnings, *stage_warnings)
        if warning.code.endswith("fallback_applied")
    ]
    unresolved_raw_fallback_rows = [
        row.session_id
        for row in session_rows
        if bool(_session_analysis_payload(row).get("needs_raw_fallback"))
    ]
    check = ValidationCheckResult(
        check_name="stages.fallback",
        metadata={"unresolved_raw_fallback_count": len(unresolved_raw_fallback_rows)},
    )
    for warning in fallback_warnings:
        check.add_warning(warning)
    if unresolved_raw_fallback_rows:
        check.add_warning(
            PipelineIssue(
                code="raw_fallback_still_required",
                message="Some session analyses still require raw fallback context after execution.",
                context={"session_ids": unresolved_raw_fallback_rows},
            )
        )
    return check


def _finalize_report_metadata(report: ValidationReport) -> ValidationReport:
    fatal_reason_codes = [issue.code for issue in report.errors]
    partial_reason_codes = [
        issue.code
        for check in report.checks
        if check.status_impact == "partial"
        for issue in check.warnings
    ]
    report.summary.update(
        {
            "fatal_reason_codes": fatal_reason_codes,
            "partial_reason_codes": partial_reason_codes,
            "error_count": len(report.errors),
            "warning_count": len(report.warnings),
        }
    )
    report.deferred_checks = [
        deferred_check for deferred_check in report.deferred_checks if deferred_check not in _RESOLVED_CHECKS
    ]
    return report


def _error_check(
    *,
    check_name: str,
    code: str,
    message: str,
    context: Mapping[str, object],
) -> ValidationCheckResult:
    check = ValidationCheckResult(check_name=check_name)
    check.add_error(PipelineIssue(code=code, message=message, context=dict(context)))
    return check


def _parse_jsonl_line(line: str) -> dict[str, object]:
    parsed = json.loads(line)
    if not isinstance(parsed, dict):
        raise ValueError("JSONL export row must decode to an object.")
    return parsed


def _session_analysis_payload(row: PostReviewSessionResultRecord) -> Mapping[str, object]:
    payload = row.session_analysis_json
    if hasattr(payload, "__dataclass_fields__"):
        return asdict(payload)
    return payload


__all__ = [
    "RunInputLike",
    "ValidationContext",
    "run_completed_output_checks",
    "validate_backend_stage",
    "validate_db_failure",
    "validate_db_stage",
    "validate_export_stage",
    "validate_fallback_stage",
    "validate_pre_run_checks",
]
