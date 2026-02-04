"""Dataclasses for Defense PoC-0 context and transition results."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .states import FailureCode, FlowState, TerminalReason


@dataclass(slots=True)
class DefenseAction:
    """Represents a defense action emitted by the engine."""

    type: str
    payload: Dict[str, Any]


@dataclass(slots=True)
class Context:
    """Mutable state consulted and updated by the pure function engine."""

    last_non_security_state: Optional[FlowState] = None
    challenge_fail_count: int = 0
    seat_taken_count: int = 0
    hold_fail_count: int = 0
    session_age: int = 0
    is_sandboxed: bool = False
    retry_count: int = 0


@dataclass(slots=True)
class TransitionResult:
    """Return type for state transition evaluations."""

    next_state: FlowState
    context_mutations: Dict[str, Any] = field(default_factory=dict)
    actions: List[DefenseAction] = field(default_factory=list)
    failure_code: Optional[FailureCode] = None
    terminal_reason: Optional[TerminalReason] = None
    return_to: Optional[FlowState] = None


__all__ = [
    "DefenseAction",
    "Context",
    "TransitionResult",
]
