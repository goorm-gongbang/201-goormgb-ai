"""Event validation layer for Defense PoC-0."""

from dataclasses import dataclass
from typing import Optional

from ..core import FlowState
from .events import Event
from .registry import ALL_STATES, EVENT_ALLOWED_STATES


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    action: str
    message: Optional[str] = None


def validate_event(current_state: FlowState, event: Event) -> ValidationResult:
    allowed_states = EVENT_ALLOWED_STATES.get(event.type)
    if allowed_states is None:
        return ValidationResult(
            valid=False,
            action="ignore",
            message=f"Unknown event type: {event.type}",
        )

    if current_state in allowed_states or allowed_states is ALL_STATES:
        return ValidationResult(valid=True, action="accept")

    return ValidationResult(
        valid=False,
        action="ignore",
        message=f"Event {event.type} not allowed in state {current_state}",
    )


__all__ = ["ValidationResult", "validate_event"]
