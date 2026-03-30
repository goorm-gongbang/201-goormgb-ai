from __future__ import annotations

import unittest

from traffic_master_ai.defense.backoffice_copilot.core.models import SessionAnalysis, SessionReviewResult
from traffic_master_ai.defense.backoffice_copilot.storage.validators import validate_summary_text_json
from traffic_master_ai.defense.backoffice_copilot.summary import (
    SummaryOutputValidationError,
    build_window_summary_input,
    generate_summary_text,
    parse_summary_text,
)


def _session_analysis(session_id: str, *, suspicious: bool, needs_raw_fallback: bool = False) -> SessionAnalysis:
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
        suspicious_signals=["Reached T2 during session", "VQA failure observed"] if suspicious else [],
        timeline_summary=["Session reached T2 during evaluation."] if suspicious else ["Session reached T1 during evaluation."],
        needs_raw_fallback=needs_raw_fallback,
    )


class SummaryTests(unittest.TestCase):
    def test_generate_summary_text_uses_valid_adapter_output(self) -> None:
        review_results = (
            SessionReviewResult(
                session_id="sess-1",
                review_result="SUSPICIOUS",
                evidence_summary="Observed T2 trace.",
            ),
            SessionReviewResult(
                session_id="sess-2",
                review_result="NORMAL",
                evidence_summary="Observed only baseline activity.",
            ),
        )
        session_analysis_list = (
            _session_analysis("sess-1", suspicious=True),
            _session_analysis("sess-2", suspicious=False),
        )

        result = generate_summary_text(
            match_id="match-1",
            window_start_ms=100,
            window_end_ms=200,
            review_results=review_results,
            session_analysis_list=session_analysis_list,
            summary_adapter=lambda _: {
                "summary_text": [
                    "Window reviewed 2 sessions.",
                    "One session remained suspicious.",
                    "No additional storage-side information is included.",
                ]
            },
        )

        self.assertEqual(result.warnings, ())
        self.assertEqual(len(result.summary_text), 3)
        validate_summary_text_json(result.summary_text)

    def test_generate_summary_text_falls_back_when_adapter_fails(self) -> None:
        review_results = (
            SessionReviewResult(
                session_id="sess-1",
                review_result="SUSPICIOUS",
                evidence_summary="Observed T2 trace.",
            ),
        )
        session_analysis_list = (
            _session_analysis("sess-1", suspicious=True, needs_raw_fallback=True),
        )

        result = generate_summary_text(
            match_id="match-2",
            window_start_ms=10,
            window_end_ms=20,
            review_results=review_results,
            session_analysis_list=session_analysis_list,
            summary_adapter=lambda _: {"summary_text": ["too", "short"]},
        )

        self.assertEqual(len(result.summary_text), 3)
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.warnings[0].code, "window_summary_fallback_applied")
        self.assertIn("output_validation_failed", result.warnings[0].context["fallback_reason"])
        self.assertIn("reviewed 1 of 1 candidate sessions", result.summary_text[0])
        validate_summary_text_json(result.summary_text)

    def test_parse_summary_text_rejects_non_three_line_shapes(self) -> None:
        with self.assertRaises(SummaryOutputValidationError):
            parse_summary_text({"summary_text": "single string"})
        with self.assertRaises(SummaryOutputValidationError):
            parse_summary_text(["one", "two"])

    def test_build_window_summary_input_assembles_run_level_counts(self) -> None:
        review_results = (
            SessionReviewResult(
                session_id="sess-1",
                review_result="SUSPICIOUS",
                evidence_summary="Observed T2 trace.",
            ),
            SessionReviewResult(
                session_id="sess-2",
                review_result="NORMAL",
                evidence_summary="Observed only baseline activity.",
            ),
        )
        session_analysis_list = (
            _session_analysis("sess-1", suspicious=True, needs_raw_fallback=True),
            _session_analysis("sess-2", suspicious=False, needs_raw_fallback=False),
        )

        summary_input = build_window_summary_input(
            match_id="match-3",
            window_start_ms=1,
            window_end_ms=2,
            review_results=review_results,
            session_analysis_list=session_analysis_list,
        )

        self.assertEqual(summary_input["candidate_count"], 2)
        self.assertEqual(summary_input["reviewed_count"], 2)
        self.assertEqual(summary_input["suspicious_count"], 1)
        self.assertEqual(summary_input["normal_count"], 1)
        self.assertEqual(summary_input["needs_raw_fallback_count"], 1)
        self.assertTrue(summary_input["top_signals"])


if __name__ == "__main__":
    unittest.main()
