"""Canonical enums for Defense D0-MVP runtime.

Ref: L0/l0_core.yaml#flowState, L0/l0_core.yaml#apiProtocol.reasonCodes
     L1/runtime/contracts.yaml#reason_codes, #headers.defense_response_headers
     L0/l0_defense_policy.yaml#tiering
"""

from enum import Enum


# ---------------------------------------------------------------------------
# FlowState — L0/l0_core.yaml §2
# ---------------------------------------------------------------------------
class FlowState(str, Enum):
    """Canonical ticketing lifecycle states."""

    S0 = "S0"  # Start / Initial
    S1 = "S1"  # Entry Clicked
    S2 = "S2"  # Queue Passed
    S3 = "S3"  # Security Verification (Fixed Stage)
    S4 = "S4"  # Section Selected
    S5 = "S5"  # Seat Held / Confirmed
    S6 = "S6"  # Payment Initiated
    SX = "SX"  # Terminal State


# ---------------------------------------------------------------------------
# DefenseTier — L0/l0_defense_policy.yaml §4, policy_v1.yaml#tiering
# ---------------------------------------------------------------------------
class DefenseTier(str, Enum):
    """Risk tier derived from riskScore via threshold + hysteresis."""

    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


# ---------------------------------------------------------------------------
# DefenseAction — L1/runtime/contracts.yaml#headers.x-defense-action
# ---------------------------------------------------------------------------
class DefenseAction(str, Enum):
    """Planner output action enum."""

    NONE = "NONE"
    THROTTLE = "THROTTLE"
    REQUIRE_S3 = "REQUIRE_S3"
    BLOCK = "BLOCK"


# ---------------------------------------------------------------------------
# ReasonCode — L0/l0_core.yaml §6 + L1/runtime/contracts.yaml#reason_codes
# ---------------------------------------------------------------------------
class ReasonCode(str, Enum):
    """Standardised reasonCode values.

    L0 (global):
    """

    # --- L0 global codes (l0_core.yaml §6) ---
    HELD_BY_OTHERS = "HELD_BY_OTHERS"
    EXPIRED = "EXPIRED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    INVALID_HOLD = "INVALID_HOLD"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    MISSING_IDEMPOTENCY_KEY = "MISSING_IDEMPOTENCY_KEY"

    # --- L1 defense-runtime codes (contracts.yaml §2) ---
    BLOCKED = "BLOCKED"
    CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    CHALLENGE_FAILED = "CHALLENGE_FAILED"
    CHALLENGE_PASSED = "CHALLENGE_PASSED"
    CHALLENGE_TEMPORARILY_LOCKED = "CHALLENGE_TEMPORARILY_LOCKED"
    CHALLENGE_VERIFY_UNAVAILABLE = "CHALLENGE_VERIFY_UNAVAILABLE"
    CHALLENGE_EXPIRED = "CHALLENGE_EXPIRED"
    CHALLENGE_INVALID = "CHALLENGE_INVALID"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# ReasonCode → HTTP status mapping
# Ref: L0/l0_core.yaml §6.reasonCodes.mapping + L1/contracts.yaml §2.http_mapping
# ---------------------------------------------------------------------------
REASON_CODE_HTTP_MAP: dict[ReasonCode, int] = {
    # L0 global
    ReasonCode.HELD_BY_OTHERS: 409,
    ReasonCode.EXPIRED: 410,
    ReasonCode.PAYMENT_FAILED: 502,
    ReasonCode.INVALID_HOLD: 400,
    ReasonCode.NOT_FOUND: 404,
    ReasonCode.VALIDATION_ERROR: 400,
    ReasonCode.MISSING_IDEMPOTENCY_KEY: 400,
    # L1 defense
    ReasonCode.BLOCKED: 403,
    ReasonCode.CHALLENGE_REQUIRED: 428,
    ReasonCode.INVALID_TRANSITION: 409,
    ReasonCode.CHALLENGE_TEMPORARILY_LOCKED: 429,
    ReasonCode.INTERNAL_ERROR: 500,
}


# ---------------------------------------------------------------------------
# Allowed transitions table
# Ref: L0/l0_core.yaml §2.invariantTransitions
#      annex/orchestrator_spec.yaml#canonical_state_machine.allowed_transitions
# ---------------------------------------------------------------------------
ALLOWED_TRANSITIONS: set[tuple[FlowState, FlowState]] = {
    (FlowState.S0, FlowState.S1),
    (FlowState.S1, FlowState.S2),
    (FlowState.S2, FlowState.S3),
    (FlowState.S3, FlowState.S4),
    (FlowState.S4, FlowState.S5),
    (FlowState.S5, FlowState.S6),
    (FlowState.S6, FlowState.S5),
    (FlowState.S6, FlowState.SX),
    # Abort / timeout → SX from any non-terminal state
    (FlowState.S0, FlowState.SX),
    (FlowState.S1, FlowState.SX),
    (FlowState.S2, FlowState.SX),
    (FlowState.S3, FlowState.SX),
    (FlowState.S4, FlowState.SX),
    (FlowState.S5, FlowState.SX),
}
