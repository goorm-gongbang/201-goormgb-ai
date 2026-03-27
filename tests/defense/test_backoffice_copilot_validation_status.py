from __future__ import annotations

import unittest
from datetime import UTC, datetime

from traffic_master_ai.defense.backoffice_copilot.core.issues import PipelineIssue
from traffic_master_ai.defense.backoffice_copilot.core.models import (
    BackendCandidate,
    BackendRequest,
    BackendResponse,
    PostReviewRunRecord,
    PostReviewSessionResultRecord,
    SessionAnalysis,
)
from traffic_master_ai.defense.backoffice_copilot.core.state import PostReviewRunInput
from traffic_master_ai.defense.backoffice_copilot.output.exporter import ExportArtifacts, build_export_artifacts
from traffic_master_ai.defense.backoffice_copilot.output.persistence import OutputStageResult
from traffic_master_ai.defense.backoffice_copilot.storage.repository import PkConflictPolicy
from traffic_master_ai.defense.backoffice_copilot.validation import (
    ValidationContext,
    resolve_run_validation,
)

def _run_input() -> PostReviewRunInput:
    return PostReviewRunInput(
        match_id="match-1",
        window_start_ms=100,
        window_end_ms=200,
        limit=10,
        use_raw_audit_fallback=False,
    )


def _run_row(*, suspicious_count: int = 0, status: str = "SUCCESS") -> PostReviewRunRecord:
    now = datetime(2026, 3, 27, 4, 0, 0, tzinfo=UTC)
    return PostReviewRunRecord(
        match_id="match-1",
        window_start_ms=100,
        window_end_ms=200,
        candidate_count=1,
        suspicious_count=suspicious_count,
        summary_text_json=[
            "Window reviewed 1 candidate session.",
            f"{suspicious_count} sessions remained suspicious after review.",
            "Summary remained independent from final validation.",
        ],
        status=status,
        created_at=now,
        updated_at=now,
    )


def _session_row(
    *,
    review_result: str = "NORMAL",
    backend_delivery_status: str = "PENDING",
    session_id: str = "sess-1",
    needs_raw_fallback: bool = False,
) -> PostReviewSessionResultRecord:
    now = datetime(2026, 3, 27, 4, 0, 0, tzinfo=UTC)
    return PostReviewSessionResultRecord(
        match_id="match-1",
        session_id=session_id,
        review_result=review_result,
        evidence_summary="Observed only baseline activity." if review_result == "NORMAL" else "Observed repeated T2 activity.",
        session_analysis_json=SessionAnalysis(
            session_id=session_id,
            latest_flow_state="F4M",
            latest_action="NONE" if review_result == "NORMAL" else "THROTTLE",
            latest_tier="T1" if review_result == "NORMAL" else "T2",
            terminal_outcome="NOT_BLOCKED",
            seen_t1=True,
            seen_t2=review_result == "SUSPICIOUS",
            vqa_fail_count=0 if review_result == "NORMAL" else 1,
            throttle_event_count=0 if review_result == "NORMAL" else 1,
            suspicious_signals=[] if review_result == "NORMAL" else ["Reached T2 during session"],
            timeline_summary=["Observed only baseline activity."],
            needs_raw_fallback=needs_raw_fallback,
        ),
        backend_delivery_status=backend_delivery_status,
        created_at=now,
        updated_at=now,
    )


def _export_artifacts(run_row: PostReviewRunRecord, session_rows: tuple[PostReviewSessionResultRecord, ...]) -> ExportArtifacts:
    return build_export_artifacts(run_row=run_row, session_rows=session_rows)


class ValidationStatusResolverTests(unittest.TestCase):
    def test_resolve_run_validation_returns_success_for_clean_db_first_output(self) -> None:
        run_row = _run_row()
        session_rows = (_session_row(),)
        outcome = resolve_run_validation(
            ValidationContext(
                run_input=_run_input(),
                conflict_policy=PkConflictPolicy.UPSERT,
                output_result=OutputStageResult(
                    post_review_runs_row=run_row,
                    post_review_session_result_rows=session_rows,
                    backend_request=None,
                    backend_response=None,
                    export_artifacts=_export_artifacts(run_row, session_rows),
                    warnings=(),
                ),
                upstream_warnings=(
                    PipelineIssue(
                        code="llm_review_fallback_applied",
                        message="Fallback was used for one session.",
                        context={"session_id": "sess-1", "fallback_applied": True},
                    ),
                ),
            )
        )

        self.assertEqual(outcome.final_status, "SUCCESS")
        self.assertFalse(outcome.errors)
        self.assertIn("llm_review_fallback_applied", [issue.code for issue in outcome.warnings])

    def test_resolve_run_validation_returns_partial_success_for_backend_failure(self) -> None:
        run_row = _run_row(suspicious_count=1)
        session_rows = (_session_row(review_result="SUSPICIOUS", backend_delivery_status="FAILED"),)
        backend_request = BackendRequest(
            match_id="match-1",
            window_start_ms=100,
            window_end_ms=200,
            suspicious_count=1,
            candidates=[
                BackendCandidate(
                    session_id="sess-1",
                    review_result="SUSPICIOUS",
                    reason_summary="Observed repeated T2 activity.",
                )
            ],
        )
        outcome = resolve_run_validation(
            ValidationContext(
                run_input=_run_input(),
                conflict_policy=PkConflictPolicy.FAIL_FAST,
                output_result=OutputStageResult(
                    post_review_runs_row=run_row,
                    post_review_session_result_rows=session_rows,
                    backend_request=backend_request,
                    backend_response=None,
                    export_artifacts=_export_artifacts(run_row, session_rows),
                    warnings=(
                        PipelineIssue(
                            code="backend_delivery_failed",
                            message="Backend delivery was skipped because no adapter was configured.",
                            context={"match_id": "match-1", "fallback_reason": "adapter_missing"},
                        ),
                    ),
                ),
            )
        )

        self.assertEqual(outcome.final_status, "PARTIAL_SUCCESS")
        self.assertFalse(outcome.errors)
        self.assertIn("backend_delivery_failed", [issue.code for issue in outcome.warnings])

    def test_resolve_run_validation_treats_db_failure_as_failed(self) -> None:
        outcome = resolve_run_validation(
            ValidationContext(
                run_input=_run_input(),
                conflict_policy=PkConflictPolicy.UPSERT,
                output_result=None,
                output_error=RuntimeError("database unavailable"),
            )
        )

        self.assertEqual(outcome.final_status, "FAILED")
        self.assertIn("db_persistence_failed", [issue.code for issue in outcome.errors])

    def test_resolve_run_validation_rejects_invalid_delivery_status_for_attempted_session(self) -> None:
        run_row = _run_row(suspicious_count=1)
        session_rows = (_session_row(review_result="SUSPICIOUS", backend_delivery_status=""),)
        backend_request = BackendRequest(
            match_id="match-1",
            window_start_ms=100,
            window_end_ms=200,
            suspicious_count=1,
            candidates=[
                BackendCandidate(
                    session_id="sess-1",
                    review_result="SUSPICIOUS",
                    reason_summary="Observed repeated T2 activity.",
                )
            ],
        )

        outcome = resolve_run_validation(
            ValidationContext(
                run_input=_run_input(),
                conflict_policy=PkConflictPolicy.UPSERT,
                output_result=OutputStageResult(
                    post_review_runs_row=run_row,
                    post_review_session_result_rows=session_rows,
                    backend_request=backend_request,
                    backend_response=BackendResponse(
                        match_id="match-1",
                        accepted_count=1,
                        rejected_count=0,
                        status="ACCEPTED",
                        received_at="2026-03-27T04:01:00+00:00",
                    ),
                    export_artifacts=None,
                    warnings=(),
                ),
            )
        )

        self.assertEqual(outcome.final_status, "FAILED")
        self.assertIn("invalid_post_review_session_results_row", [issue.code for issue in outcome.errors])

    def test_resolve_run_validation_treats_export_failure_as_partial_success(self) -> None:
        run_row = _run_row()
        session_rows = (_session_row(),)
        outcome = resolve_run_validation(
            ValidationContext(
                run_input=_run_input(),
                conflict_policy=PkConflictPolicy.UPSERT,
                output_result=OutputStageResult(
                    post_review_runs_row=run_row,
                    post_review_session_result_rows=session_rows,
                    backend_request=None,
                    backend_response=None,
                    export_artifacts=None,
                    warnings=(
                        PipelineIssue(
                            code="post_review_export_failed",
                            message="Export generation failed after DB-first persistence completed.",
                            context={"match_id": "match-1", "failure_reason": "OSError: disk full"},
                        ),
                    ),
                ),
            )
        )

        self.assertEqual(outcome.final_status, "PARTIAL_SUCCESS")
        self.assertFalse(outcome.errors)
        self.assertIn("post_review_export_failed", [issue.code for issue in outcome.warnings])


if __name__ == "__main__":
    unittest.main()
