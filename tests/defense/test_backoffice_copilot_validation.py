from __future__ import annotations

import unittest
from datetime import UTC, datetime

from traffic_master_ai.defense.backoffice_copilot.core.models import (
    PostReviewRunRecord,
    PostReviewSessionResultRecord,
    SessionAnalysis,
)
from traffic_master_ai.defense.backoffice_copilot.core.state import PostReviewRunInput
from traffic_master_ai.defense.backoffice_copilot.validation import (
    DEFAULT_DEFERRED_CHECKS,
    ValidationCheckResult,
    ValidationReport,
    get_allowed_values,
    validate_allowed_value,
    validate_db_rows,
    validate_run_input_params,
)


def _session_analysis() -> SessionAnalysis:
    return SessionAnalysis(
        session_id="sess-1",
        latest_flow_state="F4M",
        latest_action="NONE",
        latest_tier="T1",
        terminal_outcome="NOT_BLOCKED",
        seen_t1=True,
        seen_t2=False,
        vqa_fail_count=0,
        throttle_event_count=0,
        suspicious_signals=[],
        timeline_summary=["Observed only baseline activity."],
        needs_raw_fallback=False,
    )


class ValidationSkeletonTests(unittest.TestCase):
    def test_validate_run_input_params_accepts_minimal_valid_contract(self) -> None:
        check = validate_run_input_params(
            PostReviewRunInput(
                match_id="match-1",
                window_start_ms=100,
                window_end_ms=200,
                limit=10,
                use_raw_audit_fallback=False,
            )
        )

        self.assertEqual(check.check_name, "params.run_input")
        self.assertFalse(check.has_errors)
        self.assertIn("match_id", check.metadata["validated_fields"])

    def test_validate_run_input_params_reports_type_and_range_errors(self) -> None:
        check = validate_run_input_params(
            {
                "match_id": "",
                "window_start_ms": 200,
                "window_end_ms": 100,
                "limit": 0,
                "use_raw_audit_fallback": "yes",
            }
        )

        self.assertTrue(check.has_errors)
        error_codes = {issue.code for issue in check.errors}
        self.assertIn("invalid_run_input_match_id", error_codes)
        self.assertIn("invalid_run_input_window_range", error_codes)
        self.assertIn("invalid_run_input_limit_range", error_codes)
        self.assertIn("invalid_run_input_use_raw_audit_fallback", error_codes)

    def test_validate_allowed_value_reuses_documented_sets(self) -> None:
        self.assertEqual(
            get_allowed_values("status"),
            frozenset({"SUCCESS", "PARTIAL_SUCCESS", "FAILED"}),
        )

        valid_check = validate_allowed_value("review_result", "NORMAL")
        invalid_check = validate_allowed_value("backend_delivery_status", "UNKNOWN")

        self.assertFalse(valid_check.has_errors)
        self.assertTrue(invalid_check.has_errors)
        self.assertEqual(invalid_check.errors[0].code, "invalid_allowed_value")

    def test_validation_report_merges_checks_and_preserves_deferred_slots(self) -> None:
        report = ValidationReport()
        report.add_check(ValidationCheckResult(check_name="params.run_input"))

        other = ValidationReport(
            checks=[ValidationCheckResult(check_name="db_checks.post_review_runs")],
            deferred_checks=["custom_future_check"],
            summary={"session_row_count": 1},
        )
        report.merge(other)

        self.assertEqual([check.check_name for check in report.checks], ["params.run_input", "db_checks.post_review_runs"])
        self.assertTrue(set(DEFAULT_DEFERRED_CHECKS).issubset(report.deferred_checks))
        self.assertIn("custom_future_check", report.deferred_checks)
        self.assertEqual(report.summary["session_row_count"], 1)

    def test_validate_db_rows_wraps_task2_storage_validators(self) -> None:
        now = datetime(2026, 3, 27, 3, 0, 0, tzinfo=UTC)
        run_record = PostReviewRunRecord(
            match_id="match-1",
            window_start_ms=100,
            window_end_ms=200,
            candidate_count=1,
            suspicious_count=0,
            summary_text_json=[
                "Window reviewed 1 candidate session.",
                "0 sessions remained suspicious after review.",
                "Summary remained independent from status resolution.",
            ],
            status="SUCCESS",
            created_at=now,
            updated_at=now,
        )
        session_record = PostReviewSessionResultRecord(
            match_id="match-1",
            session_id="sess-1",
            review_result="NORMAL",
            evidence_summary="Observed only baseline activity.",
            session_analysis_json=_session_analysis(),
            backend_delivery_status="PENDING",
            created_at=now,
            updated_at=now,
        )

        valid_report = validate_db_rows(run_record=run_record, session_records=[session_record])
        self.assertFalse(valid_report.has_errors)
        self.assertEqual(valid_report.summary["session_row_count"], 1)

        invalid_report = validate_db_rows(
            run_record=PostReviewRunRecord(
                match_id="match-2",
                window_start_ms=100,
                window_end_ms=200,
                candidate_count=0,
                suspicious_count=1,
                summary_text_json=["too", "short"],
                status="SUCCESS",
                created_at=now,
                updated_at=now,
            )
        )
        self.assertTrue(invalid_report.has_errors)
        self.assertEqual(invalid_report.errors[0].code, "invalid_post_review_runs_row")


if __name__ == "__main__":
    unittest.main()
