"""Snapshot definitions for state and policy."""

from dataclasses import dataclass, field
from typing import Any

from traffic_master_ai.attack.a0_poc.states import State


@dataclass(slots=True)
class StateSnapshot:
    """
    Current state snapshot for transition decisions.

    This is mutable to allow the engine wrapper to update state
    between transitions.

    Attributes:
        current_state: The current state machine state
        last_non_security_state: Last state before S3 interrupt (for ReturnTo)
        budgets: Resource budgets (e.g., {"retry": 3, "security": 2})
        counters: Accumulated counters (e.g., {"attempts": 5})
        elapsed_ms: Elapsed time in milliseconds
    """

    current_state: State
    last_non_security_state: State | None = None
    budgets: dict[str, int] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    elapsed_ms: int = 0

    def copy(self) -> "StateSnapshot":
        """Create a shallow copy of the snapshot."""
        return StateSnapshot(
            current_state=self.current_state,
            last_non_security_state=self.last_non_security_state,
            budgets=dict(self.budgets),
            counters=dict(self.counters),
            elapsed_ms=self.elapsed_ms,
        )


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    """
    Policy profile snapshot injected from external configuration.

    Immutable since policies are determined externally and should not
    be modified during transition processing.

    Attributes:
        profile_name: Name of the active policy profile
        rules: Optional policy rules dictionary
    """

    profile_name: str
    rules: dict[str, Any] = field(default_factory=dict)

    def get_rule(self, key: str, default: Any = None) -> Any:
        """Get a policy rule value with optional default."""
        return self.rules.get(key, default)
