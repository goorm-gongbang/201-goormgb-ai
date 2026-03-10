"""Pydantic request/response models for AI Defense API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FlowStateStr = Literal["S0", "S1", "S2", "S3", "S4", "S4R", "S5", "S5R", "S6", "SX"]
DefenseTierStr = Literal["T0", "T1", "T2", "T3"]
DefenseActionStr = Literal["NONE", "CHALLENGE", "THROTTLE", "GATE", "BLOCK"]
ChallengeTypeStr = Literal["queue_gate", "catch_ball"]
ChallengeResultStr = Literal["PASSED", "FAILED", "BLOCKED", "EXPIRED"]
PointerEventTypeStr = Literal["down", "move", "up", "click"]


class EvaluateTelemetryFeatures(BaseModel):
    """Telemetry summary features for a single trigger window."""

    total_dist: float | None = Field(default=None, alias="totalDist")
    linear_dist: float | None = Field(default=None, alias="linearDist")
    linearity_ratio: float | None = Field(default=None, alias="linearityRatio")
    avg_velocity: float | None = Field(default=None, alias="avgVelocity")
    tremor_std_dev: float | None = Field(default=None, alias="tremorStdDev")
    dwell_time: float | None = Field(default=None, alias="dwellTime")
    timestamp: int | None = None

    model_config = {"populate_by_name": True, "extra": "forbid"}


class EvaluateRequest(BaseModel):
    """Adapter -> AI defense decision request."""

    session_id: str = Field(min_length=1)
    trace_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    path: str = Field(min_length=1)
    method: str = Field(min_length=1, description="HTTP method such as GET/POST")
    timestamp: int = Field(ge=0, description="Unix epoch milliseconds")
    headers: dict[str, str] = Field(default_factory=dict)

    # Optional context injected by adapter/cloud pipeline.
    flow_state: FlowStateStr | None = None
    defense_tier: DefenseTierStr | None = None
    challenge_fail_count: int = Field(default=0, ge=0)
    repetitive_pattern_count: int = Field(default=0, ge=0)
    token_mismatch: bool = False
    signals: list[str] = Field(default_factory=list)
    telemetry_features: EvaluateTelemetryFeatures | None = None

    model_config = {"extra": "forbid"}


class EvaluateResponse(BaseModel):
    """AI defense decision response consumed by authz adapter."""

    allow: bool
    session_id: str
    flow_state: FlowStateStr
    defense_tier: DefenseTierStr
    action: DefenseActionStr
    actions: list[DefenseActionStr] = Field(default_factory=list)
    reason: str | None = None
    rule_hits: list[str] = Field(default_factory=list)
    risk_score: float | None = None
    policy_version: str = "def-pol-2.0.0"
    headers_to_add: dict[str, str] = Field(default_factory=dict)
    decision_id: str
    latency_ms: int = Field(ge=0)
    version: str = "v2"

    model_config = {"extra": "forbid"}


class HealthResponse(BaseModel):
    """Basic liveness/readiness response."""

    status: Literal["ok"]
    service: str
    version: str


class RuntimeStateSnapshot(BaseModel):
    """Runtime session state kept in Redis (or in-memory fallback)."""

    flow_state: FlowStateStr = "S0"
    defense_tier: DefenseTierStr = "T0"
    risk_score: float = 0.0
    challenge_fail_count: int = 0
    seat_taken_streak: int = 0
    hold_fail_streak: int = 0
    heavy_budget_left: int = 2
    replan_budget_left: int = 3
    probation_until_ms: int | None = None
    policy_version: str = "def-pol-2.0.0"
    updated_ts_ms: int = 0
    vqa_required: bool = True
    vqa_passed: bool = False
    vqa_attempt_count: int = 0
    vqa_retry_limit: int = 2
    vqa_last_result: ChallengeResultStr | None = None
    active_challenge_id: str | None = None
    active_challenge_expires_at_ms: int | None = None

    model_config = {"extra": "forbid"}


class ChallengeStartRequest(BaseModel):
    """Start a one-time challenge gate."""

    session_id: str = Field(min_length=1)
    trace_id: str | None = None
    flow_state: FlowStateStr | None = None
    challenge_type: ChallengeTypeStr = "catch_ball"

    model_config = {"extra": "forbid"}


class ChallengeStartResponse(BaseModel):
    """Challenge issuance response."""

    session_id: str
    challenge_id: str
    challenge_type: ChallengeTypeStr
    challenge_token: str
    issued_at_ms: int
    expires_at_ms: int
    attempt_limit: int
    public_params: dict[str, float | int | str | bool]

    model_config = {"extra": "forbid"}


class ChallengePointerEvent(BaseModel):
    """Raw client pointer event used for server-side verification."""

    t_ms: int = Field(ge=0)
    x: float
    y: float
    event: PointerEventTypeStr

    model_config = {"extra": "forbid"}


class ChallengeEventIngestRequest(BaseModel):
    """Raw challenge events upload."""

    session_id: str = Field(min_length=1)
    challenge_id: str = Field(min_length=1)
    challenge_token: str = Field(min_length=1)
    events: list[ChallengePointerEvent] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class ChallengeEventIngestResponse(BaseModel):
    """Accepted event count response."""

    session_id: str
    challenge_id: str
    accepted_events: int
    total_events: int

    model_config = {"extra": "forbid"}


class ChallengeVerifyRequest(BaseModel):
    """Challenge verification request."""

    session_id: str = Field(min_length=1)
    challenge_id: str = Field(min_length=1)
    challenge_token: str = Field(min_length=1)
    final_click_ts_ms: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ChallengeVerifyResponse(BaseModel):
    """Server-side verification result."""

    session_id: str
    challenge_id: str
    result: ChallengeResultStr
    passed: bool
    attempts_used: int
    attempts_left: int
    defense_tier: DefenseTierStr
    action: DefenseActionStr
    reason: str | None = None
    headers_to_add: dict[str, str] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class RuntimeVqaMarkRequest(BaseModel):
    """Backend -> AI runtime VQA status sync request."""

    session_id: str = Field(min_length=1)
    vqa_passed: bool
    flow_state: FlowStateStr | None = None

    model_config = {"extra": "forbid"}


class RuntimeVqaMarkResponse(BaseModel):
    """VQA status sync response."""

    session_id: str
    vqa_passed: bool
    flow_state: FlowStateStr
    defense_tier: DefenseTierStr
    updated_ts_ms: int

    model_config = {"extra": "forbid"}
