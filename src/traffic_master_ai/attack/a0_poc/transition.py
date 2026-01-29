"""Transition result and decision log definitions."""

from dataclasses import dataclass, field
from typing import Any

from traffic_master_ai.attack.a0_poc.events import SemanticEvent
from traffic_master_ai.attack.a0_poc.states import State


@dataclass(frozen=True, slots=True)
class TransitionResult:
    """
    Result of a pure transition function.

    Immutable to ensure no side effects. The `commands` field contains
    intent-level instructions only (actual execution is handled elsewhere).

    Attributes:
        next_state: The state to transition to
        terminal_reason: If transitioning to SX, the reason (done|abort|cooldown|reset)
        failure_code: Optional failure code for error tracking
        notes: Human-readable notes about the transition decision
        commands: Intent-level commands (not executed, just recorded)
    """

    next_state: State
    terminal_reason: str | None = None
    failure_code: str | None = None
    notes: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate terminal_reason is set iff next_state is SX."""
        if self.next_state.is_terminal() and self.terminal_reason is None:
            raise ValueError("terminal_reason required when next_state is SX_TERMINAL")
        if not self.next_state.is_terminal() and self.terminal_reason is not None:
            raise ValueError("terminal_reason must be None for non-terminal states")

    def is_terminal(self) -> bool:
        """Check if this result leads to a terminal state."""
        return self.next_state.is_terminal()


@dataclass(frozen=True, slots=True)
class DecisionLog:
    """
    Decision log entry schema for audit/replay purposes.

    This is a schema definition only - actual file storage/JSONL writing
    is handled by a separate layer (out of scope for A0-1).

    Attributes:
        decision_id: Unique identifier for this decision
        timestamp_ms: Unix timestamp in milliseconds
        current_state: State before transition
        event: The event that triggered the transition
        next_state: State after transition
        policy_profile: Name of the active policy profile
        budgets: Budget snapshot at decision time
        counters: Counter snapshot at decision time
        elapsed_ms: Elapsed time at decision time
        notes: Decision notes from TransitionResult
    """

    decision_id: str
    timestamp_ms: int
    current_state: State
    event: SemanticEvent
    next_state: State
    policy_profile: str
    budgets: dict[str, int]
    counters: dict[str, int]
    elapsed_ms: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization (schema only, no IO)."""
        return {
            "decision_id": self.decision_id,
            "timestamp_ms": self.timestamp_ms,
            "current_state": self.current_state.value,
            "event": {
                "event_type": self.event.event_type,
                "stage": self.event.stage.value if self.event.stage else None,
                "failure_code": self.event.failure_code,
                "context": self.event.context,
            },
            "next_state": self.next_state.value,
            "policy_profile": self.policy_profile,
            "budgets": self.budgets,
            "counters": self.counters,
            "elapsed_ms": self.elapsed_ms,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """
    Final result of a state machine execution run.
    
    Captures the complete execution path from start to terminal state.
    
    Attributes:
        state_path: Ordered list of states visited during execution
        terminal_state: Final terminal state (always SX_TERMINAL)
        terminal_reason: Reason for termination (done/abort/cooldown/reset)
        handled_events: Number of events successfully processed
        total_elapsed_ms: Total execution time in milliseconds
        final_budgets: Budget snapshot at termination
        final_counters: Counter snapshot at termination
    """
    
    state_path: list[State]
    terminal_state: State
    terminal_reason: str
    handled_events: int
    total_elapsed_ms: int
    final_budgets: dict[str, int] = field(default_factory=dict)
    final_counters: dict[str, int] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate terminal state is SX."""
        if not self.terminal_state.is_terminal():
            raise ValueError("terminal_state must be SX_TERMINAL")
        if self.terminal_reason not in {"done", "abort", "cooldown", "reset"}:
            raise ValueError(f"Invalid terminal_reason: {self.terminal_reason}")
    
    def is_success(self) -> bool:
        """Check if execution completed successfully."""
        return self.terminal_reason == "done"

