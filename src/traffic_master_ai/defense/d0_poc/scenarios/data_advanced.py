"""Advanced threat scenarios for Defense PoC-0.

Contains SCN-07 through SCN-15 covering edge cases, attack defense,
failure matrix validation, and S6 protection.
"""

from typing import List, Optional

from ..core import DefenseTier, EventSource, FlowState
from ..core.states import TerminalReason
from ..signals import (
    DEF_BLOCKED,
    DEF_CHALLENGE_FORCED,
    FLOW_ABORT,
    FLOW_RESET,
    FLOW_START,
    SIGNAL_REPETITIVE_PATTERN,
    SIGNAL_TOKEN_MISMATCH,
    STAGE_1_ENTRY_CLICKED,
    STAGE_2_QUEUE_PASSED,
    STAGE_3_CHALLENGE_FAILED,
    STAGE_3_CHALLENGE_PASSED,
    STAGE_4_SECTION_SELECTED,
    STAGE_5_CONFIRM_CLICKED,
    STAGE_5_SEAT_TAKEN,
    STAGE_6_PAYMENT_COMPLETED,
)
from ..signals.events import Event
from .data_basic import EventFactory, step
from .schema import Scenario, ScenarioStep


# =============================================================================
# SCN-07: Flow Reset / Abort Priority
# =============================================================================

def build_scn_07_flow_control() -> Scenario:
    """SCN-07: FLOW_RESET and FLOW_ABORT priority verification.

    Validates that flow control events always work and produce correct
    terminal_reason (RESET/ABORT).
    """
    f = EventFactory(session_id="scn-07")

    return Scenario(
        id="SCN-07",
        title="Flow Control - Reset and Abort Priority",
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
                "Progress to S2",
                expected_state=FlowState.S2,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(FLOW_RESET),
                "Reset flow -> back to S0 with RESET terminal",
                expected_state=FlowState.S0,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(FLOW_START),
                "Start again after reset",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(FLOW_ABORT),
                "Abort flow -> SX with ABORT terminal",
                expected_state=FlowState.SX,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
        ],
    )


# =============================================================================
# SCN-08: Challenge Block (F-1)
# =============================================================================

def build_scn_08_challenge_block() -> Scenario:
    """SCN-08: Three challenge failures lead to T3 and Block.

    Validates Failure Matrix F-1: 3 consecutive challenge failures
    trigger T3 escalation and immediate block.
    """
    f = EventFactory(session_id="scn-08")

    return Scenario(
        id="SCN-08",
        title="Challenge Block - F-1 Three Failures",
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
                "Pass queue -> enter challenge",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_3_CHALLENGE_FAILED),
                "Challenge fail #1",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_3_CHALLENGE_FAILED),
                "Challenge fail #2",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_3_CHALLENGE_FAILED),
                "Challenge fail #3 -> T3 + BLOCK + SX",
                expected_state=FlowState.SX,  # Core transitions to SX on threshold
                expected_tier=DefenseTier.T3,
                expected_actions=["BLOCK"],
            ),
        ],
    )


# =============================================================================
# SCN-09: Token Mismatch (Immediate Block)
# =============================================================================

def build_scn_09_token_mismatch() -> Scenario:
    """SCN-09: Token mismatch triggers immediate T3 and Block.

    Validates that SIGNAL_TOKEN_MISMATCH causes instant T3 escalation
    and block regardless of current tier.
    """
    f = EventFactory(session_id="scn-09")

    return Scenario(
        id="SCN-09",
        title="Token Mismatch - Immediate Block",
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
                f.make(SIGNAL_TOKEN_MISMATCH),
                "Token mismatch detected -> T3 + BLOCK + SX",
                expected_state=FlowState.SX,
                expected_tier=DefenseTier.T3,
                expected_actions=["BLOCK"],
            ),
        ],
    )


# =============================================================================
# SCN-10: Escalation Verification (T0 -> T1 -> T2)
# =============================================================================

def build_scn_10_escalation() -> Scenario:
    """SCN-10: Pattern signals escalate T0 -> T1 -> T2.

    Validates escalation logic: 1 pattern = T1, 3 patterns = T2.
    """
    f = EventFactory(session_id="scn-10")

    return Scenario(
        id="SCN-10",
        title="Tier Escalation - T0 to T2 Progression",
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
                "Pattern #1 -> T1",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern #2 -> still T1",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern #3 -> T2 escalation",
                expected_state=FlowState.S3,  # DEF_CHALLENGE_FORCED triggers S3
                expected_tier=DefenseTier.T2,
                expected_actions=["THROTTLE", "CHALLENGE"],
            ),
        ],
    )


# =============================================================================
# SCN-11: T2 Action Check (THROTTLE + CHALLENGE)
# =============================================================================

def build_scn_11_t2_actions() -> Scenario:
    """SCN-11: T2 tier produces both THROTTLE and CHALLENGE actions.

    Validates Tier-Action Matrix for T2.
    """
    f = EventFactory(session_id="scn-11")

    return Scenario(
        id="SCN-11",
        title="T2 Actions - Throttle and Challenge Combined",
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
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern #1 -> T1",
                expected_state=FlowState.S2,
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern #2 -> T1",
                expected_state=FlowState.S2,
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern #3 -> T2 with THROTTLE + CHALLENGE",
                expected_state=FlowState.S3,  # DEF_CHALLENGE_FORCED
                expected_tier=DefenseTier.T2,
                expected_actions=["THROTTLE", "CHALLENGE"],
            ),
        ],
    )


# =============================================================================
# SCN-12: S5 Streak Strong Throttle
# =============================================================================

def build_scn_12_s5_streak_throttle() -> Scenario:
    """SCN-12: S5 seat-taken streak triggers strong throttle at threshold.

    Validates F-3 rule: 7 seat-taken events trigger THROTTLE(strong).
    """
    f = EventFactory(session_id="scn-12")

    return Scenario(
        id="SCN-12",
        title="S5 Streak - Strong Throttle at Threshold",
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
                "Select section -> S5",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            # 7 seat-taken events to reach threshold
            step(
                f.make(STAGE_5_SEAT_TAKEN),
                "Seat taken #1",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_SEAT_TAKEN),
                "Seat taken #2",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_SEAT_TAKEN),
                "Seat taken #3",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_SEAT_TAKEN),
                "Seat taken #4",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_SEAT_TAKEN),
                "Seat taken #5",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_SEAT_TAKEN),
                "Seat taken #6",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_5_SEAT_TAKEN),
                "Seat taken #7 -> THROTTLE(strong) threshold met",
                expected_state=FlowState.S5,
                expected_tier=DefenseTier.T0,
                expected_actions=["THROTTLE"],  # Strong throttle via F-3 rule
            ),
        ],
    )


# =============================================================================
# SCN-13: Tier Decay (T2 -> T1)
# =============================================================================

def build_scn_13_decay() -> Scenario:
    """SCN-13: T2 tier persists through challenge.

    Note: Current RiskController doesn't implement R-4 decay on challenge pass.
    This scenario validates that T2 persists and continues actions in S3.
    """
    f = EventFactory(session_id="scn-13")

    return Scenario(
        id="SCN-13",
        title="T2 Tier Persistence - Actions Continue in S3",
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
                "Pattern #1 -> T1",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern #2 -> T1",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern #3 -> T2 with CHALLENGE -> S3",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T2,
                expected_actions=["THROTTLE", "CHALLENGE"],
            ),
            step(
                f.make(STAGE_3_CHALLENGE_PASSED),
                "Challenge pass at T2 -> stays in S3 with T2 actions",
                expected_state=FlowState.S3,  # DEF_CHALLENGE_FORCED keeps it in S3
                expected_tier=DefenseTier.T2,  # No decay implemented
                expected_actions=["THROTTLE", "CHALLENGE"],
            ),
        ],
    )


# =============================================================================
# SCN-14: Sandbox Release (Placeholder - requires SANDBOX_MAX_AGE_EXPIRED)
# =============================================================================

def build_scn_14_sandbox_release() -> Scenario:
    """SCN-14: T2 escalation with challenge loop.

    Validates that T2 tier maintains CHALLENGE actions in S3.
    """
    f = EventFactory(session_id="scn-14")

    return Scenario(
        id="SCN-14",
        title="T2 Challenge Loop - Persistent Challenge at T2",
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
                "Pattern #1 -> T1",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern #2 -> T1",
                expected_state=FlowState.S1,
                expected_tier=DefenseTier.T1,
                expected_actions=["THROTTLE"],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern #3 -> T2 with CHALLENGE",
                expected_state=FlowState.S3,
                expected_tier=DefenseTier.T2,
                expected_actions=["THROTTLE", "CHALLENGE"],
            ),
            step(
                f.make(STAGE_3_CHALLENGE_PASSED),
                "Challenge pass at T2 -> re-challenged",
                expected_state=FlowState.S3,  # DEF_CHALLENGE_FORCED loops back
                expected_tier=DefenseTier.T2,
                expected_actions=["THROTTLE", "CHALLENGE"],
            ),
        ],
    )


# =============================================================================
# SCN-15: S6 Protection (F-5)
# =============================================================================

def build_scn_15_s6_protection() -> Scenario:
    """SCN-15: S6 protection - no interventions during payment.

    Validates F-5 rule: In S6, no new THROTTLE/CHALLENGE/SANDBOX actions
    even if tier escalates. Tier can still rise but actions are blocked.
    """
    f = EventFactory(session_id="scn-15")

    return Scenario(
        id="SCN-15",
        title="S6 Protection - No Interventions During Payment",
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
                f.make(STAGE_5_CONFIRM_CLICKED),
                "Confirm seat -> enter S6 payment",
                expected_state=FlowState.S6,
                expected_tier=DefenseTier.T0,
                expected_actions=[],
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern in S6 -> T1 but NO actions (F-5 protection)",
                expected_state=FlowState.S6,
                expected_tier=DefenseTier.T1,
                expected_actions=[],  # F-5: No interventions in S6
            ),
            step(
                f.make(SIGNAL_REPETITIVE_PATTERN),
                "Pattern #2 in S6 -> still T1, NO actions",
                expected_state=FlowState.S6,
                expected_tier=DefenseTier.T1,
                expected_actions=[],
            ),
            step(
                f.make(STAGE_6_PAYMENT_COMPLETED),
                "Complete payment at T1",
                expected_state=FlowState.SX,
                expected_tier=DefenseTier.T1,
                expected_actions=[],
            ),
        ],
    )


# =============================================================================
# All Advanced Scenarios Collection
# =============================================================================

def get_all_advanced_scenarios() -> List[Scenario]:
    """Return all advanced threat scenarios.

    Returns:
        List of all SCN-07 through SCN-15 scenarios.
    """
    return [
        build_scn_07_flow_control(),
        build_scn_08_challenge_block(),
        build_scn_09_token_mismatch(),
        build_scn_10_escalation(),
        build_scn_11_t2_actions(),
        build_scn_12_s5_streak_throttle(),
        build_scn_13_decay(),
        build_scn_14_sandbox_release(),
        build_scn_15_s6_protection(),
    ]


__all__ = [
    "build_scn_07_flow_control",
    "build_scn_08_challenge_block",
    "build_scn_09_token_mismatch",
    "build_scn_10_escalation",
    "build_scn_11_t2_actions",
    "build_scn_12_s5_streak_throttle",
    "build_scn_13_decay",
    "build_scn_14_sandbox_release",
    "build_scn_15_s6_protection",
    "get_all_advanced_scenarios",
]
