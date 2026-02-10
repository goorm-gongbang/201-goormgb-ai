"""Common Event and Source definitions."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .states import FlowState


class EventType(str, Enum):
    """
    Standard Semantic Event Types.
    
    Category suffixes and Stage prefixes are removed for universality.
    """
    # Flow
    FLOW_START = "FLOW_START"
    BOOTSTRAP_COMPLETE = "BOOTSTRAP_COMPLETE"
    FLOW_ABORT = "FLOW_ABORT"
    TIMEOUT = "TIMEOUT"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    FATAL_ERROR = "FATAL_ERROR"
    POLICY_ABORT = "POLICY_ABORT"
    COOLDOWN_TRIGGERED = "COOLDOWN_TRIGGERED"
    RETRY_BUDGET_EXCEEDED = "RETRY_BUDGET_EXCEEDED"
    
    # Entry/Queue
    ENTRY_ENABLED = "ENTRY_ENABLED"
    ENTRY_NOT_READY = "ENTRY_NOT_READY"
    ENTRY_BLOCKED = "ENTRY_BLOCKED"
    ENTRY_CLICKED = "ENTRY_CLICKED"
    QUEUE_SHOWN = "QUEUE_SHOWN"
    QUEUE_PASSED = "QUEUE_PASSED"
    QUEUE_STUCK = "QUEUE_STUCK"
    POPUP_OPENED = "POPUP_OPENED"
    
    # Security
    CHALLENGE_DETECTED = "CHALLENGE_DETECTED"
    CHALLENGE_APPEARED = "CHALLENGE_APPEARED"
    CHALLENGE_PASSED = "CHALLENGE_PASSED"
    CHALLENGE_FAILED = "CHALLENGE_FAILED"
    CHALLENGE_NOT_PRESENT = "CHALLENGE_NOT_PRESENT"
    
    # Section
    SECTION_LIST_READY = "SECTION_LIST_READY"
    SECTION_SELECTED = "SECTION_SELECTED"
    SECTION_EMPTY = "SECTION_EMPTY"
    
    # Seat
    SEATMAP_READY = "SEATMAP_READY"
    SEAT_SELECTED = "SEAT_SELECTED"
    SEAT_TAKEN = "SEAT_TAKEN"
    HOLD_ACQUIRED = "HOLD_ACQUIRED"
    HOLD_CONFIRMED = "HOLD_CONFIRMED"
    HOLD_FAILED = "HOLD_FAILED"
    CONFIRM_CLICKED = "CONFIRM_CLICKED"
    
    # Transaction
    PAYMENT_PAGE_ENTERED = "PAYMENT_PAGE_ENTERED"
    PAYMENT_COMPLETE = "PAYMENT_COMPLETE"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    PAYMENT_ABORTED = "PAYMENT_ABORTED"
    PAYMENT_TIMEOUT = "PAYMENT_TIMEOUT"
    TXN_ROLLBACK_REQUIRED = "TXN_ROLLBACK_REQUIRED"
    
    # Defense Specific (Signals/Actions)
    SIGNAL_REPETITIVE_PATTERN = "SIGNAL_REPETITIVE_PATTERN"
    SIGNAL_TOKEN_MISMATCH = "SIGNAL_TOKEN_MISMATCH"
    DEF_CHALLENGE_FORCED = "DEF_CHALLENGE_FORCED"
    DEF_THROTTLED = "DEF_THROTTLED"
    DEF_SANDBOXED = "DEF_SANDBOXED"
    DEF_BLOCKED = "DEF_BLOCKED"
    DEF_HONEY_SHAPED = "DEF_HONEY_SHAPED"


class EventSource(str, Enum):
    """Source of the event."""
    UI = "UI"
    API = "API"
    TIMER = "TIMER"
    DEFENSE = "DEFENSE"
    MOCK = "MOCK"
    PAGE = "PAGE"
    BACKEND = "BACKEND"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True, slots=True)
class SemanticEvent:
    """Standardized Semantic Event data model."""
    type: EventType | str
    event_id: str = ""
    session_id: str = ""
    source: EventSource | str = EventSource.MOCK
    stage: FlowState | None = None
    failure_code: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    ts_ms: int = 0

    def __post_init__(self) -> None:
        """Auto-coerce string values to proper enum types (graceful)."""
        if isinstance(self.type, str) and not isinstance(self.type, EventType):
            try:
                object.__setattr__(self, 'type', EventType(self.type))
            except ValueError:
                pass  # Keep as raw string for unknown event types
        if isinstance(self.source, str) and not isinstance(self.source, EventSource):
            try:
                object.__setattr__(self, 'source', EventSource(self.source.upper()))
            except ValueError:
                pass  # Keep as raw string for unknown sources
