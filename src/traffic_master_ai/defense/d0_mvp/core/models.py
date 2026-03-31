"""Dataclass models for Defense D0-MVP runtime.

Ref: L1/runtime/contracts.yaml#schemas (ErrorResponse, OkResponse, DefenseDecision)
     L1/runtime/contracts.yaml#ai_evaluate (EvaluateRequest)
     L1/runtime/contracts.yaml#envoy_ext_authz_adapter (CheckRequest)
     L1/runtime/state.yaml#schema (SessionState)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .enums import DefenseAction, DefenseTier, FlowState, ReasonCode


# ---------------------------------------------------------------------------
# DefenseDecision — contracts.yaml#schemas.DefenseDecision
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class DefenseDecision:
    """AI runtime internal decision result.

    Serialised into x-defense-* response headers.
    """

    tier: DefenseTier
    action: DefenseAction
    policy_version: str
    throttle_ms: Optional[int] = None
    block_ttl_seconds: Optional[int] = None
    reason: Optional[str] = None

    def to_headers(self) -> dict[str, str]:
        """Serialise to x-defense-* header dict."""
        headers = {
            "x-defense-tier": self.tier.value,
            "x-defense-action": self.action.value,
            "x-defense-policy-version": self.policy_version,
        }
        if self.throttle_ms is not None:
            headers["x-defense-throttle-ms"] = str(self.throttle_ms)
        if self.block_ttl_seconds is not None:
            headers["x-defense-block-ttl-seconds"] = str(self.block_ttl_seconds)
        return headers


# ---------------------------------------------------------------------------
# EvaluateRequest — contracts.yaml#ai_evaluate.request
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class EvaluateRequestEvent:
    """Event payload of /evaluate request.

    Ref: contracts.yaml#ai_evaluate.request.body.event
    """

    event_type: str
    ts_ms: int
    flow_state: FlowState
    request_path: Optional[str] = None
    request_method: Optional[str] = None
    s3_result: Optional[str] = None  # "PASS" | "FAIL" | "UNKNOWN"
    source: Optional[str] = None
    payload: Optional[dict[str, Any]] = None


@dataclass(slots=True)
class EvaluateRequestContext:
    """Context payload of /evaluate request.

    Ref: contracts.yaml#ai_evaluate.request.body.context
    """

    policy_version: str
    features: Optional[dict[str, Any]] = None
    meta: Optional[dict[str, Any]] = None


@dataclass(slots=True)
class EvaluateRequest:
    """Full /evaluate request model.

    Ref: contracts.yaml#ai_evaluate.request
    """

    session_id: str
    trace_id: str
    event: EvaluateRequestEvent
    context: EvaluateRequestContext


# ---------------------------------------------------------------------------
# CheckRequest — contracts.yaml#envoy_ext_authz_adapter.request_minimum
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class CheckRequest:
    """/check/* Adapter request minimum fields.

    Ref: contracts.yaml#envoy_ext_authz_adapter.request_minimum
    """

    session_id: str
    trace_id: str
    upstream_path: str
    upstream_method: str
    flow_state: FlowState
    original_query: Optional[str] = None
    client_ip_hash: Optional[str] = None
    turnstile_token: Optional[str] = None
    category: Optional[str] = None
    status_code: Optional[int] = None


# ---------------------------------------------------------------------------
# ErrorResponse — contracts.yaml#schemas.ErrorResponse
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ErrorResponse:
    """Standard error body for deny responses (403/428/409/429/500).

    Ref: contracts.yaml#schemas.ErrorResponse
    """

    status: str = "FAIL"
    reason_code: str = ""
    message: str = ""
    detail: Optional[dict[str, Any]] = None

    @classmethod
    def from_reason(
        cls,
        reason_code: ReasonCode,
        message: str = "",
        detail: Optional[dict[str, Any]] = None,
    ) -> ErrorResponse:
        return cls(
            status="FAIL",
            reason_code=reason_code.value,
            message=message,
            detail=detail,
        )


# ---------------------------------------------------------------------------
# OkResponse — contracts.yaml#schemas.OkResponse
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class OkResponse:
    """Standard success body.

    Ref: contracts.yaml#schemas.OkResponse
    """

    status: str = "OK"
    payload: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# SessionState — L1/runtime/state.yaml#schema.session_fields
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class SessionState:
    """In-memory representation of tm:sess:{sessionId} Redis state.

    Ref: L1/runtime/state.yaml#schema.session_fields
    """

    # --- required (L0 + L1) ---
    flow_state: FlowState = FlowState.S0
    risk_score: float = 0.0
    defense_tier: DefenseTier = DefenseTier.T0
    probation_until_ms: Optional[int] = None
    challenge_fail_count: int = 0
    seat_taken_streak: int = 0
    hold_fail_streak: int = 0
    policy_version: str = ""

    # --- optional (L1) ---
    s3_passed: bool = False
    s3_passed_at_ms: Optional[int] = None
    challenge_halt_until_ms: Optional[int] = None
    last_step_risk: Optional[float] = None
    last_guard_ts_ms: Optional[int] = None
    last_decision_action: Optional[str] = None

    def to_redis_dict(self) -> dict[str, Any]:
        """Serialise to flat dict for Redis HSET."""
        d: dict[str, Any] = {
            "flowState": self.flow_state.value,
            "riskScore": self.risk_score,
            "defenseTier": self.defense_tier.value,
            "challengeFailCount": self.challenge_fail_count,
            "seatTakenStreak": self.seat_taken_streak,
            "holdFailStreak": self.hold_fail_streak,
            "policyVersion": self.policy_version,
            "s3Passed": int(self.s3_passed),
        }
        if self.probation_until_ms is not None:
            d["probationUntilMs"] = self.probation_until_ms
        if self.s3_passed_at_ms is not None:
            d["s3PassedAtMs"] = self.s3_passed_at_ms
        if self.challenge_halt_until_ms is not None:
            d["challengeHaltUntilMs"] = self.challenge_halt_until_ms
        if self.last_step_risk is not None:
            d["lastStepRisk"] = self.last_step_risk
        if self.last_guard_ts_ms is not None:
            d["lastGuardTsMs"] = self.last_guard_ts_ms
        if self.last_decision_action is not None:
            d["lastDecisionAction"] = self.last_decision_action
        return d

    @classmethod
    def from_redis_dict(cls, d: dict[str, Any]) -> SessionState:
        """Deserialise from Redis HGETALL result."""
        return cls(
            flow_state=FlowState(d.get("flowState", "S0")),
            risk_score=float(d.get("riskScore", 0.0)),
            defense_tier=DefenseTier(d.get("defenseTier", "T0")),
            probation_until_ms=_opt_int(d.get("probationUntilMs")),
            challenge_fail_count=int(d.get("challengeFailCount", 0)),
            seat_taken_streak=int(d.get("seatTakenStreak", 0)),
            hold_fail_streak=int(d.get("holdFailStreak", 0)),
            policy_version=str(d.get("policyVersion", "")),
            s3_passed=bool(int(d.get("s3Passed", 0))),
            s3_passed_at_ms=_opt_int(d.get("s3PassedAtMs")),
            challenge_halt_until_ms=_opt_int(d.get("challengeHaltUntilMs")),
            last_step_risk=_opt_float(d.get("lastStepRisk")),
            last_guard_ts_ms=_opt_int(d.get("lastGuardTsMs")),
            last_decision_action=d.get("lastDecisionAction"),
        )


def _opt_int(v: Any) -> Optional[int]:
    return int(v) if v is not None else None


def _opt_float(v: Any) -> Optional[float]:
    return float(v) if v is not None else None
