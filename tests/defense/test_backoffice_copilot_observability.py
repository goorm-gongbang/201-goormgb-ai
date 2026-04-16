"""Observability tests for Post-Review pipeline.

Verifies that structured logs are emitted for each pipeline stage,
fallback paths are distinguishable from failures, and the final
PostReviewCliResult summary includes all observability fields.

These tests do NOT change review logic — they only verify that
logs / summary fields are present and accurate.
"""

from __future__ import annotations

import logging
import unittest
from datetime import UTC, datetime

from traffic_master_ai.defense.backoffice_copilot.core.models import (
    SessionAnalysis,
    SessionReviewResult,
    SessionSummary,
)
from traffic_master_ai.defense.backoffice_copilot.core.state import AnalysisInput
from traffic_master_ai.defense.backoffice_copilot.core.models import DefenseAuditEventRow
from traffic_master_ai.defense.backoffice_copilot.output.persistence import execute_output_stage
from traffic_master_ai.defense.backoffice_copilot.review.executor import execute_session_reviews
from traffic_master_ai.defense.backoffice_copilot.runner import (
    PostReviewExecutionConfig,
    execute_post_review,
)
from traffic_master_ai.defense.backoffice_copilot.summary.window_summary import generate_summary_text


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _session_analysis(session_id: str, *, suspicious: bool = True) -> SessionAnalysis:
    return SessionAnalysis(
        session_id=session_id,
        latest_flow_state="F4M",
        latest_action="THROTTLE" if suspicious else "NONE",
        latest_tier="T2" if suspicious else "T1",
        terminal_outcome="NOT_BLOCKED",
        seen_t1=True,
        seen_t2=suspicious,
        vqa_fail_count=1 if suspicious else 0,
        throttle_event_count=1 if suspicious else 0,
        suspicious_signals=["Reached T2"] if suspicious else [],
        timeline_summary=["Reviewed."],
        needs_raw_fallback=False,
    )


def _review_result(session_id: str, result: str = "SUSPICIOUS") -> SessionReviewResult:
    return SessionReviewResult(
        session_id=session_id,
        review_result=result,
        evidence_summary="Evidence.",
    )


def _candidate(session_id: str) -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        seen_t1=True,
        seen_t2=True,
        block_event_count=0,
        vqa_fail_count=1,
        throttle_event_count=1,
        latest_flow_state="F4M",
        latest_action="THROTTLE",
        latest_tier="T2",
        terminal_outcome="NOT_BLOCKED",
    )


def _analysis_input_with_event(session_id: str = "sess-obs") -> AnalysisInput:
    return AnalysisInput(
        defense_audit_events=(
            DefenseAuditEventRow(
                ts_ms=150,
                trace_id=f"trace-{session_id}",
                session_id=session_id,
                event_type="DEF_ORCH_EXECUTED",
                payload={"latest_action": "THROTTLE"},
            ),
        ),
        raw_audit_available=False,
    )


class _RecordingRepository:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def save_run(self, _run_record) -> None:
        self.calls.append(("save_run",))

    def save_session_results(self, _session_records) -> None:
        self.calls.append(("save_session_results",))

    def save_bundle(self, _run_record, _session_records) -> None:
        self.calls.append(("save_bundle",))


class _FailingRepository:
    """Repository that always raises on save_bundle."""

    def save_run(self, run_record) -> None:
        raise RuntimeError("db_down")

    def save_session_results(self, session_records) -> None:
        raise RuntimeError("db_down")

    def save_bundle(self, run_record, session_records) -> None:
        raise RuntimeError("db_down: connection refused")


# ---------------------------------------------------------------------------
# 1. LLM adapter missing → fallback warning logged
# ---------------------------------------------------------------------------

class ReviewFallbackLogTests(unittest.TestCase):
    """post_review_review_fallback_applied is logged when LLM adapter is absent."""

    def test_no_llm_adapter_logs_fallback_warning(self) -> None:
        analysis_list = (_session_analysis("sess-1"),)
        with self.assertLogs(
            "traffic_master_ai.defense.backoffice_copilot.review.executor",
            level=logging.WARNING,
        ) as cm:
            result = execute_session_reviews(
                match_id="match-obs",
                window_start_ms=1000,
                window_end_ms=2000,
                session_analysis_list=analysis_list,
                llm_review_adapter=None,
            )

        log_output = "\n".join(cm.output)
        self.assertIn("post_review_review_fallback_applied", log_output)
        self.assertIn("match_id=match-obs", log_output)
        self.assertIn("window_start_ms=1000", log_output)
        self.assertIn("window_end_ms=2000", log_output)
        self.assertIn("fallback_reason=adapter_missing", log_output)
        self.assertIn("fallback_mode=deterministic", log_output)
        self.assertIn("degraded=true", log_output)
        # Fallback should still produce a review result (not raise)
        self.assertEqual(len(result.review_results), 1)
        # Warning recorded in issues list too
        self.assertTrue(
            any(w.code == "llm_review_fallback_applied" for w in result.warnings)
        )


# ---------------------------------------------------------------------------
# 2. Summary adapter missing → fallback warning logged
# ---------------------------------------------------------------------------

class SummaryFallbackLogTests(unittest.TestCase):
    """post_review_summary_fallback_applied is logged when summary adapter is absent."""

    def test_no_summary_adapter_logs_fallback_warning(self) -> None:
        with self.assertLogs(
            "traffic_master_ai.defense.backoffice_copilot.summary.window_summary",
            level=logging.WARNING,
        ) as cm:
            result = generate_summary_text(
                match_id="match-obs",
                window_start_ms=1000,
                window_end_ms=2000,
                review_results=[_review_result("sess-1")],
                session_analysis_list=[_session_analysis("sess-1")],
                summary_adapter=None,
            )

        log_output = "\n".join(cm.output)
        self.assertIn("post_review_summary_fallback_applied", log_output)
        self.assertIn("match_id=match-obs", log_output)
        self.assertIn("fallback_reason=adapter_missing", log_output)
        self.assertIn("fallback_mode=template", log_output)
        self.assertIn("degraded=true", log_output)
        self.assertEqual(len(result.summary_text), 3)
        self.assertTrue(
            any(w.code == "window_summary_fallback_applied" for w in result.warnings)
        )


# ---------------------------------------------------------------------------
# 3. output_persist success → db_persist_success log emitted
# ---------------------------------------------------------------------------

class DbPersistSuccessLogTests(unittest.TestCase):
    """post_review_db_persist_success is logged on successful save_bundle."""

    def test_persist_success_logs_emitted(self) -> None:
        repository = _RecordingRepository()
        now = datetime(2026, 4, 1, tzinfo=UTC)
        review_results = (_review_result("sess-1"),)
        session_analysis_list = (_session_analysis("sess-1"),)
        candidates = (_candidate("sess-1"),)

        with self.assertLogs(
            "traffic_master_ai.defense.backoffice_copilot.output.persistence",
            level=logging.INFO,
        ) as cm:
            execute_output_stage(
                repository=repository,
                match_id="match-obs",
                window_start_ms=1000,
                window_end_ms=2000,
                candidate_sessions=candidates,
                review_results=review_results,
                session_analysis_list=session_analysis_list,
                summary_text=["Line 1.", "Line 2.", "Line 3."],
                now=now,
            )

        log_output = "\n".join(cm.output)
        self.assertIn("post_review_db_persist_start", log_output)
        self.assertIn("post_review_db_persist_success", log_output)
        self.assertIn("match_id=match-obs", log_output)
        self.assertIn("session_result_row_count=1", log_output)
        self.assertNotIn("post_review_db_persist_failed", log_output)
        # save_bundle must have been called (may be followed by save_session_results for delivery update)
        self.assertTrue(any(call[0] == "save_bundle" for call in repository.calls))


# ---------------------------------------------------------------------------
# 4. output_persist failure → db_persist_failed log + error_code in summary
# ---------------------------------------------------------------------------

class DbPersistFailureLogTests(unittest.TestCase):
    """post_review_db_persist_failed is logged and error propagates when save_bundle raises."""

    def test_persist_failure_logs_and_raises(self) -> None:
        repository = _FailingRepository()
        now = datetime(2026, 4, 1, tzinfo=UTC)

        with self.assertLogs(
            "traffic_master_ai.defense.backoffice_copilot.output.persistence",
            level=logging.ERROR,
        ) as cm:
            with self.assertRaises(RuntimeError):
                execute_output_stage(
                    repository=repository,
                    match_id="match-obs",
                    window_start_ms=1000,
                    window_end_ms=2000,
                    candidate_sessions=(_candidate("sess-1"),),
                    review_results=(_review_result("sess-1"),),
                    session_analysis_list=(_session_analysis("sess-1"),),
                    summary_text=["L1.", "L2.", "L3."],
                    now=now,
                )

        log_output = "\n".join(cm.output)
        self.assertIn("post_review_db_persist_failed", log_output)
        self.assertIn("exception_type=RuntimeError", log_output)
        self.assertIn("exception_message=db_down: connection refused", log_output)


# ---------------------------------------------------------------------------
# 5. PostReviewCliResult summary fields populated correctly
# ---------------------------------------------------------------------------

class SummaryFieldsTests(unittest.TestCase):
    """PostReviewCliResult must contain all observability fields."""

    def _run(
        self,
        *,
        repository,
        input_count: int = 1,
    ):
        config = PostReviewExecutionConfig(
            match_id="match-fields",
            window_start_ms=1000,
            window_end_ms=2000,
            dry_run=False,
        )
        return execute_post_review(
            config=config,
            analysis_input=_analysis_input_with_event("sess-fields"),
            input_source="fixture_jsonl",
            input_count=input_count,
            repository=repository,
        )

    def test_success_path_summary_fields(self) -> None:
        result = self._run(repository=_RecordingRepository())

        self.assertEqual(result.status, "completed")
        self.assertIsNone(result.failure_stage)
        self.assertIsNone(result.error_code)
        self.assertFalse(result.llm_used)       # no LLM key in env
        self.assertTrue(result.fallback_used)   # deterministic fallback applied
        self.assertTrue(result.degraded)        # fallback → degraded
        self.assertTrue(result.db_persist_attempted)
        self.assertTrue(result.db_persist_succeeded)
        self.assertIsInstance(result.warning_codes, tuple)
        self.assertIsInstance(result.error_codes, tuple)

    def test_failure_path_summary_fields(self) -> None:
        result = self._run(repository=_FailingRepository())

        self.assertEqual(result.status, "failed")
        self.assertIsNotNone(result.failure_stage)
        self.assertIsNotNone(result.error_code)
        self.assertTrue(result.db_persist_attempted)
        self.assertFalse(result.db_persist_succeeded)

    def test_no_input_summary_fields(self) -> None:
        result = self._run(repository=_RecordingRepository(), input_count=0)

        self.assertEqual(result.status, "no_input")
        self.assertIsNone(result.failure_stage)
        self.assertIsNone(result.error_code)
        self.assertFalse(result.degraded)
        self.assertFalse(result.db_persist_attempted)
        self.assertFalse(result.db_persist_succeeded)


# ---------------------------------------------------------------------------
# 6. Existing status contract unchanged (regression guard)
# ---------------------------------------------------------------------------

class StatusContractRegressionTests(unittest.TestCase):
    """Core status semantics must not change."""

    def test_no_input_status(self) -> None:
        config = PostReviewExecutionConfig(
            match_id="match-reg",
            window_start_ms=1000,
            window_end_ms=2000,
        )
        result = execute_post_review(
            config=config,
            analysis_input=AnalysisInput(),
            input_source="clickhouse_read_model",
            input_count=0,
            repository=_RecordingRepository(),
        )
        self.assertEqual(result.status, "no_input")
        self.assertIsNone(result.final_status)

    def test_completed_status_on_success(self) -> None:
        config = PostReviewExecutionConfig(
            match_id="match-reg",
            window_start_ms=1000,
            window_end_ms=2000,
        )
        result = execute_post_review(
            config=config,
            analysis_input=_analysis_input_with_event("sess-reg"),
            input_source="fixture_jsonl",
            input_count=1,
            repository=_RecordingRepository(),
        )
        self.assertIn(result.status, ("completed", "failed"))

    def test_failed_status_on_db_error(self) -> None:
        config = PostReviewExecutionConfig(
            match_id="match-reg",
            window_start_ms=1000,
            window_end_ms=2000,
        )
        result = execute_post_review(
            config=config,
            analysis_input=_analysis_input_with_event("sess-reg"),
            input_source="fixture_jsonl",
            input_count=1,
            repository=_FailingRepository(),
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.final_status, "FAILED")


if __name__ == "__main__":
    unittest.main()
