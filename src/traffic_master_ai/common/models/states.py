"""Common State and Terminal Reason definitions."""

from enum import Enum


class FlowState(str, Enum):
    """
    Standard Flow States for both Attack and Defense.
    
    - S0: Init / Bootstrap
    - S1: Pre-Entry
    - S2: Queue & Entry
    - S3: Security Verification
    - S4: Section Selection
    - S5: Seat Selection
    - S6: Transaction Monitor
    - SX: Terminal state
    """
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"
    S6 = "S6"
    SX = "SX"

    def is_terminal(self) -> bool:
        """Check if this state is a terminal state."""
        return self == FlowState.SX

    def is_security(self) -> bool:
        """Check if this state is the security verification state."""
        return self == FlowState.S3

    def can_be_last_non_security(self) -> bool:
        """Check if this state can be the last non-security state before S3."""
        return self in (FlowState.S1, FlowState.S2, FlowState.S4, FlowState.S5, FlowState.S6)


class TerminalReason(str, Enum):
    """
    Standard Terminal Reasons.
    
    Values are capitalized to align with Defense team's standard.
    """
    DONE = "DONE"
    ABORT = "ABORT"
    COOLDOWN = "COOLDOWN"
    RESET = "RESET"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    BLOCKED = "BLOCKED"


class DefenseTier(str, Enum):
    """Defense Tiers as defined in Defense Spec."""
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
