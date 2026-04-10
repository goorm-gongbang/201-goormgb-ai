"""Pydantic request/response models for AI Defense API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .runtime_flow_state import normalize_runtime_flow_state

FlowStateStr = Literal["F0", "F1", "F2", "F3", "F3R", "F3M", "F4", "F4R", "F4M", "FX"]
SeatModeStr = Literal["RECOMMENDATION", "MANUAL"]
DefenseTierStr = Literal["T0", "T1", "T2", "T3"]
DefenseActionStr = Literal["NONE", "CHALLENGE", "THROTTLE", "GATE", "BLOCK"]
ChallengeTypeStr = Literal["queue_gate", "catch_ball"]
ChallengeResultStr = Literal["PASSED", "FAILED", "BLOCKED", "EXPIRED"]
PointerEventTypeStr = Literal["down", "move", "up", "click"]
CanonicalTelemetryStageStr = Literal["QUEUE_ENTER_PRECLICK", "SEAT_STAGE", "VQA_CHALLENGE"]
CanonicalTelemetryEventTypeStr = Literal["mousemove", "mousedown", "mouseup", "click"]
TargetDefenseActionStr = Literal["NONE", "THROTTLE", "REQUIRE_S3", "BLOCK"]
TargetChallengeResultStr = Literal["PASS", "FAIL"]
TargetEvaluateEventTypeStr = Literal[
    "QUEUE_ENTER",
    "SEAT_ENTRY",
    "RECOMMENDATION_BLOCKS",
    "SECTION_BLOCKS",
    "ASSIGN_HOLD",
    "SEAT_HOLDS",
]


class EvaluateTelemetryFeatures(BaseModel):
    """Telemetry summary features for a single trigger window."""

    total_dist: float | None = Field(default=None, alias="totalDist")
    linear_dist: float | None = Field(default=None, alias="linearDist")
    linearity_ratio: float | None = Field(default=None, alias="linearityRatio")
    avg_velocity: float | None = Field(default=None, alias="avgVelocity")
    tremor_std_dev: float | None = Field(default=None, alias="tremorStdDev")
    dwell_time: float | None = Field(default=None, alias="dwellTime")
    path_ratio: float | None = Field(default=None, alias="pathRatio")
    timestamp: int | None = None

    model_config = {"populate_by_name": True, "extra": "forbid"}


class TelemetrySummary(BaseModel):
    """Compact five-feature telemetry summary used by target /ai routes."""

    tremor_std_dev: float = Field(alias="tremorStdDev")
    linearity_ratio: float = Field(alias="linearityRatio")
    avg_velocity: float = Field(alias="avgVelocity")
    dwell_time: float = Field(alias="dwellTime")
    path_ratio: float = Field(alias="pathRatio")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class EvaluateRequest(BaseModel):
    """Adapter -> AI defense decision request."""

    session_id: str = Field(min_length=1)
    trace_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    path: str = Field(min_length=1)
    method: str = Field(min_length=1, description="HTTP method such as GET/POST")
    user_id: str | None = Field(default=None, description="End-user identifier (userId) extracted from JWT")
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

    @field_validator("flow_state", mode="before")
    @classmethod
    def _normalize_flow_state(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = normalize_runtime_flow_state(str(value), default=None)
        if normalized is None:
            return value
        return normalized


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

    @field_validator("flow_state", mode="before")
    @classmethod
    def _normalize_flow_state(cls, value: Any) -> Any:
        normalized = normalize_runtime_flow_state(str(value), default=None)
        if normalized is None:
            return value
        return normalized


class HealthResponse(BaseModel):
    """Basic liveness/readiness response."""

    status: Literal["ok"]
    service: str
    version: str


class RuntimeStateSnapshot(BaseModel):
    """Runtime session state kept in Redis (or in-memory fallback)."""

    flow_state: FlowStateStr = "F0"
    seat_mode: SeatModeStr | None = None
    defense_tier: DefenseTierStr = "T0"
    risk_score: float = 0.0
    last_step_risk: float | None = None
    last_guard_ts_ms: int | None = None
    challenge_fail_count: int = 0
    seat_taken_streak: int = 0
    hold_fail_streak: int = 0
    heavy_budget_left: int = 2
    replan_budget_left: int = 3
    probation_until_ms: int | None = None
    policy_version: str = "def-pol-2.0.0"
    updated_ts_ms: int = 0
    user_id: str | None = Field(default=None, alias="userId")
    vqa_required: bool = True
    vqa_passed: bool = False
    vqa_attempt_count: int = 0
    vqa_retry_limit: int = 3
    vqa_last_result: ChallengeResultStr | None = None
    active_challenge_id: str | None = None
    active_challenge_expires_at_ms: int | None = None
    active_challenge_token: str = ""
    turnstile_verified: bool = False
    turnstile_verified_at_ms: int = 0
    latest_queue_enter_preclick_summary: dict[str, Any] = Field(default_factory=dict)
    latest_queue_enter_preclick_at_ms: int = 0
    latest_seat_stage_summary: dict[str, Any] = Field(default_factory=dict)
    latest_seat_stage_at_ms: int = 0
    latest_vqa_challenge_summary: dict[str, Any] = Field(default_factory=dict)
    latest_vqa_challenge_at_ms: int = 0
    vqa_behavior_score: float = 0.0

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @field_validator("flow_state", mode="before")
    @classmethod
    def _normalize_flow_state(cls, value: Any) -> Any:
        normalized = normalize_runtime_flow_state(str(value), default="F0")
        if normalized is None:
            return "F0"
        return normalized


class ChallengeStartRequest(BaseModel):
    """Start a one-time challenge gate."""

    session_id: str = Field(min_length=1)
    trace_id: str | None = None
    flow_state: FlowStateStr | None = None
    challenge_type: ChallengeTypeStr = "catch_ball"

    model_config = {"extra": "forbid"}

    @field_validator("flow_state", mode="before")
    @classmethod
    def _normalize_flow_state(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = normalize_runtime_flow_state(str(value), default=None)
        if normalized is None:
            return value
        return normalized


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

    @field_validator("flow_state", mode="before")
    @classmethod
    def _normalize_flow_state(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = normalize_runtime_flow_state(str(value), default=None)
        if normalized is None:
            return value
        return normalized


class RuntimeVqaMarkResponse(BaseModel):
    """VQA status sync response."""

    session_id: str
    vqa_passed: bool
    flow_state: FlowStateStr
    defense_tier: DefenseTierStr
    updated_ts_ms: int

    @field_validator("flow_state", mode="before")
    @classmethod
    def _normalize_flow_state(cls, value: Any) -> Any:
        normalized = normalize_runtime_flow_state(str(value), default=None)
        if normalized is None:
            return value
        return normalized


class AiPrecheckRequest(BaseModel):
    """Frontend -> AI direct route for queue-enter precheck."""

    match_id: int = Field(alias="matchId", ge=0)
    cf_token: str = Field(alias="cfToken", min_length=1)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AiPrecheckResponse(BaseModel):
    """Minimal queue-enter precheck response."""

    allowed: bool

    model_config = {"extra": "forbid"}


class RawTelemetryEvent(BaseModel):
    """Frontend raw telemetry event batch item."""

    type: CanonicalTelemetryEventTypeStr
    ts_ms: int = Field(alias="tsMs", ge=0)
    x_norm: float | None = Field(default=None, alias="xNorm", ge=0.0, le=1.0)
    y_norm: float | None = Field(default=None, alias="yNorm", ge=0.0, le=1.0)
    button: Literal[0, 1, 2] | None = None

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AiTelemetryIngestRequest(BaseModel):
    """Frontend -> AI raw telemetry batch ingest request."""

    match_id: int = Field(alias="matchId", ge=0)
    stage: CanonicalTelemetryStageStr = Field(
        description=(
            "Canonical telemetry stage. "
            "QUEUE_ENTER_PRECLICK = queue enter 직전, "
            "SEAT_STAGE = 좌석 탐색/선택 구간, "
            "VQA_CHALLENGE = 보안 관문 상호작용 구간."
        )
    )
    events: list[RawTelemetryEvent] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AiTelemetryIngestResponse(BaseModel):
    """Frontend-friendly telemetry ingest response."""

    accepted: bool

    model_config = {"extra": "forbid"}


class AiEvaluateEvent(BaseModel):
    """Authz Adapter -> AI event envelope."""

    event_type: TargetEvaluateEventTypeStr = Field(alias="eventType")
    request_path: str = Field(alias="requestPath", min_length=1)
    request_method: str = Field(alias="requestMethod", min_length=1)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AiEvaluateContext(BaseModel):
    """Authz Adapter -> AI context envelope."""

    sid: str = Field(min_length=1)
    user_id: str | None = Field(default=None, alias="userId", min_length=1)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AiEvaluateRequest(BaseModel):
    """Authz Adapter -> AI evaluate request for target /ai/evaluate."""

    event: AiEvaluateEvent
    context: AiEvaluateContext

    model_config = {"extra": "forbid"}


class AiEvaluateDecision(BaseModel):
    """Minimal target decision payload."""

    action: TargetDefenseActionStr

    model_config = {"extra": "forbid"}


class AiEvaluateResponse(BaseModel):
    """Minimal target evaluate response."""

    decision: AiEvaluateDecision

    model_config = {"extra": "forbid"}


class AiChallengeStartRequest(BaseModel):
    """Frontend -> AI direct route for challenge issuance."""

    match_id: int = Field(alias="matchId", ge=0)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AiChallengeStartResponse(BaseModel):
    """Minimal target challenge-start response."""

    challenge_id: str = Field(alias="challengeId")
    remaining_attempts: int = Field(alias="remainingAttempts", ge=0)
    expires_at_ms: int = Field(alias="expiresAtMs", ge=0)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AiChallengeVerifyRequest(BaseModel):
    """Frontend -> AI challenge verification request."""

    match_id: int = Field(alias="matchId", ge=0)
    challenge_id: str = Field(alias="challengeId", min_length=1)
    caught: bool
    catch_ts_ms: int = Field(alias="catchTsMs", ge=0)
    catch_x_norm: float = Field(alias="catchXNorm", ge=0.0, le=1.0)
    catch_y_norm: float = Field(alias="catchYNorm", ge=0.0, le=1.0)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class AiChallengeVerifyResponse(BaseModel):
    """Minimal target challenge-verify response."""

    success: bool
    remaining_attempts: int = Field(alias="remainingAttempts", ge=0)
    reason: str | None = None

    model_config = {"populate_by_name": True, "extra": "forbid"}
