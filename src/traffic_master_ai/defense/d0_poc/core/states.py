"""Core enumerations for Defense PoC-0 flow and outcomes."""

from enum import Enum


class FlowState(str, Enum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"
    S6 = "S6"
    SX = "SX"


class DefenseTier(str, Enum):
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class EventSource(str, Enum):
    PAGE = "PAGE"
    BACKEND = "BACKEND"
    TIMER = "TIMER"
    DEFENSE = "DEFENSE"


class TerminalReason(str, Enum):
    DONE = "DONE"
    ABORT = "ABORT"
    COOLDOWN = "COOLDOWN"
    RESET = "RESET"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    BLOCKED = "BLOCKED"


class FailureCode(str, Enum):
    F_NONE = "F_NONE"
    F_CHALLENGE_FAILED = "F_CHALLENGE_FAILED"
    F_TIMEOUT = "F_TIMEOUT"
    F_SEAT_TAKEN = "F_SEAT_TAKEN"
    F_HOLD_FAILED = "F_HOLD_FAILED"
    F_BLOCKED = "F_BLOCKED"
    F_POLICY_VIOLATION = "F_POLICY_VIOLATION"


__all__ = [
    "FlowState",
    "DefenseTier",
    "EventSource",
    "TerminalReason",
    "FailureCode",
]
