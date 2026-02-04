"""Risk Controller for Defense PoC-0 Brain layer.

Evaluates EvidenceState to determine Risk Tier transitions and
generates RISK_TIER_UPDATED events when tier changes occur.
"""

from typing import Optional, Tuple
import uuid

from ..core import DefenseTier, EventSource, FlowState
from ..signals import (
    RISK_TIER_UPDATED,
    SIGNAL_REPETITIVE_PATTERN,
    STAGE_3_CHALLENGE_PASSED,
)
from ..signals.events import Event
from .evidence import EvidenceState


# Tier rank mapping for comparison (higher = more severe)
_TIER_RANK = {
    DefenseTier.T0: 0,
    DefenseTier.T1: 1,
    DefenseTier.T2: 2,
    DefenseTier.T3: 3,
}


class RiskController:
    """Controller that determines Risk Tier based on accumulated evidence.

    Applies Risk Rules (R-1 through R-4) to evaluate evidence and
    determine if tier escalation or de-escalation is warranted.
    """

    # PolicySnapshot thresholds (PoC-0 fixed)
    _CHALLENGE_FAIL_THRESHOLD = 3
    _REPETITIVE_PATTERN_T1_THRESHOLD = 1
    _REPETITIVE_PATTERN_T2_THRESHOLD = 3

    def decide_tier(
        self,
        evidence: EvidenceState,
        current_tier: DefenseTier,
        current_flow_state: FlowState,
        event: Event,
    ) -> Tuple[DefenseTier, Optional[Event]]:
        """Evaluate evidence and determine the new Risk Tier.

        This method is pure: it does not mutate any input.

        Args:
            evidence: Current cumulative evidence state.
            current_tier: Current defense tier.
            current_flow_state: Current flow state.
            event: The triggering event.

        Returns:
            Tuple of (new_tier, optional RISK_TIER_UPDATED event).
            If tier unchanged, returns (current_tier, None).
        """
        # Step 1: Evaluate escalation rules (R-1, R-2, R-3)
        target_tier = self._evaluate_escalation_rules(evidence)

        # Step 2: Apply tier comparison (no drop unless R-4)
        if _TIER_RANK[target_tier] < _TIER_RANK[current_tier]:
            # By default, don't allow tier to drop
            target_tier = current_tier

        # Step 3: Check R-4 decay condition
        if self._should_decay(current_tier, current_flow_state, event):
            target_tier = DefenseTier.T1

        # Step 4: Generate event if tier changed
        if target_tier != current_tier:
            tier_event = self._create_tier_updated_event(
                current_tier=current_tier,
                target_tier=target_tier,
                source_event=event,
            )
            return target_tier, tier_event

        return current_tier, None

    def _evaluate_escalation_rules(self, evidence: EvidenceState) -> DefenseTier:
        """Evaluate escalation rules R-1, R-2, R-3 and return highest tier.

        Args:
            evidence: Current evidence state.

        Returns:
            The highest tier indicated by escalation rules, or T0 if none apply.
        """
        # R-3: Critical Signal (highest priority) - Spec F-4
        if evidence.token_mismatch_detected:
            return DefenseTier.T3

        # R-2: Failure Accumulation - Spec F-1
        if evidence.challenge_fail_count >= self._CHALLENGE_FAIL_THRESHOLD:
            return DefenseTier.T3

        # R-1: Repetitive Pattern
        pattern_count = self._count_repetitive_patterns(evidence)
        if pattern_count >= self._REPETITIVE_PATTERN_T2_THRESHOLD:
            return DefenseTier.T2
        if pattern_count >= self._REPETITIVE_PATTERN_T1_THRESHOLD:
            return DefenseTier.T1

        # Default
        return DefenseTier.T0

    def _count_repetitive_patterns(self, evidence: EvidenceState) -> int:
        """Count SIGNAL_REPETITIVE_PATTERN occurrences in signal history.

        Args:
            evidence: Current evidence state.

        Returns:
            Number of SIGNAL_REPETITIVE_PATTERN events in history.
        """
        return sum(
            1 for sig in evidence.signal_history
            if sig == SIGNAL_REPETITIVE_PATTERN
        )

    def _should_decay(
        self,
        current_tier: DefenseTier,
        current_flow_state: FlowState,
        event: Event,
    ) -> bool:
        """Check if R-4 decay condition is satisfied.

        R-4 allows tier to decay to T1 when:
        - current_tier is T2 or higher
        - current_flow_state is S3
        - event.type is STAGE_3_CHALLENGE_PASSED

        Args:
            current_tier: Current defense tier.
            current_flow_state: Current flow state.
            event: The triggering event.

        Returns:
            True if decay should occur.
        """
        return (
            _TIER_RANK[current_tier] >= _TIER_RANK[DefenseTier.T2]
            and current_flow_state == FlowState.S3
            and event.type == STAGE_3_CHALLENGE_PASSED
        )

    def _create_tier_updated_event(
        self,
        current_tier: DefenseTier,
        target_tier: DefenseTier,
        source_event: Event,
    ) -> Event:
        """Create a RISK_TIER_UPDATED event.

        Args:
            current_tier: The tier before change.
            target_tier: The tier after change.
            source_event: The triggering event (for ts_ms and session_id).

        Returns:
            New RISK_TIER_UPDATED Event.
        """
        return Event(
            event_id=f"risk-{uuid.uuid4().hex[:8]}",
            ts_ms=source_event.ts_ms,
            type=RISK_TIER_UPDATED,
            source=EventSource.DEFENSE,
            session_id=source_event.session_id,
            payload={
                "from": current_tier.value,
                "to": target_tier.value,
            },
        )


__all__ = ["RiskController"]
