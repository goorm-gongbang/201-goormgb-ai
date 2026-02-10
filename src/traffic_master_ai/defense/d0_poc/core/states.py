"""Core enumerations for Defense PoC-0 flow and outcomes."""

from traffic_master_ai.common.models.states import FlowState, DefenseTier, TerminalReason as CommonTerminalReason

# Aliases and Extensions
TerminalReason = CommonTerminalReason

from enum import Enum

class EventSource(str, Enum):
    PAGE = "PAGE"
    BACKEND = "BACKEND"
    TIMER = "TIMER"
    DEFENSE = "DEFENSE"


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
