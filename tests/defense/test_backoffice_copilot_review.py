from __future__ import annotations

import unittest

from traffic_master_ai.defense.backoffice_copilot.core.models import SessionAnalysis
from traffic_master_ai.defense.backoffice_copilot.review import (
    LlmOutputValidationError,
    build_fallback_review_result,
    build_llm_review_input,
    execute_session_reviews,
    parse_llm_review_output,
)


def _analysis(
    session_id: str,
    *,
    seen_t2: bool = False,
    vqa_fail_count: int = 0,
    throttle_event_count: int = 0,
    latest_action: str = "NONE",
) -> SessionAnalysis:
    return SessionAnalysis(
        session_id=session_id,
        latest_flow_state="F4M",
        latest_action=latest_action,
        latest_tier="T2" if seen_t2 else "T1",
        terminal_outcome="NOT_BLOCKED",
        seen_t1=True,
        seen_t2=seen_t2,
        vqa_fail_count=vqa_fail_count,
        throttle_event_count=throttle_event_count,
        suspicious_signals=["Reached T2 during session"] if seen_t2 else [],
        timeline_summary=["Session reached T1 during evaluation."],
        needs_raw_fallback=False,
    )


class ReviewTests(unittest.TestCase):
    def test_output_parser_accepts_only_allowed_contract(self) -> None:
        parsed = parse_llm_review_output(
            {"review_result": "SUSPICIOUS", "evidence_summary": "Observed T2 trace."}
        )

        self.assertEqual(parsed.review_result, "SUSPICIOUS")
        self.assertEqual(parsed.evidence_summary, "Observed T2 trace.")

        with self.assertRaises(LlmOutputValidationError):
            parse_llm_review_output({"review_result": "UNSURE", "evidence_summary": "bad"})
        with self.assertRaises(LlmOutputValidationError):
            parse_llm_review_output({"review_result": "NORMAL", "evidence_summary": "   "})

    def test_fallback_result_is_traceable(self) -> None:
        result, warning = build_fallback_review_result(
            _analysis("sess-fallback", seen_t2=True, vqa_fail_count=1),
            reason="adapter_missing",
        )

        self.assertEqual(result.session_id, "sess-fallback")
        self.assertEqual(result.review_result, "SUSPICIOUS")
        self.assertIn("Rule-based fallback", result.evidence_summary)
        self.assertEqual(warning.code, "llm_review_fallback_applied")
        self.assertEqual(
            warning.context,
            {
                "session_id": "sess-fallback",
                "fallback_reason": "adapter_missing",
                "fallback_applied": True,
            },
        )

    def test_executor_uses_fallback_for_invalid_outputs_and_preserves_order(self) -> None:
        session_analysis_list = (
            _analysis("sess-1", seen_t2=True),
            _analysis("sess-2", throttle_event_count=1, latest_action="THROTTLE"),
            _analysis("sess-3"),
        )

        def adapter(llm_input):
            if llm_input.session_analysis.session_id == "sess-1":
                return {"review_result": "SUSPICIOUS", "evidence_summary": "Observed T2 trace."}
            if llm_input.session_analysis.session_id == "sess-2":
                return {"review_result": "REVIEW_NEEDED", "evidence_summary": "bad"}
            raise TimeoutError("timeout")

        execution = execute_session_reviews(
            match_id="match-1",
            window_start_ms=1,
            window_end_ms=2,
            session_analysis_list=session_analysis_list,
            llm_review_adapter=adapter,
            max_workers=3,
        )

        self.assertEqual(
            [result.session_id for result in execution.review_results],
            ["sess-1", "sess-2", "sess-3"],
        )
        self.assertEqual(
            [result.review_result for result in execution.review_results],
            ["SUSPICIOUS", "SUSPICIOUS", "NORMAL"],
        )
        self.assertEqual(len(execution.warnings), 2)
        self.assertEqual(
            [warning.context["session_id"] for warning in execution.warnings],
            ["sess-2", "sess-3"],
        )
        self.assertIn("output_validation_failed", execution.warnings[0].context["fallback_reason"])
        self.assertEqual(execution.warnings[1].context["fallback_reason"], "adapter_timeout")

    def test_input_builder_uses_fixed_envelope(self) -> None:
        session_analysis = _analysis("sess-input")

        llm_input = build_llm_review_input(
            match_id="match-1",
            window_start_ms=100,
            window_end_ms=200,
            session_analysis=session_analysis,
        )

        self.assertEqual(llm_input.match_id, "match-1")
        self.assertEqual(llm_input.window_start_ms, 100)
        self.assertEqual(llm_input.window_end_ms, 200)
        self.assertEqual(llm_input.session_analysis.session_id, "sess-input")
        self.assertEqual(tuple(llm_input.task.labels), ("NORMAL", "SUSPICIOUS"))
        self.assertEqual(tuple(llm_input.task.required_fields), ("review_result", "evidence_summary"))


if __name__ == "__main__":
    unittest.main()
