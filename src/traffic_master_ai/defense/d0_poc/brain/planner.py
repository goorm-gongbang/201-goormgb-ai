"""Action Planner for Defense PoC-0 Brain layer.

Plans defense actions based on Risk Tier and current state.
This component only creates plans; actual execution is out of scope.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from ..core.states import DefenseTier, FlowState
from .evidence import EvidenceState


@dataclass
class PlannedAction:
    """Represents a planned defense action.

    Attributes:
        action_type: Type of action - "THROTTLE" | "BLOCK" | "CHALLENGE" | "SANDBOX" | "HONEY"
        params: Action parameters (e.g., {"strength": "light"})
    """

    action_type: str
    params: Dict = field(default_factory=dict)


# PoC-0 Fixed Parameters
_SEAT_TAKEN_STREAK_THRESHOLD = 7


class ActionPlanner:
    """Plans defense actions based on Risk Tier and special rules.

    Applies Tier-Action Matrix and Special Rules (F-3, F-5) to determine
    which defense actions should be executed.

    Tier-Action Matrix (baseline):
        - T0: No Action
        - T1: THROTTLE (Light)
        - T2: THROTTLE (Strong) + CHALLENGE (Medium)
        - T3: BLOCK
    """

    def plan_actions(
        self,
        tier: DefenseTier,
        flow_state: FlowState,
        evidence: EvidenceState,
    ) -> List[PlannedAction]:
        """Plan defense actions based on tier, flow state, and evidence.

        This method is pure: it does not mutate any input.

        Args:
            tier: Current defense tier.
            flow_state: Current flow state.
            evidence: Current evidence state for special rule checks.

        Returns:
            List of PlannedAction objects to be executed.
        """
        # Rule F-5 (S6 Protection): S6에서는 신규 개입 금지
        if flow_state == FlowState.S6:
            # Exception: T3 blocking is allowed in S6
            if tier == DefenseTier.T3:
                return [PlannedAction(action_type="BLOCK", params={"reason": "tier_t3"})]
            # No new THROTTLE/CHALLENGE/HONEY/SANDBOX in S6
            return []

        # Apply Tier-Action Matrix
        actions = self._apply_tier_matrix(tier)

        # Rule F-3 (S5 Streak): seat_taken_streak >= 7 -> add THROTTLE(Strong)
        if evidence.seat_taken_streak >= _SEAT_TAKEN_STREAK_THRESHOLD:
            actions = self._apply_s5_streak_rule(actions)

        return actions

    def _apply_tier_matrix(self, tier: DefenseTier) -> List[PlannedAction]:
        """Apply the Tier-Action Matrix to generate baseline actions.

        Args:
            tier: Current defense tier.

        Returns:
            List of PlannedAction from tier matrix.
        """
        if tier == DefenseTier.T0:
            return []

        if tier == DefenseTier.T1:
            return [PlannedAction(action_type="THROTTLE", params={"strength": "light"})]

        if tier == DefenseTier.T2:
            return [
                PlannedAction(action_type="THROTTLE", params={"strength": "strong"}),
                PlannedAction(action_type="CHALLENGE", params={"difficulty": "medium"}),
            ]

        if tier == DefenseTier.T3:
            return [PlannedAction(action_type="BLOCK", params={"reason": "tier_t3"})]

        # Fallback (should not reach)
        return []

    def _apply_s5_streak_rule(
        self, actions: List[PlannedAction]
    ) -> List[PlannedAction]:
        """Apply Rule F-3: S5 Streak adds or upgrades THROTTLE(Strong).

        If THROTTLE is already planned:
            - Light -> upgrade to Strong
            - Strong -> keep as is
        If no THROTTLE planned:
            - Add THROTTLE(Strong)

        Args:
            actions: Current list of planned actions.

        Returns:
            Updated list with F-3 rule applied.
        """
        throttle_idx = None
        for i, action in enumerate(actions):
            if action.action_type == "THROTTLE":
                throttle_idx = i
                break

        if throttle_idx is not None:
            # THROTTLE exists - check if upgrade needed
            current_strength = actions[throttle_idx].params.get("strength", "light")
            if current_strength == "light":
                # Upgrade Light to Strong
                actions[throttle_idx] = PlannedAction(
                    action_type="THROTTLE", params={"strength": "strong"}
                )
            # Strong already - no change needed
        else:
            # No THROTTLE - add THROTTLE(Strong)
            actions.append(
                PlannedAction(action_type="THROTTLE", params={"strength": "strong"})
            )

        return actions


__all__ = ["PlannedAction", "ActionPlanner"]
