"""Pure state transition engine for Defense PoC-0."""

from typing import Dict, List, Optional

from ..core import (
    Context,
    DefenseAction,
    FailureCode,
    FlowState,
    TerminalReason,
    TransitionResult,
)
from ..policy.snapshot import PolicySnapshot
from ..signals import (
    DEF_BLOCKED,
    DEF_THROTTLED,
    FLOW_ABORT,
    FLOW_RESET,
    FLOW_START,
    SIGNAL_TOKEN_MISMATCH,
    STAGE_1_ENTRY_CLICKED,
    STAGE_2_QUEUE_PASSED,
    STAGE_3_CHALLENGE_FAILED,
    STAGE_3_CHALLENGE_PASSED,
    STAGE_4_SECTION_SELECTED,
    STAGE_5_CONFIRM_CLICKED,
    STAGE_5_HOLD_FAILED,
    STAGE_5_SEAT_TAKEN,
    STAGE_6_PAYMENT_ABORTED,
    STAGE_6_PAYMENT_COMPLETED,
)
from ..signals.events import Event


def transition(
    state: FlowState,
    event: Event,
    context: Context,
    policy: PolicySnapshot,
) -> TransitionResult:
    """
    Evaluate a single (state, event, context) tuple and produce a TransitionResult.

    The function is pure: it does not mutate the incoming Context and returns only
    the changed fields via `context_mutations`.
    """

    next_state: FlowState = state
    failure_code: Optional[FailureCode] = None
    terminal_reason: Optional[TerminalReason] = None
    return_to: Optional[FlowState] = None
    actions: List[DefenseAction] = []
    mutations: Dict[str, object] = {}

    def set_mutation(field: str, value: object) -> None:
        mutations[field] = value

    def inc(field: str) -> int:
        new_val = getattr(context, field) + 1
        set_mutation(field, new_val)
        return new_val

    # Failure / guardrail rules
    if event.type == SIGNAL_TOKEN_MISMATCH:
        next_state = FlowState.SX
        failure_code = FailureCode.F_POLICY_VIOLATION
        terminal_reason = TerminalReason.BLOCKED
        actions.append(
            DefenseAction(type=DEF_BLOCKED, payload={"reason": "token_mismatch"}),
        )
    elif event.type == STAGE_3_CHALLENGE_FAILED:
        count = inc("challenge_fail_count")
        if count >= policy.challenge_fail_threshold:
            next_state = FlowState.SX
            failure_code = FailureCode.F_CHALLENGE_FAILED
            terminal_reason = TerminalReason.BLOCKED
            actions.append(
                DefenseAction(
                    type=DEF_BLOCKED,
                    payload={"reason": "challenge_fail_threshold"},
                ),
            )
        else:
            next_state = state
    elif event.type in (STAGE_5_SEAT_TAKEN, STAGE_5_HOLD_FAILED) and state == FlowState.S5:
        field = "seat_taken_count" if event.type == STAGE_5_SEAT_TAKEN else "hold_fail_count"
        streak = inc(field)
        if streak >= policy.seat_taken_streak_threshold:
            actions.append(DefenseAction(type=DEF_THROTTLED, payload={"state": "S5"}))
        next_state = FlowState.S5
    elif event.type == DEF_BLOCKED:
        next_state = FlowState.SX
        failure_code = FailureCode.F_BLOCKED
        terminal_reason = TerminalReason.BLOCKED
    elif event.type == FLOW_ABORT:
        next_state = FlowState.SX
        terminal_reason = TerminalReason.ABORT
    elif event.type == FLOW_RESET:
        next_state = FlowState.S0
        terminal_reason = TerminalReason.RESET
        set_mutation("challenge_fail_count", 0)
        set_mutation("seat_taken_count", 0)
        set_mutation("hold_fail_count", 0)
        set_mutation("last_non_security_state", None)
        set_mutation("is_sandboxed", False)
        set_mutation("session_age", 0)
    elif event.type == STAGE_6_PAYMENT_ABORTED:
        next_state = FlowState.SX
        terminal_reason = TerminalReason.ABORT
    elif event.type == "TXN_ROLLBACK" and state == FlowState.S6:
        next_state = FlowState.S5
        return_to = FlowState.S6
    else:
        # Normal progression
        if state == FlowState.S0 and event.type == FLOW_START:
            next_state = FlowState.S1
        elif state == FlowState.S1 and event.type == STAGE_1_ENTRY_CLICKED:
            next_state = FlowState.S2
        elif state == FlowState.S2 and event.type == STAGE_2_QUEUE_PASSED:
            next_state = FlowState.S3
        elif state == FlowState.S3 and event.type == STAGE_3_CHALLENGE_PASSED:
            next_state = FlowState.S4
        elif state == FlowState.S4 and event.type == STAGE_4_SECTION_SELECTED:
            next_state = FlowState.S5
        elif state == FlowState.S5 and event.type == STAGE_5_CONFIRM_CLICKED:
            next_state = FlowState.S6
        elif state == FlowState.S6 and event.type == STAGE_6_PAYMENT_COMPLETED:
            next_state = FlowState.SX
            terminal_reason = TerminalReason.DONE

    # Reset streak counters when leaving S5 and not due to seat/hold failures.
    if state == FlowState.S5 and next_state != FlowState.S5:
        if "seat_taken_count" not in mutations:
            set_mutation("seat_taken_count", 0)
        if "hold_fail_count" not in mutations:
            set_mutation("hold_fail_count", 0)

    return TransitionResult(
        next_state=next_state,
        context_mutations=mutations,
        actions=actions,
        failure_code=failure_code,
        terminal_reason=terminal_reason,
        return_to=return_to,
    )


__all__ = ["transition"]
