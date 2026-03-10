"""Planner implementation for D0-MVP.

Ref: annex/planner_spec.yaml
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .analyzer import EvidenceSummaryForPlanner
from ..core.enums import DefenseAction, DefenseTier, FlowState, ReasonCode
from ..core.models import DefenseDecision
from ..policy.snapshot import PolicySnapshot


@dataclass(slots=True, frozen=True)
class PlannerPlan:
    """Planner output plan schema."""

    action: DefenseAction
    reason: str
    tier: DefenseTier
    decision: DefenseDecision
    deny_http_status: Optional[int] = None
    deny_reason_code: Optional[ReasonCode] = None


class Planner:
    """Priority-based action selector.

    Ref: annex/planner_spec.yaml#decision_rules.priority_order
    """

    def plan(
        self,
        *,
        flow_state: FlowState,
        tier: DefenseTier,
        s3_passed: bool,
        blocked: bool,
        policy: PolicySnapshot,
        evidence_summary: Optional[EvidenceSummaryForPlanner] = None,
        policy_version: Optional[str] = None,
    ) -> PlannerPlan:
        """Compute action plan for one request."""
        resolved_policy_version = policy_version or policy.policy_version
        require_s3_states = {
            FlowState(value)
            for value in policy.require_s3_for_states
            if value in FlowState._value2member_map_
        }

        # R0: ALREADY_BLOCKED
        if blocked:
            return self._build_block_plan(
                tier=tier,
                reason="persisted_block",
                policy=policy,
                policy_version=resolved_policy_version,
            )

        # R1: TERMINAL_SX
        if flow_state == FlowState.SX:
            return self._build_allow_plan(
                action=DefenseAction.NONE,
                tier=tier,
                reason="terminal_no_replan",
                policy_version=resolved_policy_version,
            )

        # R2: REQUIRE_S3_FOR_S4_S5
        if flow_state in require_s3_states and not s3_passed:
            return self._build_deny_plan(
                action=DefenseAction.REQUIRE_S3,
                tier=tier,
                reason="s3_not_passed",
                policy_version=resolved_policy_version,
                deny_http_status=428,
                deny_reason_code=ReasonCode.CHALLENGE_REQUIRED,
            )

        # R3: S6_RESTRICTION
        if flow_state == FlowState.S6:
            return self._build_allow_plan(
                action=DefenseAction.NONE,
                tier=tier,
                reason="no_new_intervention_in_s6",
                policy_version=resolved_policy_version,
            )

        # R4~R7: TIER_DEFAULT from policy_v1 action matrix
        action = _policy_action_to_enum(policy.action_for_tier(tier.value))
        reason_suffix = _reason_suffix(evidence_summary)

        if action == DefenseAction.NONE:
            return self._build_allow_plan(
                action=action,
                tier=tier,
                reason=_with_suffix(f"tier_{tier.value.lower()}", reason_suffix),
                policy_version=resolved_policy_version,
            )

        if action == DefenseAction.THROTTLE:
            return self._build_throttle_plan(
                tier=tier,
                reason=_with_suffix(_default_throttle_reason(tier), reason_suffix),
                policy=policy,
                policy_version=resolved_policy_version,
            )

        if action == DefenseAction.BLOCK:
            return self._build_block_plan(
                tier=tier,
                reason=_with_suffix(f"tier_{tier.value.lower()}_block", reason_suffix),
                policy=policy,
                policy_version=resolved_policy_version,
            )

        return self._build_deny_plan(
            action=DefenseAction.REQUIRE_S3,
            tier=tier,
            reason=_with_suffix("tier_requires_s3", reason_suffix),
            policy_version=resolved_policy_version,
            deny_http_status=428,
            deny_reason_code=ReasonCode.CHALLENGE_REQUIRED,
        )

    def _build_allow_plan(
        self,
        *,
        action: DefenseAction,
        tier: DefenseTier,
        reason: str,
        policy_version: str,
    ) -> PlannerPlan:
        decision = DefenseDecision(
            tier=tier,
            action=action,
            policy_version=policy_version,
            reason=reason,
        )
        return PlannerPlan(
            action=action,
            reason=reason,
            tier=tier,
            decision=decision,
        )

    def _build_throttle_plan(
        self,
        *,
        tier: DefenseTier,
        reason: str,
        policy: PolicySnapshot,
        policy_version: str,
    ) -> PlannerPlan:
        throttle_ms = policy.throttle_delay_for_tier(tier.value)
        decision = DefenseDecision(
            tier=tier,
            action=DefenseAction.THROTTLE,
            policy_version=policy_version,
            throttle_ms=throttle_ms,
            reason=reason,
        )
        return PlannerPlan(
            action=DefenseAction.THROTTLE,
            reason=reason,
            tier=tier,
            decision=decision,
        )

    def _build_block_plan(
        self,
        *,
        tier: DefenseTier,
        reason: str,
        policy: PolicySnapshot,
        policy_version: str,
    ) -> PlannerPlan:
        decision = DefenseDecision(
            tier=tier,
            action=DefenseAction.BLOCK,
            policy_version=policy_version,
            block_ttl_seconds=policy.block_ttl_seconds,
            reason=reason,
        )
        return PlannerPlan(
            action=DefenseAction.BLOCK,
            reason=reason,
            tier=tier,
            decision=decision,
            deny_http_status=policy.block_http_status,
            deny_reason_code=ReasonCode.BLOCKED,
        )

    def _build_deny_plan(
        self,
        *,
        action: DefenseAction,
        tier: DefenseTier,
        reason: str,
        policy_version: str,
        deny_http_status: int,
        deny_reason_code: ReasonCode,
    ) -> PlannerPlan:
        decision = DefenseDecision(
            tier=tier,
            action=action,
            policy_version=policy_version,
            reason=reason,
        )
        return PlannerPlan(
            action=action,
            reason=reason,
            tier=tier,
            decision=decision,
            deny_http_status=deny_http_status,
            deny_reason_code=deny_reason_code,
        )


__all__ = ["Planner", "PlannerPlan"]


def _policy_action_to_enum(action: str) -> DefenseAction:
    try:
        return DefenseAction(action)
    except ValueError:
        return DefenseAction.NONE


def _default_throttle_reason(tier: DefenseTier) -> str:
    if tier == DefenseTier.T1:
        return "tier_t1_light_throttle"
    if tier == DefenseTier.T2:
        return "tier_t2_throttle"
    return f"tier_{tier.value.lower()}_throttle"


def _reason_suffix(
    evidence_summary: Optional[EvidenceSummaryForPlanner],
) -> Optional[str]:
    if evidence_summary is None:
        return None
    parts: list[str] = []
    if evidence_summary.scan_pressure == "HIGH":
        parts.append("scan_high")
    elif evidence_summary.scan_pressure == "MED":
        parts.append("scan_med")
    if evidence_summary.hv_click_pressure == "HIGH":
        parts.append("hv_high")
    elif evidence_summary.hv_click_pressure == "MED":
        parts.append("hv_med")
    if evidence_summary.s3_failed_recently:
        parts.append("s3_fail_burst")
    if evidence_summary.in_probation:
        parts.append("probation")
    if not parts:
        return None
    return "_".join(parts)


def _with_suffix(reason: str, suffix: Optional[str]) -> str:
    if not suffix:
        return reason
    return f"{reason}_{suffix}"
