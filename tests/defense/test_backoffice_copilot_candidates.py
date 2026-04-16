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


class WideningCandidateSelectionTests(unittest.TestCase):
    """Tests for the widened is_candidate_session() protection-context path.

    Scenario: runtime has already throttled or challenged a session, but tier
    data in the audit window is absent or only T0.  The session should now
    qualify as a candidate so the LLM can review it.
    """

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_throttle_only_events(session_id: str) -> tuple:
        """Session that was throttled but shows no T1/T2 tier stamp."""
        return (
            DefenseAuditEventRow(
                ts_ms=200,
                trace_id="t-throttle-1",
                session_id=session_id,
                event_type="DEF_THROTTLE_APPLIED",
                payload={
                    "flowState": "F3",
                    "serverDecision": {"riskTier": "T0", "action": "THROTTLE"},
                    "terminal_outcome": "NOT_BLOCKED",
                },
            ),
        )

    @staticmethod
    def _make_challenge_fail_events(session_id: str) -> tuple:
        """Session with a challenge failure but no explicit T1/T2 stamp."""
        return (
            DefenseAuditEventRow(
                ts_ms=300,
                trace_id="t-vqa-1",
                session_id=session_id,
                event_type="S3_CHALLENGE_RESULT",
                payload={
                    "flowState": "F2",
                    "challenge": {"result": "FAIL"},
                    "result": {"status": "FAIL", "reasonCode": "VQA_FAIL"},
                    "serverDecision": {"riskTier": "T0", "action": "NONE"},
                    "terminal_outcome": "NOT_BLOCKED",
                },
            ),
        )

    @staticmethod
    def _make_blocked_session_events(session_id: str) -> tuple:
        """Blocked session — must still be excluded even with throttle context."""
        return (
            DefenseAuditEventRow(
                ts_ms=400,
                trace_id="t-block-1",
                session_id=session_id,
                event_type="DEF_THROTTLE_APPLIED",
                payload={
                    "flowState": "F2",
                    "serverDecision": {"riskTier": "T1", "action": "THROTTLE"},
                },
            ),
            DefenseAuditEventRow(
                ts_ms=410,
                trace_id="t-block-2",
                session_id=session_id,
                event_type="DEF_BLOCK_ENFORCED",
                payload={
                    "flowState": "FX",
                    "serverDecision": {"riskTier": "T3", "action": "BLOCK"},
                },
            ),
        )

    @staticmethod
    def _make_t3_session_events(session_id: str) -> tuple:
        """T3 session — must still be excluded even with throttle context."""
        return (
            DefenseAuditEventRow(
                ts_ms=500,
                trace_id="t-t3-throttle",
                session_id=session_id,
                event_type="DEF_THROTTLE_APPLIED",
                payload={
                    "flowState": "F3",
                    "serverDecision": {"riskTier": "T3", "action": "THROTTLE"},
                },
            ),
        )

    # ------------------------------------------------------------------
    # inclusion tests (widened path)
    # ------------------------------------------------------------------

    def test_throttle_only_session_is_candidate(self) -> None:
        """A session that was throttled (no T1/T2 stamp) should now be a candidate."""
        events = self._make_throttle_only_events("sess-throttle-only")
        analysis_input = AnalysisInput(
            defense_audit_events=events,
            raw_audit_available=False,
        )
        selection = build_candidate_selection(analysis_input)

        candidate_ids = [s.session_id for s in selection.candidate_sessions]
        self.assertIn(
            "sess-throttle-only",
            candidate_ids,
            "Throttled session must be a candidate even without explicit T1/T2 tier data",
        )

    def test_challenge_fail_session_is_candidate(self) -> None:
        """A session with a challenge failure (no T1/T2 stamp) should be a candidate."""
        events = self._make_challenge_fail_events("sess-vqa-fail")
        analysis_input = AnalysisInput(
            defense_audit_events=events,
            raw_audit_available=False,
        )
        selection = build_candidate_selection(analysis_input)

        candidate_ids = [s.session_id for s in selection.candidate_sessions]
        self.assertIn(
            "sess-vqa-fail",
            candidate_ids,
            "Challenge-failed session must be a candidate even without T1/T2 tier data",
        )

    # ------------------------------------------------------------------
    # exclusion tests (safety invariants preserved)
    # ------------------------------------------------------------------

    def test_blocked_session_excluded_even_with_throttle(self) -> None:
        """A session that was blocked must be excluded regardless of throttle count."""
        events = self._make_blocked_session_events("sess-blocked-with-throttle")
        analysis_input = AnalysisInput(
            defense_audit_events=events,
            raw_audit_available=False,
        )
        selection = build_candidate_selection(analysis_input)

        candidate_ids = [s.session_id for s in selection.candidate_sessions]
        self.assertNotIn(
            "sess-blocked-with-throttle",
            candidate_ids,
            "Blocked sessions must always be excluded from candidates",
        )

    def test_t3_session_excluded_even_with_throttle(self) -> None:
        """A session at T3 must be excluded regardless of other context signals."""
        events = self._make_t3_session_events("sess-t3-throttle")
        analysis_input = AnalysisInput(
            defense_audit_events=events,
            raw_audit_available=False,
        )
        selection = build_candidate_selection(analysis_input)

        candidate_ids = [s.session_id for s in selection.candidate_sessions]
        self.assertNotIn(
            "sess-t3-throttle",
            candidate_ids,
            "T3 sessions must always be excluded from candidates",
        )

    def test_candidate_count_increases_with_widened_selection(self) -> None:
        """Mixed input: widened selection must produce more candidates than old logic."""
        all_events = (
            # throttle-only session (NEW: would now be included)
            *self._make_throttle_only_events("sess-new-throttle"),
            # challenge-fail session (NEW: would now be included)
            *self._make_challenge_fail_events("sess-new-challenge"),
            # blocked session (must still be excluded)
            *self._make_blocked_session_events("sess-always-blocked"),
        )
        analysis_input = AnalysisInput(
            defense_audit_events=all_events,
            raw_audit_available=False,
        )
        selection = build_candidate_selection(analysis_input)

        candidate_ids = {s.session_id for s in selection.candidate_sessions}
        # Both protection-context sessions must be included
        self.assertIn("sess-new-throttle", candidate_ids)
        self.assertIn("sess-new-challenge", candidate_ids)
        # Blocked session must not be included
        self.assertNotIn("sess-always-blocked", candidate_ids)
        # At least 2 candidates from 3 sessions
        self.assertGreaterEqual(len(selection.candidate_sessions), 2)

    # ------------------------------------------------------------------
    # regression: original passing session still works
    # ------------------------------------------------------------------

    def test_original_t1_t2_candidate_still_passes(self) -> None:
        """Regression: a session with explicit T1+T2 signals still passes."""
        events = (
            DefenseAuditEventRow(
                ts_ms=100,
                trace_id="orig-1",
                session_id="sess-original",
                event_type="DEF_GUARD_SCORED",
                payload={"serverDecision": {"riskTier": "T1", "action": "NONE"}},
            ),
            DefenseAuditEventRow(
                ts_ms=110,
                trace_id="orig-2",
                session_id="sess-original",
                event_type="DEF_THROTTLE_APPLIED",
                payload={"serverDecision": {"riskTier": "T2", "action": "THROTTLE"}},
            ),
        )
        analysis_input = AnalysisInput(
            defense_audit_events=events,
            raw_audit_available=False,
        )
        selection = build_candidate_selection(analysis_input)

        candidate_ids = [s.session_id for s in selection.candidate_sessions]
        self.assertIn("sess-original", candidate_ids)


if __name__ == "__main__":
    unittest.main()
