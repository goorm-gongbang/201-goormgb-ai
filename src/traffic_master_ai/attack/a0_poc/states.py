"""State definitions for State Machine Spec v1.0."""

from enum import Enum


class State(Enum):
    """
    State Machine states as defined in Spec v1.0.

    - S0: Init / Bootstrap
    - S1: Pre-Entry
    - S2: Queue & Entry
    - S3: Security Verification (interruptible)
    - S4: Section Selection
    - S5: Seat Selection
    - S6: Transaction Monitor
    - SX: Terminal (done | abort | cooldown | reset)
    """

    S0_INIT = "S0"
    S1_PRE_ENTRY = "S1"
    S2_QUEUE_ENTRY = "S2"
    S3_SECURITY = "S3"
    S4_SECTION = "S4"
    S5_SEAT = "S5"
    S6_TRANSACTION = "S6"
    SX_TERMINAL = "SX"

    def is_terminal(self) -> bool:
        """Check if this state is a terminal state."""
        return self == State.SX_TERMINAL

    def is_security(self) -> bool:
        """Check if this state is the security verification state."""
        return self == State.S3_SECURITY

    def can_be_last_non_security(self) -> bool:
        """
        Check if this state can be stored as last_non_security_state.
        Per spec: last_non_security_state ∈ {S1, S2, S4, S5, S6}
        """
        return self in {
            State.S1_PRE_ENTRY,
            State.S2_QUEUE_ENTRY,
            State.S4_SECTION,
            State.S5_SEAT,
            State.S6_TRANSACTION,
        }


# Terminal reason literals as defined in spec
TERMINAL_REASONS = frozenset({"done", "abort", "cooldown", "reset"})


class TerminalReason(Enum):
    """
    Terminal state reasons as defined in Spec v1.0.
    
    - done: 정상 완료 (티켓팅 성공)
    - abort: 치명적 오류로 중단
    - cooldown: 정책 위반으로 쿨다운 진입
    - reset: 외부 요청으로 리셋
    """
    
    DONE = "done"
    ABORT = "abort"
    COOLDOWN = "cooldown"
    RESET = "reset"

