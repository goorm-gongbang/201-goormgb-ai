"""Semantic Event definitions for Event Dictionary v1.0."""

from dataclasses import dataclass, field
from typing import Any

from traffic_master_ai.attack.a0_poc.states import State


@dataclass(frozen=True, slots=True)
class SemanticEvent:
    """
    Semantic Event as defined in Event Dictionary v1.0.

    Only high-level semantic events are used (e.g., ENTRY_ENABLED, QUEUE_PASSED).
    Low-level browser/DOM events are out of scope.

    Attributes:
        event_type: The semantic event type string
        stage: Optional state context where event originated
        failure_code: Optional failure code for error events
        context: Additional event context data
    """

    event_type: str
    stage: State | None = None
    failure_code: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate event_type is non-empty."""
        if not self.event_type:
            raise ValueError("event_type must be non-empty")


# Known semantic event types from Spec v1.0
# This is a reference set, not exhaustive validation
KNOWN_EVENT_TYPES = frozenset({
    # Normal flow events
    "BOOTSTRAP_COMPLETE",
    "ENTRY_ENABLED",
    "QUEUE_PASSED",
    "SECTION_SELECTED",
    "SEAT_SELECTED",
    "HOLD_CONFIRMED",
    "PAYMENT_COMPLETE",
    # Security events
    "CHALLENGE_DETECTED",
    "CHALLENGE_PASSED",
    "CHALLENGE_NOT_PRESENT",
    "CHALLENGE_FAILED",
    # Failure events
    "SEAT_TAKEN",
    "HOLD_FAILED",
    "TXN_ROLLBACK_REQUIRED",
    "PAYMENT_TIMEOUT",
    # Terminal events
    "FATAL_ERROR",
    "POLICY_ABORT",
    "COOLDOWN_TRIGGERED",
})
