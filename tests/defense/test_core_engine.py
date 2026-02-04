"""Unit tests for Defense PoC-0 core transition engine."""

import pytest
from typing import List

from traffic_master_ai.defense.d0_poc.core import EventSource, FlowState
from traffic_master_ai.defense.d0_poc.orchestrator.harness import EngineHarness
from traffic_master_ai.defense.d0_poc.signals import (
    DEF_BLOCKED,
    DEF_CHALLENGE_FORCED,
    FLOW_START,
    SIGNAL_TOKEN_MISMATCH,
    STAGE_1_ENTRY_CLICKED,
    STAGE_2_QUEUE_PASSED,
    STAGE_3_CHALLENGE_FAILED,
    STAGE_3_CHALLENGE_PASSED,
    STAGE_4_SECTION_SELECTED,
    STAGE_5_CONFIRM_CLICKED,
    STAGE_6_PAYMENT_COMPLETED,
)
from traffic_master_ai.defense.d0_poc.signals.events import Event


def make_event(event_type: str, seq: int = 0) -> Event:
    """Factory helper to create test events.

    Args:
        event_type: The canonical event type string.
        seq: Optional sequence number for unique event_id.

    Returns:
        Event object with test defaults.
    """
    return Event(
        event_id=f"test-{seq}",
        ts_ms=1000 + seq,
        type=event_type,
        source=EventSource.BACKEND,
        session_id="test-session",
        payload={},
    )


def make_events(event_types: List[str]) -> List[Event]:
    """Factory helper to create a list of test events.

    Args:
        event_types: List of canonical event type strings.

    Returns:
        List of Event objects.
    """
    return [make_event(t, seq=i) for i, t in enumerate(event_types)]


class TestHappyPath:
    """Test successful flow completion."""

    def test_happy_path_completes_with_done(self) -> None:
        """Happy path should complete with final_state=SX and reason=DONE."""
        events = make_events([
            FLOW_START,
            STAGE_1_ENTRY_CLICKED,
            STAGE_2_QUEUE_PASSED,
            STAGE_3_CHALLENGE_PASSED,
            STAGE_4_SECTION_SELECTED,
            STAGE_5_CONFIRM_CLICKED,
            STAGE_6_PAYMENT_COMPLETED,
        ])

        harness = EngineHarness()
        result = harness.run(events)

        assert result["final_state"] == "SX"
        assert len(result["trace"]) == 7

        # Last trace entry should have DONE reason
        last_trace = result["trace"][-1]
        assert last_trace["reason"] == "DONE"
        assert last_trace["to"] == "SX"


class TestChallengeBlock:
    """Test challenge failure threshold blocking."""

    def test_challenge_fail_threshold_blocks(self) -> None:
        """Three challenge failures should trigger BLOCKED."""
        events = make_events([
            FLOW_START,
            STAGE_1_ENTRY_CLICKED,
            STAGE_2_QUEUE_PASSED,
            STAGE_3_CHALLENGE_FAILED,  # fail 1
            STAGE_3_CHALLENGE_FAILED,  # fail 2
            STAGE_3_CHALLENGE_FAILED,  # fail 3 -> threshold reached
        ])

        harness = EngineHarness()
        result = harness.run(events)

        assert result["final_state"] == "SX"

        # Find trace entry with DEF_BLOCKED action
        blocked_actions = [
            t for t in result["trace"]
            if DEF_BLOCKED in t["actions"]
        ]
        assert len(blocked_actions) > 0, "DEF_BLOCKED action should exist in trace"

        # Last trace should have BLOCKED reason
        last_trace = result["trace"][-1]
        assert last_trace["reason"] == "BLOCKED"


class TestInterruptAndReturn:
    """Test S3 interrupt and return-to logic."""

    def test_interrupt_from_s4_returns_to_s4(self) -> None:
        """DEF_CHALLENGE_FORCED from S4 should save state, then return to S4."""
        events = make_events([
            FLOW_START,
            STAGE_1_ENTRY_CLICKED,
            STAGE_2_QUEUE_PASSED,
            STAGE_3_CHALLENGE_PASSED,  # -> S4
            DEF_CHALLENGE_FORCED,      # S4 -> S3, save last_non_security_state
            STAGE_3_CHALLENGE_PASSED,  # S3 -> S4 (return to)
            STAGE_4_SECTION_SELECTED,  # S4 -> S5
            STAGE_5_CONFIRM_CLICKED,   # S5 -> S6
            STAGE_6_PAYMENT_COMPLETED, # S6 -> SX
        ])

        harness = EngineHarness()
        result = harness.run(events)

        assert result["final_state"] == "SX"

        # Find S4 -> S3 transition (interrupt)
        interrupt_traces = [
            t for t in result["trace"]
            if t["from"] == "S4" and t["to"] == "S3"
        ]
        assert len(interrupt_traces) == 1, "Should have S4 -> S3 interrupt transition"

        # Find S3 -> S4 transition (return)
        return_traces = [
            t for t in result["trace"]
            if t["from"] == "S3" and t["to"] == "S4"
        ]
        # Should have at least one S3 -> S4 (the return after interrupt)
        assert len(return_traces) >= 1, "Should have S3 -> S4 return transition"


class TestTokenMismatch:
    """Test immediate blocking on token mismatch."""

    def test_token_mismatch_immediately_blocks(self) -> None:
        """SIGNAL_TOKEN_MISMATCH should immediately terminate with BLOCKED."""
        events = make_events([
            FLOW_START,
            STAGE_1_ENTRY_CLICKED,
            SIGNAL_TOKEN_MISMATCH,  # Immediate block
        ])

        harness = EngineHarness()
        result = harness.run(events)

        assert result["final_state"] == "SX"

        # Last trace should have BLOCKED reason
        last_trace = result["trace"][-1]
        assert last_trace["reason"] == "BLOCKED"

        # DEF_BLOCKED action should be present
        assert DEF_BLOCKED in last_trace["actions"], "DEF_BLOCKED action should be present"

        # Should terminate after token mismatch
        assert last_trace["event"] == SIGNAL_TOKEN_MISMATCH
