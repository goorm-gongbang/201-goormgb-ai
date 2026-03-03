"""Runtime state for Attack Agent MVP (A1).

Keep this as the single mutable state container that the orchestrator updates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from traffic_master_ai.common.models.states import FlowState, TerminalReason

SeatMode = Literal["MAP", "RECOMMEND"]


@dataclass(slots=True)
class Budget:
    """Retry budgets (MVP defaults; can be overridden by config/policy)."""

    challenge: int = 3
    section: int = 10
    seat: int = 20
    hold: int = 10
    net: int = 10


@dataclass(slots=True)
class Counters:
    """Counters for observability and policy decisions."""

    challenge_failed: int = 0
    section_empty: int = 0
    seat_taken: int = 0
    hold_failed: int = 0
    payment_failed: int = 0


@dataclass(slots=True)
class AgentState:
    # Core
    flow_state: FlowState = FlowState.S0
    mode: SeatMode = "MAP"

    # Security interrupt recovery
    last_non_security_state: FlowState | None = None

    # Execution identifiers (populated over time)
    session_id: str = ""
    queue_ticket_id: str = ""
    hold_id: str = ""
    order_id: str = ""

    # Budgets/counters
    budget: Budget = field(default_factory=Budget)
    counters: Counters = field(default_factory=Counters)

    # Terminal
    terminal_reason: TerminalReason | None = None

    # Free-form context (selectors, last URL, chosen zone, etc.)
    context: dict[str, Any] = field(default_factory=dict)

    def set_terminal(self, reason: TerminalReason) -> None:
        self.flow_state = FlowState.SX
        self.terminal_reason = reason

