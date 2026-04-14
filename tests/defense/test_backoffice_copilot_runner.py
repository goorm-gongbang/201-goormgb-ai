from __future__ import annotations

from datetime import UTC, datetime
import unittest
from unittest.mock import patch

from traffic_master_ai.defense.backoffice_copilot.core.models import DefenseAuditEventRow
from traffic_master_ai.defense.backoffice_copilot.core.state import AnalysisInput, PostReviewRunInput
from traffic_master_ai.defense.backoffice_copilot.runner import (
    PostReviewExecutionConfig,
    _config_from_args,
    _parse_args,
    build_default_post_review_match_id,
    build_analysis_input_from_clickhouse_read_models,
    execute_post_review,
    resolve_default_post_review_window,
)
from traffic_master_ai.defense.backoffice_copilot.storage import (
    BackofficeClickHouseReadModelInput,
    ClickHousePostReviewCandidateRow,
    ClickHouseSessionRollupRow,
    PkConflictPolicy,
)
from traffic_master_ai.defense.backoffice_copilot.workflow import (
    BackofficeCopilotWorkflowDependencies,
    build_backoffice_copilot_workflow,
)


class _FailingRepository:
    def save_run(self, run_record) -> None:
        raise AssertionError("repository write must not be called")

    def save_session_results(self, session_records) -> None:
        raise AssertionError("repository write must not be called")

    def save_bundle(self, run_record, session_records) -> None:
        raise AssertionError("repository write must not be called")


class _RecordingRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def save_run(self, run_record) -> None:
        self.calls.append(("save_run", run_record))

    def save_session_results(self, session_records) -> None:
        self.calls.append(("save_session_results", tuple(session_records)))

    def save_bundle(self, run_record, session_records) -> None:
        self.calls.append(("save_bundle", run_record, tuple(session_records)))


def _run_input() -> PostReviewRunInput:
    return PostReviewRunInput(
        match_id="match-runner",
        window_start_ms=100,
        window_end_ms=200,
        limit=10,
        use_raw_audit_fallback=False,
    )


def _passing_analysis_input() -> AnalysisInput:
    return AnalysisInput(
        defense_audit_events=(
            DefenseAuditEventRow(
                ts_ms=150,
                trace_id="trace-runner",
                session_id="sess-runner",
                event_type="DEF_ORCH_EXECUTED",
                payload={
                    "latest_flow_state": "F4M",
                    "latest_action": "ALLOW",
                    "latest_tier": "T1",
                    "terminal_outcome": "NOT_BLOCKED",
                    "reason_code": "RULE_HIT",
                },
            ),
        ),
        raw_audit_available=False,
    )


class BackofficeCopilotRunnerTests(unittest.TestCase):
    def test_default_window_uses_previous_utc_ten_minute_bucket(self) -> None:
        window_start_ms, window_end_ms = resolve_default_post_review_window(
            now_ms=1776112567123
        )

        self.assertEqual(window_end_ms % 600000, 0)
        self.assertEqual(window_end_ms - window_start_ms, 600000)
        self.assertLessEqual(window_end_ms, 1776112567123)

    def test_default_match_id_is_deterministic_for_same_window_end(self) -> None:
        window_end = datetime(2026, 4, 14, 12, 30, tzinfo=UTC)
        window_end_ms = int(window_end.timestamp() * 1000)

        self.assertEqual(
            build_default_post_review_match_id(window_end_ms),
            "post-review-202604141230",
        )
        self.assertEqual(
            build_default_post_review_match_id(window_end_ms),
            build_default_post_review_match_id(window_end_ms),
        )

    def test_cli_config_generates_default_window_and_match_id(self) -> None:
        with patch(
            "traffic_master_ai.defense.backoffice_copilot.runner.time.time",
            return_value=1776112567.123,
        ):
            config = _config_from_args(_parse_args(["--dry-run"]))

        self.assertEqual(config.window_end_ms % 600000, 0)
        self.assertEqual(config.window_end_ms - config.window_start_ms, 600000)
        self.assertEqual(
            config.match_id,
            build_default_post_review_match_id(config.window_end_ms),
        )
        self.assertTrue(config.dry_run)

    def test_workflow_accepts_analysis_input_provider_without_fixture_path(self) -> None:
        repository = _RecordingRepository()
        workflow = build_backoffice_copilot_workflow(
            BackofficeCopilotWorkflowDependencies(
                audit_events_jsonl_path=None,
                analysis_input_provider=lambda _: _passing_analysis_input(),
                repository=repository,
                conflict_policy=PkConflictPolicy.UPSERT,
                llm_review_adapter=lambda _: {
                    "review_result": "NORMAL",
                    "evidence_summary": "Candidate stayed below suspicious threshold.",
                },
                summary_adapter=lambda _: {
                    "summary_text": [
                        "Window reviewed 1 candidate session.",
                        "0 sessions remained suspicious after review.",
                        "Post-review output stayed PostgreSQL-first.",
                    ]
                },
            )
        )

        result = workflow.invoke(_run_input())

        self.assertEqual(result.final_status, "SUCCESS")
        self.assertEqual(len(result.state.candidate_sessions), 1)
        self.assertEqual([call[0] for call in repository.calls], ["save_bundle"])

    def test_clickhouse_read_model_input_is_adapted_without_raw_fallback(self) -> None:
        analysis_input = build_analysis_input_from_clickhouse_read_models(
            BackofficeClickHouseReadModelInput(
                session_rollups=(
                    ClickHouseSessionRollupRow(
                        window_start_ms=100,
                        window_end_ms=200,
                        session_id="sess-clickhouse",
                        first_ts_ms=110,
                        last_ts_ms=190,
                        event_count=4,
                        latest_flow_state="F4M",
                        latest_action="THROTTLE",
                        latest_risk_tier="T2",
                        latest_reason_code="RULE_HIT",
                        latest_policy_version="policy-v1",
                        throttle_action_count=2,
                        block_action_count=0,
                        challenge_issue_count=1,
                        challenge_verified_count=0,
                    ),
                ),
                candidate_rows=(
                    ClickHousePostReviewCandidateRow(
                        window_start_ms=100,
                        window_end_ms=200,
                        session_id="sess-clickhouse",
                        first_ts_ms=110,
                        last_ts_ms=190,
                        latest_action="THROTTLE",
                        latest_risk_tier="T2",
                        latest_reason_code="RULE_HIT",
                        latest_policy_version="policy-v1",
                        block_action_count=0,
                        throttle_action_count=2,
                        challenge_issue_count=1,
                        challenge_verified_count=0,
                        candidate_reason="throttle_action_detected",
                    ),
                ),
            )
        )

        event_types = [row.event_type for row in analysis_input.defense_audit_events]

        self.assertFalse(analysis_input.raw_audit_available)
        self.assertEqual(event_types.count("DEF_THROTTLE_APPLIED"), 2)
        self.assertIn("S3_CHALLENGE_RESULT", event_types)
        self.assertEqual(event_types[-1], "DEF_ORCH_EXECUTED")

    def test_execute_post_review_no_input_short_circuits_without_repository(self) -> None:
        with self.assertLogs(
            "traffic_master_ai.defense.backoffice_copilot.runner",
            level="INFO",
        ) as logs:
            result = execute_post_review(
                config=PostReviewExecutionConfig(
                    match_id="match-empty",
                    window_start_ms=100,
                    window_end_ms=200,
                ),
                analysis_input=AnalysisInput(),
                input_source="clickhouse_read_model",
                input_count=0,
                repository=_FailingRepository(),
            )

        self.assertEqual(result.status, "no_input")
        self.assertEqual(result.output_count, 0)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.error_count, 0)
        self.assertIn("post_review_summary", "\n".join(logs.output))

    def test_execute_post_review_dry_run_uses_noop_repository(self) -> None:
        result = execute_post_review(
            config=PostReviewExecutionConfig(
                match_id="match-dry-run",
                window_start_ms=100,
                window_end_ms=200,
                dry_run=True,
                review_max_workers=1,
                session_analysis_max_workers=1,
            ),
            analysis_input=_passing_analysis_input(),
            input_source="clickhouse_read_model",
            input_count=1,
            repository=_FailingRepository(),
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output_count, 1)
        self.assertTrue(result.dry_run)


if __name__ == "__main__":
    unittest.main()
