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
    "FLOW_START",           # S0 → S1 (= BOOTSTRAP_COMPLETE)
    "BOOTSTRAP_COMPLETE",   # S0 → S1
    "ENTRY_ENABLED",        # S1 → S2
    "QUEUE_PASSED",         # S2 → S4
    "SECTION_LIST_READY",   # S4 상태 유지 (정보 이벤트)
    "SECTION_SELECTED",     # S4 → S5
    "SEATMAP_READY",        # S5 상태 유지 (정보 이벤트)
    "SEAT_SELECTED",        # S5 → S6
    "HOLD_ACQUIRED",        # S6 상태에서 홀드 확인 (= HOLD_CONFIRMED)
    "HOLD_CONFIRMED",       # S6 상태에서 홀드 확인
    "PAYMENT_PAGE_ENTERED", # S6 상태 유지 (정보 이벤트)
    "PAYMENT_COMPLETE",     # S6 → SX
    "PAYMENT_COMPLETED",    # S6 → SX (alias)
    # Security events
    "CHALLENGE_DETECTED",       # Any → S3
    "DEF_CHALLENGE_FORCED",     # Any → S3 (= CHALLENGE_DETECTED)
    "CHALLENGE_APPEARED",       # S3 상태 유지 (정보 이벤트)
    "CHALLENGE_PASSED",         # S3 → last_non_security_state
    "CHALLENGE_NOT_PRESENT",    # S3 → last_non_security_state
    "CHALLENGE_FAILED",         # S3 상태 유지 또는 SX
    # Failure events
    "SECTION_EMPTY",        # S4 상태 유지 (재시도)
    "SEAT_TAKEN",           # S5 상태 유지 또는 S4 롤백
    "HOLD_FAILED",          # S5 상태 유지 또는 S4 롤백
    "TXN_ROLLBACK_REQUIRED",# S6 → S5
    "PAYMENT_TIMEOUT",      # S6 → SX 또는 S5
    # Terminal events
    "FATAL_ERROR",
    "POLICY_ABORT",
    "COOLDOWN_TRIGGERED",
    "SESSION_EXPIRED",      # Any → SX (reset)
})
