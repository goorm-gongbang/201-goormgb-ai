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
        # Evidence-driven fields
        self.assertEqual(summary_input["throttle_total"], 1)   # only sess-1 (suspicious)
        self.assertEqual(summary_input["challenge_fail_total"], 1)   # only sess-1
        tier_breakdown = summary_input["tier_breakdown"]
        self.assertIsInstance(tier_breakdown, dict)
        self.assertEqual(tier_breakdown.get("T2"), 1)   # sess-1
        self.assertEqual(tier_breakdown.get("T1"), 1)   # sess-2
        action_breakdown = summary_input["action_breakdown"]
        self.assertIsInstance(action_breakdown, dict)
        self.assertEqual(action_breakdown.get("THROTTLE"), 1)
        self.assertEqual(action_breakdown.get("NONE"), 1)

    def test_build_window_summary_input_zero_mitigations(self) -> None:
        """All-normal sessions produce zero throttle/challenge totals."""
        review_results = (
            SessionReviewResult(session_id="sess-x", review_result="NORMAL", evidence_summary="ok"),
        )
        session_analysis_list = (
            _session_analysis("sess-x", suspicious=False),
        )

        summary_input = build_window_summary_input(
            match_id="match-z",
            window_start_ms=0,
            window_end_ms=1,
            review_results=review_results,
            session_analysis_list=session_analysis_list,
        )

        self.assertEqual(summary_input["throttle_total"], 0)
        self.assertEqual(summary_input["challenge_fail_total"], 0)
        self.assertNotIn("T2", summary_input["tier_breakdown"])  # only T1

    def test_fallback_summary_includes_mitigation_counts(self) -> None:
        """Fallback line 2 must mention throttle and challenge counts when > 0."""
        from traffic_master_ai.defense.backoffice_copilot.summary.fallback import build_fallback_summary_text

        lines = build_fallback_summary_text({
            "match_id": "m1",
            "window_start_ms": 0,
            "window_end_ms": 600000,
            "candidate_count": 3,
            "reviewed_count": 3,
            "suspicious_count": 2,
            "normal_count": 1,
            "needs_raw_fallback_count": 0,
            "top_signals": [],
            "throttle_total": 4,
            "challenge_fail_total": 2,
            "tier_breakdown": {"T1": 1, "T2": 2},
            "action_breakdown": {"THROTTLE": 3, "NONE": 1},
        })

        self.assertEqual(len(lines), 3)
        self.assertIn("4 throttle event(s)", lines[1])
        self.assertIn("2 challenge failure(s)", lines[1])
        self.assertIn("T1:1", lines[2])
        self.assertIn("T2:2", lines[2])
        self.assertIn("THROTTLE:3", lines[2])

    def test_fallback_summary_no_mitigations_falls_back_to_signals(self) -> None:
        """When throttle/challenge totals are 0, line 2 falls back to top_signals."""
        from traffic_master_ai.defense.backoffice_copilot.summary.fallback import build_fallback_summary_text

        lines = build_fallback_summary_text({
            "match_id": "m2",
            "window_start_ms": 0,
            "window_end_ms": 600000,
            "candidate_count": 1,
            "reviewed_count": 1,
            "suspicious_count": 0,
            "normal_count": 1,
            "needs_raw_fallback_count": 0,
            "top_signals": [{"signal": "high_velocity", "count": 5}],
            "throttle_total": 0,
            "challenge_fail_total": 0,
            "tier_breakdown": {"T1": 1},
            "action_breakdown": {"NONE": 1},
        })

        self.assertIn("high_velocity (5)", lines[1])
        self.assertNotIn("throttle", lines[1].lower())

    def test_fallback_summary_no_mitigations_no_signals(self) -> None:
        """When no mitigations and no signals, line 2 is the 'no pattern' message."""
        from traffic_master_ai.defense.backoffice_copilot.summary.fallback import build_fallback_summary_text

        lines = build_fallback_summary_text({
            "match_id": "m3",
            "window_start_ms": 0,
            "window_end_ms": 600000,
            "candidate_count": 0,
            "reviewed_count": 0,
            "suspicious_count": 0,
            "normal_count": 0,
            "needs_raw_fallback_count": 0,
            "top_signals": [],
            "throttle_total": 0,
            "challenge_fail_total": 0,
            "tier_breakdown": {},
            "action_breakdown": {},
        })

        self.assertIn("No repeated suspicious signal", lines[1])
        # Line 3 falls back to raw-context message when no breakdown data
        self.assertIn("requiring additional raw context", lines[2])


if __name__ == "__main__":
    unittest.main()
