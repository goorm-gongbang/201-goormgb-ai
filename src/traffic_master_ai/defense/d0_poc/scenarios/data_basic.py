"""Standard acceptance test scenarios (Happy Path) for Defense PoC-0.

Contains SCN-01 through SCN-06 covering basic flow, challenge, interrupt,
timeout, seat-taken, and sandbox scenarios.
"""

from typing import List, Optional

from ..core import DefenseTier, EventSource, FlowState
from ..signals import (
    DEF_CHALLENGE_FORCED,
    DEF_SANDBOXED,
    FLOW_START,
    SIGNAL_REPETITIVE_PATTERN,
    STAGE_1_ENTRY_CLICKED,
    STAGE_2_QUEUE_PASSED,
    STAGE_3_CHALLENGE_PASSED,
    STAGE_4_SECTION_SELECTED,
    STAGE_5_CONFIRM_CLICKED,
    STAGE_5_SEAT_TAKEN,
    STAGE_6_PAYMENT_COMPLETED,
    TIME_COOLDOWN_EXPIRED,
    TIME_TIMEOUT,
)
from ..signals.events import Event
from .schema import Scenario, ScenarioStep


# =============================================================================
# Event Factory Helpers
# =============================================================================


class EventFactory:
    """Factory for creating test events with auto-incrementing IDs and timestamps."""

    def __init__(self, session_id: str = "test-session", base_ts: int = 1000000) -> None:
        """Initialize factory.

        Args:
            session_id: Default session ID for all events.
            base_ts: Base timestamp in milliseconds.
        """
        self._session_id = session_id
        self._base_ts = base_ts
        self._seq = 0

    def make(
        self,
        event_type: str,
        source: EventSource = EventSource.PAGE,
        payload: Optional[dict] = None,
    ) -> Event:
        """Create an event with auto-generated ID and timestamp.

        Args:
            event_type: The canonical event type string.
            source: Event source (default: PAGE).
            payload: Optional payload dict.

        Returns:
            Event object with sequential ID and timestamp.
        """
        self._seq += 1
        return Event(
            event_id=f"evt-{self._seq:04d}",
            ts_ms=self._base_ts + (self._seq * 1000),
            type=event_type,
            source=source,
            session_id=self._session_id,
            payload=payload or {},
        )

    def reset(self) -> None:
        """Reset the sequence counter."""
        self._seq = 0


def step(
    event: Event,
    description: str,
    expected_state: Optional[FlowState] = None,
    expected_tier: Optional[DefenseTier] = None,
    expected_actions: Optional[List[str]] = None,
) -> ScenarioStep:
    """Shorthand helper to create a ScenarioStep.

    Args:
        event: Input event.
        description: Human-readable description.
        expected_state: Expected FlowState after step.
        expected_tier: Expected DefenseTier after step.
        expected_actions: Expected action types (e.g., ["THROTTLE"]).

    Returns:
        ScenarioStep instance.
    """
    return ScenarioStep(
        input_event=event,
        description=description,
        expected_state=expected_state,
        expected_tier=expected_tier,
        expected_actions=expected_actions,
    )


# =============================================================================
# SCN-01: Happy Path (No Challenge)
# =============================================================================

def build_scn_01_happy_path() -> Scenario:
    """SCN-01: Complete flow S0->S1->S2->S3->S4->S5->S6->SX without issues.

    Validates normal state progression with no challenges or failures.
    """
    f = EventFactory(session_id="scn-01")

    return Scenario(
        id="SCN-01",
        title="Happy Path - Complete Flow Without Challenge",
        steps=[
            step(
                f.make(FLOW_START),
                "Start the booking flow",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_1_ENTRY_CLICKED),
                "Click entry button to proceed to queue",
                expected_state=FlowState.S2,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_2_QUEUE_PASSED),
                "Pass queue and enter challenge stage",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_3_CHALLENGE_PASSED),
                "Pass challenge and proceed to section selection",
                expected_state=FlowState.S4,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_4_SECTION_SELECTED),
                "Select section and enter seat map",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_CONFIRM_CLICKED),
                "Confirm seat selection and enter payment",
                expected_state=FlowState.S6,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_6_PAYMENT_COMPLETED),
                "Complete payment and finish flow",
                expected_state=FlowState.SX,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
        ],
    )


# =============================================================================
# SCN-02: Challenge Pass (T1 -> Challenge -> Pass)
# =============================================================================

def build_scn_02_challenge_pass() -> Scenario:
    """SCN-02: T1 escalation then challenge pass.

    Validates that suspicious pattern triggers T1 and challenge still passes.
    """
    f = EventFactory(session_id="scn-02")

    return Scenario(
        id="SCN-02",
        title="Challenge Pass - T1 Escalation Then Normal Flow",
        steps=[
            step(
                f.make(FLOW_START),
                "Start the booking flow",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Trigger repetitive pattern signal -> T1 escalation",
                expected_state=FlowState.S1,  # State unchanged
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],  # T1 action
            ),
            step(
                f.make(STAGE_1_ENTRY_CLICKED),
                "Click entry to proceed (while T1)",
                expected_state=FlowState.S2,
                expected_tier=DefenseTier.T1,
                expected_actions=[],  # No new actions
            ),
            step(
                f.make(STAGE_2_QUEUE_PASSED),
                "Pass queue and proceed to challenge",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T1,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_3_CHALLENGE_PASSED),
                "Pass challenge at T1",
                expected_state=FlowState.S4,
                expected_tier=DefenseTier.T1,
                expected_actions=[],
            ),
        ],
    )


# =============================================================================
# SCN-03: S3 Interrupt (DEF_CHALLENGE_FORCED)
# =============================================================================

def build_scn_03_interrupt() -> Scenario:
    """SCN-03: Interrupt at S2 with DEF_CHALLENGE_FORCED -> S3 -> Pass -> Return to S2.

    Validates interrupt handling and return-to logic.
    """
    f = EventFactory(session_id="scn-03")

    return Scenario(
        id="SCN-03",
        title="S3 Interrupt - Challenge Forced Then Return",
        steps=[
            step(
                f.make(FLOW_START),
                "Start the booking flow",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_1_ENTRY_CLICKED),
                "Click entry to proceed to queue",
                expected_state=FlowState.S2,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(DEF_CHALLENGE_FORCED),
                "Force challenge interrupt while in S2 -> go to S3",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_3_CHALLENGE_PASSED),
                "Pass challenge -> return to S2 (saved state)",
                expected_state=FlowState.S2,  # Return to saved state
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_2_QUEUE_PASSED),
                "Continue from S2 -> S3 naturally",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
        ],
    )


# =============================================================================
# SCN-04: Timeout Retry
# =============================================================================

def build_scn_04_timeout_retry() -> Scenario:
    """SCN-04: Timeout followed by cooldown and retry.

    Validates timeout handling without exceeding retry threshold.
    """
    f = EventFactory(session_id="scn-04")

    return Scenario(
        id="SCN-04",
        title="Timeout Retry - Single Timeout With Recovery",
        steps=[
            step(
                f.make(FLOW_START),
                "Start the booking flow",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_1_ENTRY_CLICKED),
                "Click entry to proceed",
                expected_state=FlowState.S2,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(TIME_TIMEOUT),
                "Timeout occurs in S2 (retry count = 1)",
                expected_state=FlowState.S2,  # Stay in same state
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(TIME_COOLDOWN_EXPIRED),
                "Cooldown expires, ready to retry",
                expected_state=FlowState.S2,  # Still in S2
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_2_QUEUE_PASSED),
                "Retry succeeds, proceed to S3",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
        ],
    )


# =============================================================================
# SCN-05: Seat Taken at S5
# =============================================================================

def build_scn_05_seat_taken() -> Scenario:
    """SCN-05: Multiple seat-taken events at S5.

    Validates SEAT_TAKEN streak tracking without tier escalation.
    """
    f = EventFactory(session_id="scn-05")

    return Scenario(
        id="SCN-05",
        title="Seat Taken - Multiple Attempts Without Escalation",
        steps=[
            step(
                f.make(FLOW_START),
                "Start the booking flow",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_1_ENTRY_CLICKED),
                "Click entry",
                expected_state=FlowState.S2,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_2_QUEUE_PASSED),
                "Pass queue",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_3_CHALLENGE_PASSED),
                "Pass challenge",
                expected_state=FlowState.S4,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_4_SECTION_SELECTED),
                "Select section",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_SEAT_TAKEN),
                "First seat taken - streak = 1",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_SEAT_TAKEN),
                "Second seat taken - streak = 2",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_SEAT_TAKEN),
                "Third seat taken - streak = 3 (still T0)",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_CONFIRM_CLICKED),
                "Finally confirm seat selection",
                expected_state=FlowState.S6,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
        ],
    )


# =============================================================================
# SCN-06: T2 Escalation with Challenge
# =============================================================================

def build_scn_06_sandbox() -> Scenario:
    """SCN-06: T2 escalation triggers throttle and challenge.

    Validates that multiple pattern signals lead to T2 with THROTTLE+CHALLENGE actions.
    """
    f = EventFactory(session_id="scn-06")

    return Scenario(
        id="SCN-06",
        title="T2 Escalation - Throttle and Challenge Actions",
        steps=[
            step(
                f.make(FLOW_START),
                "Start the booking flow",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "First pattern signal -> T1",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Second pattern signal -> still T1",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Third pattern signal -> T2 escalation with THROTTLE+CHALLENGE -> S3",
                expected_state=FlowState.S3,  # DEF_CHALLENGE_FORCED triggers transition to S3
                expected_tier=DefenseTier.T2,
                expected_actions=["THROTTLE", "CHALLENGE"],  # T2 actions per Tier-Action Matrix
            ),
        ],
    )


# =============================================================================
# All Scenarios Collection
# =============================================================================

def get_all_basic_scenarios() -> List[Scenario]:
    """Return all standard (happy path) scenarios.

    Returns:
        List of all SCN-01 through SCN-06 scenarios.
    """
    return [
        build_scn_01_happy_path(),
        build_scn_02_challenge_pass(),
        build_scn_03_interrupt(),
        build_scn_04_timeout_retry(),
        build_scn_05_seat_taken(),
        build_scn_06_sandbox(),
    ]


__all__ = [
    "EventFactory",
    "build_scn_01_happy_path",
    "build_scn_02_challenge_pass",
    "build_scn_03_interrupt",
    "build_scn_04_timeout_retry",
    "build_scn_05_seat_taken",
    "build_scn_06_sandbox",
    "get_all_basic_scenarios",
    "step",
]
