from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from traffic_master_ai.defense.backoffice_copilot.core.state import PostReviewRunInput
from traffic_master_ai.defense.backoffice_copilot.workflow import (
    WORKFLOW_NODE_ORDER,
    BackofficeCopilotWorkflowDependencies,
    build_backoffice_copilot_workflow,
)


class _FakeRepository:
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
        match_id="match-1",
        window_start_ms=100,
        window_end_ms=200,
        limit=10,
        use_raw_audit_fallback=False,
    )
def _fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / "backoffice_copilot" / name


class WorkflowAppTests(unittest.TestCase):
    def test_workflow_entrypoint_runs_six_nodes_in_fixed_order(self) -> None:
        repository = _FakeRepository()
        workflow = build_backoffice_copilot_workflow(
            BackofficeCopilotWorkflowDependencies(
                audit_events_jsonl_path=_fixture_path("single_candidate_t2.jsonl"),
                repository=repository,
                conflict_policy="upsert",
                llm_review_adapter=lambda _: {
                    "review_result": "NORMAL",
                    "evidence_summary": "Observed throttle activity but no suspicious outcome.",
                },
                summary_adapter=lambda _: {
                    "summary_text": [
                        "Window reviewed 1 candidate session.",
                        "0 sessions remained suspicious after review.",
                        "DB-first output stayed downstream of the summary node.",
                    ]
                },
            )
        )

        result = workflow.invoke(_run_input())

        self.assertEqual(result.node_history, WORKFLOW_NODE_ORDER)
        self.assertEqual(len(result.node_history), 6)
        self.assertEqual(result.final_status, "SUCCESS")
        self.assertEqual(result.validation_outcome.final_status, "SUCCESS")
        self.assertEqual(result.state.match_id, "match-1")
        self.assertEqual(len(result.state.candidate_sessions), 1)
        self.assertEqual(len(result.state.session_analysis_list), 1)
        self.assertEqual(len(result.state.review_results), 1)
        self.assertEqual(result.state.review_results[0].review_result, "NORMAL")
        self.assertEqual(len(result.state.summary_text), 3)
        self.assertEqual(result.state.post_review_runs_row.status, "SUCCESS")
        self.assertIsNone(result.state.backend_request)
        self.assertEqual([call[0] for call in repository.calls], ["save_bundle"])
        self.assertEqual(result.state.errors, [])

    def test_workflow_node_6_keeps_summary_and_persistence_separate_while_resolving_partial(self) -> None:
        repository = _FakeRepository()
        with TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir) / "exports"
            workflow = build_backoffice_copilot_workflow(
                BackofficeCopilotWorkflowDependencies(
                    audit_events_jsonl_path=_fixture_path("single_candidate_t2.jsonl"),
                    repository=repository,
                    conflict_policy="upsert",
                    llm_review_adapter=lambda _: {
                        "review_result": "SUSPICIOUS",
                        "evidence_summary": "Observed repeated T2 throttle activity.",
                    },
                    summary_adapter=lambda _: {
                        "summary_text": [
                            "Window reviewed 1 candidate session.",
                            "1 session remained suspicious after review.",
                            "Summary generation completed before DB persistence and delivery.",
                        ]
                    },
                    backend_adapter=None,
                    export_dir=export_dir,
                )
            )

            result = workflow.invoke(_run_input())
            summary_json = json.loads((export_dir / "summary.json").read_text(encoding="utf-8"))

        self.assertEqual(result.node_history, WORKFLOW_NODE_ORDER)
        self.assertEqual(result.final_status, "PARTIAL_SUCCESS")
        self.assertEqual(result.validation_outcome.final_status, "PARTIAL_SUCCESS")
        self.assertEqual(result.state.summary_text[1], "1 session remained suspicious after review.")
        self.assertEqual(result.state.post_review_runs_row.status, "PARTIAL_SUCCESS")
        self.assertEqual(result.state.backend_request.suspicious_count, 1)
        self.assertEqual(result.state.post_review_session_result_rows[0].backend_delivery_status, "FAILED")
        self.assertIn("backend_delivery_failed", [issue.code for issue in result.state.warnings])
        self.assertEqual(
            [call[0] for call in repository.calls],
            ["save_bundle", "save_session_results", "save_run"],
        )
        self.assertEqual(summary_json["status"], "PARTIAL_SUCCESS")


if __name__ == "__main__":
    unittest.main()
