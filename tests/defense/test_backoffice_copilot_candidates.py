from __future__ import annotations

import unittest

from traffic_master_ai.defense.backoffice_copilot.analysis import build_candidate_selection
from traffic_master_ai.defense.backoffice_copilot.core.models import DefenseAuditEventRow, SessionSummary
from traffic_master_ai.defense.backoffice_copilot.core.state import AnalysisInput


class CandidateSelectionTests(unittest.TestCase):
    def test_build_candidate_selection_keeps_summaries_and_subset(self) -> None:
        analysis_input = AnalysisInput(
            defense_audit_events=(
                DefenseAuditEventRow(
                    ts_ms=100,
                    trace_id="trace-1",
                    session_id="sess-candidate",
                    event_type="DEF_GUARD_SCORED",
                    payload={
                        "flowState": "F2",
                        "serverDecision": {"riskTier": "T1", "action": "NONE"},
                    },
                ),
                DefenseAuditEventRow(
                    ts_ms=110,
                    trace_id="trace-2",
                    session_id="sess-candidate",
                    event_type="DEF_THROTTLE_APPLIED",
                    payload={
                        "flowState": "F3",
                        "serverDecision": {"riskTier": "T2", "action": "THROTTLE"},
                    },
                ),
                DefenseAuditEventRow(
                    ts_ms=120,
                    trace_id="trace-3",
                    session_id="sess-candidate",
                    event_type="S3_CHALLENGE_RESULT",
                    payload={
                        "flowState": "F4M",
                        "result": {"status": "FAIL", "reasonCode": "VQA_FAIL"},
                        "challenge": {"result": "FAIL"},
                        "serverDecision": {"riskTier": "T2", "action": "NONE"},
                    },
                ),
                DefenseAuditEventRow(
                    ts_ms=130,
                    trace_id="trace-4",
                    session_id="sess-blocked",
                    event_type="DEF_GUARD_SCORED",
                    payload={
                        "flowState": "F2",
                        "serverDecision": {"riskTier": "T1", "action": "NONE"},
                    },
                ),
                DefenseAuditEventRow(
                    ts_ms=140,
                    trace_id="trace-5",
                    session_id="sess-blocked",
                    event_type="DEF_BLOCK_ENFORCED",
                    payload={
                        "flowState": "FX",
                        "serverDecision": {"riskTier": "T3", "action": "BLOCK"},
                    },
                ),
                DefenseAuditEventRow(
                    ts_ms=150,
                    trace_id="trace-6",
                    session_id="sess-blocked",
                    event_type="S3_CHALLENGE_HALTED",
                    payload={
                        "flowState": "F4M",
                        "result": {
                            "terminalReason": "CHALLENGE_TEMPORARILY_LOCKED",
                            "reasonCode": "CHALLENGE_TEMPORARILY_LOCKED",
                        },
                        "serverDecision": {"riskTier": "T2", "action": "THROTTLE"},
                    },
                ),
            ),
            raw_audit_available=True,
        )

        selection = build_candidate_selection(analysis_input)

        self.assertEqual(len(selection.session_summaries), 2)
        self.assertTrue(all(isinstance(item, SessionSummary) for item in selection.session_summaries))
        self.assertEqual(
            [summary.session_id for summary in selection.session_summaries],
            ["sess-candidate", "sess-blocked"],
        )
        self.assertEqual(
            [summary.session_id for summary in selection.candidate_sessions],
            ["sess-candidate"],
        )
        candidate_summary = selection.candidate_sessions[0]
        self.assertTrue(candidate_summary.seen_t1)
        self.assertTrue(candidate_summary.seen_t2)
        self.assertEqual(candidate_summary.block_event_count, 0)
        self.assertEqual(candidate_summary.vqa_fail_count, 1)
        self.assertEqual(candidate_summary.throttle_event_count, 1)
        self.assertEqual(candidate_summary.latest_tier, "T2")
        self.assertEqual(candidate_summary.terminal_outcome, "NOT_BLOCKED")
        self.assertEqual(selection.warnings, ())

    def test_zero_candidates_returns_warning_only(self) -> None:
        analysis_input = AnalysisInput(
            defense_audit_events=(
                DefenseAuditEventRow(
                    ts_ms=100,
                    trace_id="trace-1",
                    session_id="sess-blocked",
                    event_type="DEF_BLOCK_ENFORCED",
                    payload={
                        "flowState": "FX",
                        "serverDecision": {"riskTier": "T3", "action": "BLOCK"},
                    },
                ),
            ),
            raw_audit_available=False,
        )

        selection = build_candidate_selection(analysis_input)

        self.assertEqual(len(selection.session_summaries), 1)
        self.assertEqual(selection.candidate_sessions, ())
        self.assertEqual(len(selection.warnings), 1)
        self.assertEqual(selection.warnings[0].code, "candidate_sessions_empty")
        self.assertEqual(
            selection.warnings[0].context,
            {"session_summary_count": 1, "raw_audit_available": False},
        )


if __name__ == "__main__":
    unittest.main()
