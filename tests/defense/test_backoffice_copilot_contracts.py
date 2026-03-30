from __future__ import annotations

import unittest

from traffic_master_ai.defense.backoffice_copilot import (
    AnalysisInput,
    BackofficeCopilotConfig,
    BackofficeCopilotWorkflowDependencies,
    PostReviewGraphState,
    PostReviewRunInput,
    build_backoffice_copilot_workflow,
)
from traffic_master_ai.defense.backoffice_copilot.core import (
    BackendRequest,
    PostReviewRunContext,
    SessionAnalysis,
    SessionReviewResult,
)


class BackofficeCopilotContractTests(unittest.TestCase):
    def test_task_1_config_and_state_keep_match_id_only_contract(self) -> None:
        config = BackofficeCopilotConfig(
            match_id="match-1",
            window_start_ms=100,
            window_end_ms=200,
            limit=50,
            use_raw_audit_fallback=True,
        )

        run_input = config.to_run_input()
        run_context = config.to_run_context()
        graph_state = config.to_graph_state()

        self.assertIsInstance(run_input, PostReviewRunInput)
        self.assertIsInstance(run_context, PostReviewRunContext)
        self.assertIsInstance(graph_state, PostReviewGraphState)
        self.assertEqual(run_input.match_id, "match-1")
        self.assertEqual(run_context.match_id, "match-1")
        self.assertEqual(graph_state.match_id, "match-1")
        self.assertFalse(hasattr(run_input, "review_run_id"))
        self.assertFalse(hasattr(run_context, "review_run_id"))
        self.assertFalse(hasattr(graph_state, "review_run_id"))

    def test_task_1_graph_state_exposes_fixed_public_fields(self) -> None:
        state = PostReviewGraphState.from_input(
            PostReviewRunInput(
                match_id="match-2",
                window_start_ms=1,
                window_end_ms=2,
                limit=3,
                use_raw_audit_fallback=False,
            )
        )

        self.assertIsInstance(state.analysis_input, AnalysisInput)
        self.assertEqual(state.candidate_sessions, [])
        self.assertEqual(state.session_analysis_list, [])
        self.assertEqual(state.review_results, [])
        self.assertEqual(state.summary_text, [])
        self.assertIsNone(state.post_review_runs_row)
        self.assertEqual(state.post_review_session_result_rows, [])
        self.assertIsNone(state.backend_request)
        self.assertIsNone(state.backend_response)
        self.assertEqual(state.warnings, [])
        self.assertEqual(state.errors, [])

    def test_import_surface_exposes_workflow_and_core_contracts(self) -> None:
        self.assertTrue(callable(build_backoffice_copilot_workflow))
        self.assertIsNotNone(BackofficeCopilotWorkflowDependencies)
        self.assertIsNotNone(BackendRequest)
        self.assertIsNotNone(SessionAnalysis)
        self.assertIsNotNone(SessionReviewResult)


if __name__ == "__main__":
    unittest.main()
