from __future__ import annotations

import unittest

from traffic_master_ai.defense.backoffice_copilot.analysis import build_session_analysis_list
from traffic_master_ai.defense.backoffice_copilot.core.models import DefenseAuditEventRow, SessionSummary
from traffic_master_ai.defense.backoffice_copilot.core.state import AnalysisInput
from traffic_master_ai.defense.backoffice_copilot.storage.validators import validate_session_analysis_json


class SessionAnalysisTests(unittest.TestCase):
    def test_build_session_analysis_without_fallback(self) -> None:
        candidate_sessions = (
            SessionSummary(
                session_id="sess-1",
                seen_t1=True,
                seen_t2=True,
                block_event_count=0,
                vqa_fail_count=1,
                throttle_event_count=1,
                latest_flow_state="F4M",
                latest_action="THROTTLE",
                latest_tier="T2",
                terminal_outcome="NOT_BLOCKED",
            ),
        )
        analysis_input = AnalysisInput(
            defense_audit_events=(
                DefenseAuditEventRow(
                    ts_ms=100,
                    trace_id="trace-1",
                    session_id="sess-1",
                    event_type="DEF_THROTTLE_APPLIED",
                    payload={
                        "flowState": "F3",
                        "serverDecision": {"riskTier": "T2", "action": "THROTTLE"},
                    },
                ),
                DefenseAuditEventRow(
                    ts_ms=110,
                    trace_id="trace-2",
                    session_id="sess-1",
                    event_type="S3_CHALLENGE_RESULT",
                    payload={
                        "flowState": "F4M",
                        "result": {
                            "status": "FAIL",
                            "reasonCode": "VQA_FAIL",
                            "terminalReason": "VQA_FAILURE",
                        },
                        "challenge": {"result": "FAIL"},
                        "serverDecision": {"riskTier": "T2", "action": "THROTTLE"},
                    },
                ),
            ),
            raw_audit_available=True,
        )

        analyses = build_session_analysis_list(
            candidate_sessions,
            analysis_input,
            window_start_ms=100,
            window_end_ms=200,
            max_workers=2,
        )

        self.assertEqual(len(analyses), 1)
        analysis = analyses[0]
        self.assertEqual(analysis.session_id, "sess-1")
        self.assertEqual(analysis.latest_tier, "T2")
        self.assertEqual(analysis.latest_action, "THROTTLE")
        self.assertEqual(analysis.terminal_outcome, "NOT_BLOCKED")
        self.assertFalse(analysis.needs_raw_fallback)
        self.assertIn("Reached T2 during session", analysis.suspicious_signals)
        self.assertIn("VQA failure observed", analysis.suspicious_signals)
        self.assertIn("Throttle applied during session", analysis.suspicious_signals)
        self.assertIn("Session reached T2 during evaluation.", analysis.timeline_summary)
        self.assertIn("Terminal reason recorded as VQA_FAILURE.", analysis.timeline_summary)
        validate_session_analysis_json(analysis)

    def test_limited_raw_fallback_uses_session_and_window_only(self) -> None:
        captured_calls: list[tuple[str, int, int, int]] = []

        def provider(
            session_id: str,
            window_start_ms: int,
            window_end_ms: int,
            limit: int,
        ) -> list[dict[str, object]]:
            captured_calls.append((session_id, window_start_ms, window_end_ms, limit))
            return [
                {
                    "tsMs": 120,
                    "traceId": "trace-fallback",
                    "sessionId": session_id,
                    "eventType": "S3_CHALLENGE_RESULT",
                    "flowState": "F4M",
                    "result": {
                        "status": "FAIL",
                        "reasonCode": "CHALLENGE_TIMEOUT",
                        "terminalReason": "CHALLENGE_TIMEOUT",
                    },
                    "challenge": {"result": "FAIL"},
                    "serverDecision": {"riskTier": "T1", "action": "NONE"},
                }
            ]

        candidate_sessions = (
            SessionSummary(
                session_id="sess-fallback",
                seen_t1=True,
                seen_t2=False,
                block_event_count=0,
                vqa_fail_count=0,
                throttle_event_count=0,
                latest_flow_state="F2",
                latest_action="NONE",
                latest_tier="T1",
                terminal_outcome="NOT_BLOCKED",
            ),
        )
        analysis_input = AnalysisInput(
            defense_audit_events=(
                DefenseAuditEventRow(
                    ts_ms=100,
                    trace_id="trace-1",
                    session_id="sess-fallback",
                    event_type="DEF_GUARD_SCORED",
                    payload={
                        "flowState": "F2",
                        "serverDecision": {"riskTier": "T1", "action": "NONE"},
                    },
                ),
            ),
            raw_audit_available=True,
        )

        analyses = build_session_analysis_list(
            candidate_sessions,
            analysis_input,
            window_start_ms=90,
            window_end_ms=150,
            raw_fallback_provider=provider,
            raw_fallback_limit=7,
        )

        self.assertEqual(captured_calls, [("sess-fallback", 90, 150, 7)])
        self.assertEqual(len(analyses), 1)
        analysis = analyses[0]
        self.assertFalse(analysis.needs_raw_fallback)
        self.assertIn("VQA failure observed", analysis.suspicious_signals)
        self.assertIn("Terminal reason observed: CHALLENGE_TIMEOUT", analysis.suspicious_signals)
        self.assertIn("Terminal reason recorded as CHALLENGE_TIMEOUT.", analysis.timeline_summary)
        validate_session_analysis_json(analysis)

    def test_missing_fallback_context_stays_visible_without_failure(self) -> None:
        candidate_sessions = (
            SessionSummary(
                session_id="sess-missing",
                seen_t1=True,
                seen_t2=False,
                block_event_count=0,
                vqa_fail_count=0,
                throttle_event_count=0,
                latest_flow_state="F2",
                latest_action="NONE",
                latest_tier="T1",
                terminal_outcome="NOT_BLOCKED",
            ),
        )
        analysis_input = AnalysisInput(
            defense_audit_events=(
                DefenseAuditEventRow(
                    ts_ms=100,
                    trace_id="trace-1",
                    session_id="sess-missing",
                    event_type="DEF_GUARD_SCORED",
                    payload={
                        "flowState": "F2",
                        "serverDecision": {"riskTier": "T1", "action": "NONE"},
                    },
                ),
            ),
            raw_audit_available=False,
        )

        analyses = build_session_analysis_list(
            candidate_sessions,
            analysis_input,
            window_start_ms=90,
            window_end_ms=150,
        )

        self.assertEqual(len(analyses), 1)
        analysis = analyses[0]
        self.assertTrue(analysis.needs_raw_fallback)
        self.assertEqual(analysis.suspicious_signals, [])
        self.assertIn(
            "Additional raw context is unavailable because limited decision_audit fallback is disabled.",
            analysis.timeline_summary,
        )
        validate_session_analysis_json(analysis)

    def test_fallback_provider_failure_keeps_reason_visible_without_crashing(self) -> None:
        candidate_sessions = (
            SessionSummary(
                session_id="sess-error",
                seen_t1=True,
                seen_t2=False,
                block_event_count=0,
                vqa_fail_count=0,
                throttle_event_count=0,
                latest_flow_state="F2",
                latest_action="NONE",
                latest_tier="T1",
                terminal_outcome="NOT_BLOCKED",
            ),
        )
        analysis_input = AnalysisInput(
            defense_audit_events=(
                DefenseAuditEventRow(
                    ts_ms=100,
                    trace_id="trace-1",
                    session_id="sess-error",
                    event_type="DEF_GUARD_SCORED",
                    payload={
                        "flowState": "F2",
                        "serverDecision": {"riskTier": "T1", "action": "NONE"},
                    },
                ),
            ),
            raw_audit_available=True,
        )

        def provider(*_args):
            raise RuntimeError("unexpected provider failure")

        analyses = build_session_analysis_list(
            candidate_sessions,
            analysis_input,
            window_start_ms=90,
            window_end_ms=150,
            raw_fallback_provider=provider,
        )

        self.assertEqual(len(analyses), 1)
        analysis = analyses[0]
        self.assertTrue(analysis.needs_raw_fallback)
        self.assertIn(
            "Limited decision_audit fallback failed within the requested session window (RuntimeError).",
            analysis.timeline_summary,
        )
        validate_session_analysis_json(analysis)


if __name__ == "__main__":
    unittest.main()
