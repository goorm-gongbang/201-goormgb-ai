"""Unit tests for Defense PoC-0 Brain layer logic.

Tests the full pipeline: Evidence -> Risk -> Plan -> Actuator
"""

import pytest
from typing import Any, Dict, Optional

from traffic_master_ai.defense.d0_poc.actions import Actuator
from traffic_master_ai.defense.d0_poc.brain import (
    ActionPlanner,
    EvidenceState,
    RiskController,
    SignalAggregator,
)
from traffic_master_ai.defense.d0_poc.core import DefenseTier, EventSource, FlowState
from traffic_master_ai.defense.d0_poc.core.models import Context
from traffic_master_ai.defense.d0_poc.signals import (
    DEF_BLOCKED,
    DEF_CHALLENGE_FORCED,
    DEF_THROTTLED,
    SIGNAL_REPETITIVE_PATTERN,
    SIGNAL_TOKEN_MISMATCH,
    STAGE_3_CHALLENGE_FAILED,
    STAGE_5_SEAT_TAKEN,
)
from traffic_master_ai.defense.d0_poc.signals.events import Event


from traffic_master_ai.common.models.events import EventType

def mk_event(
    event_type: str,
    source: EventSource = EventSource.PAGE,
    session_id: str = "s1",
    ts_ms: int = 1,
    payload: Optional[Dict[str, Any]] = None,
    seq: int = 0,
) -> Event:
    """Factory helper to create test events."""
    return Event(
        type=EventType(event_type),
        event_id=f"test-{seq}",
        session_id=session_id,
        source=source,
        payload=payload or {},
        ts_ms=ts_ms + seq,
    )


class TestTierEscalationPattern:
    """Case 1: Tier Escalation via SIGNAL_REPETITIVE_PATTERN."""

    def test_single_pattern_escalates_to_t1(self) -> None:
        """SIGNAL_REPETITIVE_PATTERN 1회 -> tier == T1."""
        aggregator = SignalAggregator()
        risk = RiskController()

        evidence = EvidenceState()
        tier = DefenseTier.T0
        flow_state = FlowState.S1

        # Inject 1 SIGNAL_REPETITIVE_PATTERN
        event = mk_event(SIGNAL_REPETITIVE_PATTERN, seq=0)
        evidence = aggregator.process_event(evidence, event)
        tier, _ = risk.decide_tier(evidence, tier, flow_state, event)

        assert tier == DefenseTier.T1

    def test_three_patterns_escalates_to_t2(self) -> None:
        """SIGNAL_REPETITIVE_PATTERN 3회 누적 -> tier == T2."""
        aggregator = SignalAggregator()
        risk = RiskController()

        evidence = EvidenceState()
        tier = DefenseTier.T0
        flow_state = FlowState.S1

        # Inject 3 SIGNAL_REPETITIVE_PATTERN
        for i in range(3):
            event = mk_event(SIGNAL_REPETITIVE_PATTERN, seq=i)
            evidence = aggregator.process_event(evidence, event)
            tier, _ = risk.decide_tier(evidence, tier, flow_state, event)

        assert tier == DefenseTier.T2


class TestImmediateBlockTokenMismatch:
    """Case 2: Immediate Block on SIGNAL_TOKEN_MISMATCH."""

    def test_token_mismatch_triggers_t3_and_block(self) -> None:
        """SIGNAL_TOKEN_MISMATCH -> tier == T3, BLOCK plan, DEF_BLOCKED event."""
        aggregator = SignalAggregator()
        risk = RiskController()
        planner = ActionPlanner()
        actuator = Actuator()

        evidence = EvidenceState()
        tier = DefenseTier.T0
        flow_state = FlowState.S1
        context = Context()

        # Inject SIGNAL_TOKEN_MISMATCH
        event = mk_event(SIGNAL_TOKEN_MISMATCH, seq=0)
        evidence = aggregator.process_event(evidence, event)
        tier, _ = risk.decide_tier(evidence, tier, flow_state, event)

        # Verify tier
        assert tier == DefenseTier.T3

        # Verify planner produces BLOCK
        plans = planner.plan_actions(tier, flow_state, evidence)
        block_plans = [p for p in plans if p.action_type == "BLOCK"]
        assert len(block_plans) >= 1, "Should have BLOCK plan"

        # Verify actuator produces DEF_BLOCKED
        def_events = actuator.execute_plans(plans, context, event)
        blocked_events = [e for e in def_events if e.type == DEF_BLOCKED]
        assert len(blocked_events) >= 1, "Should have DEF_BLOCKED event"


class TestChallengeFailureLoop:
    """Case 3: Failure Matrix F-1 (Challenge Loop)."""

    def test_three_challenge_failures_triggers_t3_and_block(self) -> None:
        """STAGE_3_CHALLENGE_FAILED 3회 -> tier == T3, BLOCK, DEF_BLOCKED."""
        aggregator = SignalAggregator()
        risk = RiskController()
        planner = ActionPlanner()
        actuator = Actuator()

        evidence = EvidenceState()
        tier = DefenseTier.T0
        flow_state = FlowState.S3  # Challenge stage
        context = Context()

        # Inject 3 challenge failures
        for i in range(3):
            event = mk_event(STAGE_3_CHALLENGE_FAILED, seq=i)
            evidence = aggregator.process_event(evidence, event)
            tier, _ = risk.decide_tier(evidence, tier, flow_state, event)

        # Verify tier
        assert tier == DefenseTier.T3

        # Verify planner produces BLOCK
        plans = planner.plan_actions(tier, flow_state, evidence)
        block_plans = [p for p in plans if p.action_type == "BLOCK"]
        assert len(block_plans) >= 1, "Should have BLOCK plan"

        # Verify actuator produces DEF_BLOCKED
        final_event = mk_event(STAGE_3_CHALLENGE_FAILED, seq=3)
        def_events = actuator.execute_plans(plans, context, final_event)
        blocked_events = [e for e in def_events if e.type == DEF_BLOCKED]
        assert len(blocked_events) >= 1, "Should have DEF_BLOCKED event"


class TestS5StreakLogic:
    """Case 4: S5 Streak Logic (F-3)."""

    def test_s5_streak_7_triggers_throttle_strong(self) -> None:
        """STAGE_5_SEAT_TAKEN 7회 -> tier 유지, THROTTLE strong 계획."""
        aggregator = SignalAggregator()
        risk = RiskController()
        planner = ActionPlanner()
        actuator = Actuator()

        evidence = EvidenceState()
        tier = DefenseTier.T0
        flow_state = FlowState.S5  # Seat selection stage
        context = Context()

        # Inject 7 seat taken events
        for i in range(7):
            event = mk_event(STAGE_5_SEAT_TAKEN, seq=i)
            evidence = aggregator.process_event(evidence, event)
            tier, _ = risk.decide_tier(evidence, tier, flow_state, event)

        # Verify tier stays at T0 (no escalation from seat taken alone)
        assert tier == DefenseTier.T0

        # Verify evidence has streak of 7
        assert evidence.seat_taken_streak == 7

        # Verify planner produces THROTTLE strong (F-3 rule)
        plans = planner.plan_actions(tier, flow_state, evidence)
        throttle_plans = [p for p in plans if p.action_type == "THROTTLE"]
        assert len(throttle_plans) >= 1, "Should have THROTTLE plan"
        assert throttle_plans[0].params.get("strength") == "strong", \
            "THROTTLE should be strong for streak >= 7"

        # Verify actuator produces DEF_THROTTLED
        final_event = mk_event(STAGE_5_SEAT_TAKEN, seq=7)
        def_events = actuator.execute_plans(plans, context, final_event)
        throttle_events = [e for e in def_events if e.type == DEF_THROTTLED]
        assert len(throttle_events) >= 1, "Should have DEF_THROTTLED event"
        assert throttle_events[0].payload.get("strength") == "strong"


class TestS6Protection:
    """Case 5: S6 Protection (F-5)."""

    def test_s6_blocks_new_throttle_and_challenge(self) -> None:
        """S6에서 T2까지 -> planner가 THROTTLE/CHALLENGE를 계획하지 않음."""
        aggregator = SignalAggregator()
        risk = RiskController()
        planner = ActionPlanner()
        actuator = Actuator()

        evidence = EvidenceState()
        tier = DefenseTier.T0
        flow_state = FlowState.S6  # Payment stage
        context = Context()

        # Inject 3 SIGNAL_REPETITIVE_PATTERN to reach T2
        for i in range(3):
            event = mk_event(SIGNAL_REPETITIVE_PATTERN, seq=i)
            evidence = aggregator.process_event(evidence, event)
            tier, _ = risk.decide_tier(evidence, tier, flow_state, event)

        # Verify tier is T2
        assert tier == DefenseTier.T2

        # Verify planner produces NO actions in S6
        plans = planner.plan_actions(tier, flow_state, evidence)
        assert len(plans) == 0, "S6 should block all new interventions for T2"

        # Verify actuator produces no events
        final_event = mk_event(SIGNAL_REPETITIVE_PATTERN, seq=3)
        def_events = actuator.execute_plans(plans, context, final_event)
        assert len(def_events) == 0, "No DEF events should be generated in S6"

    def test_s6_allows_block_for_t3(self) -> None:
        """S6에서 T3이면 BLOCK은 허용됨."""
        aggregator = SignalAggregator()
        risk = RiskController()
        planner = ActionPlanner()
        actuator = Actuator()

        evidence = EvidenceState()
        tier = DefenseTier.T0
        flow_state = FlowState.S6
        context = Context()

        # Inject SIGNAL_TOKEN_MISMATCH to reach T3
        event = mk_event(SIGNAL_TOKEN_MISMATCH, seq=0)
        evidence = aggregator.process_event(evidence, event)
        tier, _ = risk.decide_tier(evidence, tier, flow_state, event)

        # Verify tier is T3
        assert tier == DefenseTier.T3

        # Verify planner produces BLOCK even in S6
        plans = planner.plan_actions(tier, flow_state, evidence)
        block_plans = [p for p in plans if p.action_type == "BLOCK"]
        assert len(block_plans) >= 1, "S6 should allow BLOCK for T3"

        # Verify actuator produces DEF_BLOCKED
        def_events = actuator.execute_plans(plans, context, event)
        blocked_events = [e for e in def_events if e.type == DEF_BLOCKED]
        assert len(blocked_events) >= 1, "Should have DEF_BLOCKED even in S6"


class TestFullPipeline:
    """Integration test for full pipeline flow."""

    def test_full_pipeline_escalation_to_block(self) -> None:
        """Full pipeline: Evidence -> Risk -> Plan -> Actuator for T3 block."""
        aggregator = SignalAggregator()
        risk = RiskController()
        planner = ActionPlanner()
        actuator = Actuator()

        evidence = EvidenceState()
        tier = DefenseTier.T0
        flow_state = FlowState.S3
        context = Context()

        # Process events through full pipeline
        events_to_process = [
            (STAGE_3_CHALLENGE_FAILED, FlowState.S3),
            (STAGE_3_CHALLENGE_FAILED, FlowState.S3),
            (STAGE_3_CHALLENGE_FAILED, FlowState.S3),
        ]

        all_def_events = []
        for i, (event_type, state) in enumerate(events_to_process):
            event = mk_event(event_type, seq=i)
            flow_state = state

            # Pipeline
            evidence = aggregator.process_event(evidence, event)
            tier, tier_event = risk.decide_tier(evidence, tier, flow_state, event)
            plans = planner.plan_actions(tier, flow_state, evidence)
            def_events = actuator.execute_plans(plans, context, event)
            all_def_events.extend(def_events)

        # Verify final state
        assert tier == DefenseTier.T3
        assert evidence.challenge_fail_count == 3

        # Verify DEF_BLOCKED was generated at some point
        blocked_events = [e for e in all_def_events if e.type == DEF_BLOCKED]
        assert len(blocked_events) >= 1, "Pipeline should produce DEF_BLOCKED"
