"""Orchestrator implementation for D0-MVP.

Ref: annex/orchestrator_spec.yaml
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from ..brain.planner import PlannerPlan
from ..core.enums import ALLOWED_TRANSITIONS, DefenseAction, FlowState, ReasonCode
from ..core.models import DefenseDecision, ErrorResponse, SessionState
from ..events.common import RuntimeEvent
from ..policy.snapshot import PolicySnapshot
from ..state.block_state import BlockStateManager
from ..state.session_state import SessionStateManager


@dataclass(slots=True, frozen=True)
class OrchestratorResult:
    """Final orchestrated output."""

    allow: bool
    decision: DefenseDecision
    http_status: Optional[int]
    error: Optional[ErrorResponse]
    headers: dict[str, str]
    state_from: FlowState
    state_to: Optional[FlowState]
    transition_applied: bool
    reason_code: Optional[ReasonCode]


class Orchestrator:
    """Terminal-first state transition executor."""

    def __init__(
        self,
        *,
        session_state: SessionStateManager,
        block_state: BlockStateManager,
    ) -> None:
        self._session_state = session_state
        self._block_state = block_state

    def execute(
        self,
        *,
        session_id: str,
        state: SessionState,
        event: RuntimeEvent,
        plan: PlannerPlan,
        policy: PolicySnapshot,
    ) -> OrchestratorResult:
        """Execute Planner plan with transition and commit rules."""
        current_state = state.flow_state
        requested_state = event.flow_state
        transition_applied = False
        grace_until_ms = int(time.time() * 1000) + (policy.s3_grace_ttl_seconds * 1000)

        # E1: terminal-first
        persisted_block = self._block_state.is_blocked(session_id)
        block_ttl_seconds = self._block_state.get_block_ttl_seconds(session_id)
        if persisted_block or plan.action == DefenseAction.BLOCK:
            if plan.action == DefenseAction.BLOCK and not persisted_block:
                self._block_state.set_block(
                    session_id=session_id,
                    blocked_at_ms=event.ts_ms,
                    reason_code=ReasonCode.BLOCKED.value,
                    policy_version=plan.decision.policy_version,
                    ttl_seconds=policy.block_ttl_seconds,
                )
                block_ttl_seconds = policy.block_ttl_seconds
            self._session_state.update_by_role(
                "orchestrator",
                session_id,
                {"lastDecisionAction": DefenseAction.BLOCK.value},
                is_allow=False,
            )
            decision = DefenseDecision(
                tier=plan.decision.tier,
                action=DefenseAction.BLOCK,
                policy_version=plan.decision.policy_version,
                block_ttl_seconds=block_ttl_seconds or policy.block_ttl_seconds,
                reason=plan.decision.reason or "terminal_first_block",
            )
            return _deny_result(
                decision=decision,
                http_status=403,
                reason_code=ReasonCode.BLOCKED,
                message="요청이 차단되었습니다.",
                state_from=current_state,
                state_to=None,
                transition_applied=False,
            )

        if current_state == FlowState.SX:
            decision = DefenseDecision(
                tier=plan.decision.tier,
                action=DefenseAction.NONE,
                policy_version=plan.decision.policy_version,
                reason="terminal_no_replan",
            )
            return OrchestratorResult(
                allow=True,
                decision=decision,
                http_status=None,
                error=None,
                headers=decision.to_headers(),
                state_from=current_state,
                state_to=current_state,
                transition_applied=False,
                reason_code=None,
            )

        # E2: validate transition
        if requested_state != current_state:
            if (current_state, requested_state) not in ALLOWED_TRANSITIONS:
                self._session_state.update_by_role(
                    "orchestrator",
                    session_id,
                    {"lastDecisionAction": plan.action.value},
                    is_allow=False,
                )
                return _deny_result(
                    decision=plan.decision,
                    http_status=409,
                    reason_code=ReasonCode.INVALID_TRANSITION,
                    message="허용되지 않는 진행 단계입니다.",
                    state_from=current_state,
                    state_to=requested_state,
                    transition_applied=False,
                )
            transition_applied = True

        # E3: S3 fixed gate safety (forced)
        if requested_state in {FlowState.S4, FlowState.S5} and not state.s3_passed:
            self._session_state.set_s3_grace(
                session_id,
                grace_until_ms=grace_until_ms,
            )
            decision = DefenseDecision(
                tier=plan.decision.tier,
                action=DefenseAction.REQUIRE_S3,
                policy_version=plan.decision.policy_version,
                reason="s3_not_passed",
            )
            self._session_state.update_by_role(
                "orchestrator",
                session_id,
                {"lastDecisionAction": DefenseAction.REQUIRE_S3.value},
                is_allow=False,
            )
            return _deny_result(
                decision=decision,
                http_status=428,
                reason_code=ReasonCode.CHALLENGE_REQUIRED,
                message="S3 검증이 필요합니다.",
                state_from=current_state,
                state_to=None,
                transition_applied=False,
            )

        if plan.action == DefenseAction.REQUIRE_S3:
            self._session_state.set_s3_grace(
                session_id,
                grace_until_ms=grace_until_ms,
            )
            self._session_state.update_by_role(
                "orchestrator",
                session_id,
                {"lastDecisionAction": DefenseAction.REQUIRE_S3.value},
                is_allow=False,
            )
            return _deny_result(
                decision=plan.decision,
                http_status=428,
                reason_code=ReasonCode.CHALLENGE_REQUIRED,
                message="S3 검증이 필요합니다.",
                state_from=current_state,
                state_to=None,
                transition_applied=False,
            )

        # E4: commit state
        changes: dict[str, object] = {
            "lastDecisionAction": plan.action.value,
        }
        if transition_applied:
            changes["flowState"] = requested_state.value
        if event.event_type == "S3_RESULT" and event.s3_result == "PASS":
            changes["s3Passed"] = 1
            changes["s3PassedAtMs"] = event.ts_ms

        is_allow = plan.action in {DefenseAction.NONE, DefenseAction.THROTTLE}
        self._session_state.update_by_role(
            "orchestrator",
            session_id,
            changes,
            is_allow=is_allow,
        )

        # E5: response shaping
        decision = plan.decision
        headers = decision.to_headers()
        return OrchestratorResult(
            allow=True,
            decision=decision,
            http_status=None,
            error=None,
            headers=headers,
            state_from=current_state,
            state_to=requested_state if transition_applied else current_state,
            transition_applied=transition_applied,
            reason_code=None,
        )



def _deny_result(
    *,
    decision: DefenseDecision,
    http_status: int,
    reason_code: ReasonCode,
    message: str,
    state_from: FlowState,
    state_to: Optional[FlowState],
    transition_applied: bool,
) -> OrchestratorResult:
    return OrchestratorResult(
        allow=False,
        decision=decision,
        http_status=http_status,
        error=ErrorResponse.from_reason(reason_code=reason_code, message=message),
        headers=decision.to_headers(),
        state_from=state_from,
        state_to=state_to,
        transition_applied=transition_applied,
        reason_code=reason_code,
    )


__all__ = ["Orchestrator", "OrchestratorResult"]
