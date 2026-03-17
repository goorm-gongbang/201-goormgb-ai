"""Unified FastAPI app for AI Defense.

Primary runtime logic follows teammate D0-MVP implementation.
Legacy endpoints are preserved as compatibility routes.
Includes Prometheus metrics instrumentation.
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

from ..d0_mvp.api.admin_console import create_admin_console_router
from ..d0_mvp.api.challenge_api import create_challenge_router as create_d0_challenge_router
from ..d0_mvp.api.check import create_check_router
from ..d0_mvp.api.runtime import DefenseRuntime as D0DefenseRuntime
from ..d0_mvp.core.enums import DefenseAction as D0DefenseAction
from ..d0_mvp.core.enums import FlowState as D0FlowState
from ..d0_mvp.core.models import CheckRequest as D0CheckRequest
from .audit import DefenseDecisionAuditLogger
from .challenge_runtime import ChallengeConfig, ChallengeRuntime
from .models import (
    ChallengeEventIngestRequest,
    ChallengeEventIngestResponse,
    ChallengeStartRequest,
    ChallengeStartResponse,
    ChallengeVerifyRequest,
    ChallengeVerifyResponse,
    EvaluateRequest,
    EvaluateResponse,
    HealthResponse,
    RuntimeStateSnapshot,
    RuntimeVqaMarkRequest,
    RuntimeVqaMarkResponse,
)
from .state import build_runtime_store_from_env

# Custom Metrics
EVALUATE_REQUESTS = Counter(
    "ai_defense_evaluate_total",
    "Total evaluate requests by path, method, and decision",
    ["path", "method", "decision"],
)

instrumentator = Instrumentator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: Initialize Prometheus metrics on startup."""
    instrumentator.instrument(app).expose(app)
    yield


app = FastAPI(
    title="Traffic Master AI Defense API",
    version="v2",
    description=(
        "Unified defense API. D0-MVP runtime is canonical; legacy challenge/runtime "
        "contracts remain for compatibility."
    ),
    lifespan=lifespan,
)

_state_store, _state_backend = build_runtime_store_from_env()
_audit = DefenseDecisionAuditLogger.from_env()
_challenge_runtime = ChallengeRuntime(ChallengeConfig.from_env())
_d0_runtime = D0DefenseRuntime()

# [Gap Closing] Load Backend Sanction URL from env
BE_SANCTION_URL = os.getenv("TM_BACKEND_SANCTION_URL")


async def _send_be_sanction(user_id: str, reason: str):
    """Asynchronously notify backend to revoke user session."""
    if not BE_SANCTION_URL or not user_id:
        return

    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            payload = {
                "userId": user_id,
                "reason": f"[AI-Defense] {reason}",
                "action": "REVOKE_SESSION",
            }
            await client.post(BE_SANCTION_URL, json=payload)
        except Exception:
            # Shield AI performance from BE failures
            pass


# Expose teammate runtime routers directly.
app.include_router(create_check_router(_d0_runtime))
app.include_router(create_d0_challenge_router(_d0_runtime))
app.include_router(create_admin_console_router(_d0_runtime))


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service="ai-defense", version="v2")


@app.get("/readyz", response_model=HealthResponse, tags=["health"])
async def readyz() -> HealthResponse:
    return HealthResponse(status="ok", service="ai-defense", version="v2")


@app.get("/runtime/{session_id}", response_model=RuntimeStateSnapshot, tags=["state"])
async def runtime_state(session_id: str) -> RuntimeStateSnapshot:
    snap = _state_store.get(session_id)
    if snap is not None:
        return snap

    d0_state = _d0_runtime.session_state.get(session_id)
    if d0_state is None:
        raise HTTPException(status_code=404, detail="session not found")
    policy = _d0_runtime.policy_loader.load(session_id=session_id)
    bridged = _legacy_snapshot_from_d0_state(
        session_id=session_id,
        d0_state=d0_state,
        policy_version=policy.policy_version,
        challenge_max_attempts=policy.challenge_max_attempts,
        now_ms=int(time.time() * 1000),
    )
    _state_store.upsert(session_id, bridged)
    return bridged


@app.post("/evaluate", response_model=EvaluateResponse, tags=["decision"])
async def evaluate(req: EvaluateRequest, background_tasks: BackgroundTasks) -> EvaluateResponse:
    started_at = time.perf_counter()
    now_ms = int(time.time() * 1000)

    d0_check_req = _legacy_request_to_d0_check(req)
    d0_eval_req = _d0_runtime.check_request_to_evaluate(d0_check_req)
    telemetry_features = _legacy_features_to_d0(req)
    if telemetry_features:
        d0_eval_req.context.features = telemetry_features
    try:
        out = _d0_runtime.evaluate(d0_eval_req)
    except Exception as exc:  # noqa: BLE001 - fail-open policy
        out = _d0_runtime.fail_open_on_unavailable(request=d0_eval_req, error=exc)

    resp = _legacy_response_from_d0(req=req, started_at=started_at, out=out)

    # [Gap Closing] Trigger async backend sanction if status is BLOCK
    if resp.action == "BLOCK" and req.user_id:
        background_tasks.add_task(
            _send_be_sanction, user_id=req.user_id, reason=resp.reason or "AI identified as BOT"
        )

    # Record metrics
    EVALUATE_REQUESTS.labels(path=req.path, method=req.method, decision=resp.action).inc()

    snap = _legacy_snapshot_from_d0_state(
        session_id=req.session_id,
        d0_state=_d0_runtime.session_state.get(req.session_id),
        policy_version=out.policy.policy_version,
        challenge_max_attempts=out.policy.challenge_max_attempts,
        now_ms=now_ms,
    )
    _state_store.upsert(req.session_id, snap)
    _audit.log(req, resp, snap)
    return resp


@app.post("/challenge/start", response_model=ChallengeStartResponse, tags=["challenge"])
async def challenge_start(req: ChallengeStartRequest) -> ChallengeStartResponse:
    snap = _state_store.get(req.session_id) or RuntimeStateSnapshot()
    resp, next_snap = _challenge_runtime.start(req, snap)
    _state_store.upsert(req.session_id, next_snap)
    _audit.log_challenge_event(
        session_id=req.session_id,
        challenge_id=resp.challenge_id,
        event_type="CHALLENGE_ISSUED",
        payload={
            "challenge_type": resp.challenge_type,
            "attempt_limit": resp.attempt_limit,
            "expires_at_ms": resp.expires_at_ms,
            "public_params": resp.public_params,
        },
    )
    return resp


@app.post("/challenge/event", response_model=ChallengeEventIngestResponse, tags=["challenge"])
async def challenge_event(req: ChallengeEventIngestRequest) -> ChallengeEventIngestResponse:
    try:
        resp = _challenge_runtime.ingest_events(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return resp


@app.post("/challenge/verify", response_model=ChallengeVerifyResponse, tags=["challenge"])
async def challenge_verify(req: ChallengeVerifyRequest) -> ChallengeVerifyResponse:
    snap = _state_store.get(req.session_id) or RuntimeStateSnapshot()
    try:
        resp, next_snap = _challenge_runtime.verify(req, snap)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _state_store.upsert(req.session_id, next_snap)
    _audit.log_challenge_event(
        session_id=req.session_id,
        challenge_id=req.challenge_id,
        event_type="CHALLENGE_VERIFIED",
        payload={
            "result": resp.result,
            "passed": resp.passed,
            "attempts_used": resp.attempts_used,
            "attempts_left": resp.attempts_left,
            "reason": resp.reason,
        },
    )
    return resp


@app.get("/meta/storage", tags=["state"])
async def storage_meta() -> dict[str, str]:
    return {"runtime_state_backend": _state_backend}


@app.post("/runtime/vqa/mark", response_model=RuntimeVqaMarkResponse, tags=["state"])
async def runtime_mark_vqa(req: RuntimeVqaMarkRequest) -> RuntimeVqaMarkResponse:
    now_ms = int(time.time() * 1000)
    snap = _state_store.get(req.session_id) or RuntimeStateSnapshot(updated_ts_ms=now_ms)

    if req.vqa_passed:
        next_flow = req.flow_state or ("S4" if snap.flow_state == "S3" else snap.flow_state)
        next_snap = snap.model_copy(
            update={
                "flow_state": next_flow,
                "vqa_required": False,
                "vqa_passed": True,
                "vqa_last_result": "PASSED",
                "active_challenge_id": None,
                "active_challenge_expires_at_ms": None,
                "updated_ts_ms": now_ms,
            }
        )
    else:
        next_flow = req.flow_state or snap.flow_state
        next_snap = snap.model_copy(
            update={
                "flow_state": next_flow,
                "vqa_required": True,
                "vqa_passed": False,
                "updated_ts_ms": now_ms,
            }
        )

    _state_store.upsert(req.session_id, next_snap)
    _sync_mark_to_d0_runtime(req=req, now_ms=now_ms)
    return RuntimeVqaMarkResponse(
        session_id=req.session_id,
        vqa_passed=next_snap.vqa_passed,
        flow_state=next_snap.flow_state,
        defense_tier=next_snap.defense_tier,
        updated_ts_ms=next_snap.updated_ts_ms,
    )


def _legacy_request_to_d0_check(req: EvaluateRequest) -> D0CheckRequest:
    trace_id = req.trace_id or req.request_id or f"trace-{uuid.uuid4().hex[:12]}"
    return D0CheckRequest(
        session_id=req.session_id,
        trace_id=trace_id,
        upstream_path=req.path,
        upstream_method=req.method.upper(),
        flow_state=_to_d0_flow_state(req.flow_state),
        original_query=None,
        client_ip_hash=None,
        turnstile_token=(req.headers or {}).get("x-turnstile-token"),
        category=_to_api_category(req.method),
        status_code=None,
    )


def _legacy_response_from_d0(
    *,
    req: EvaluateRequest,
    started_at: float,
    out: Any,
) -> EvaluateResponse:
    orchestrated = out.orchestrator_result
    decision = orchestrated.decision
    action = _legacy_action_from_d0(decision.action)
    reason = _legacy_reason(orchestrated=orchestrated, decision=decision)

    rule_hits = _collect_rule_hits(out)
    flow_state_value = (orchestrated.state_to or orchestrated.state_from).value
    headers = _legacy_headers_from_d0(
        action=action,
        tier=decision.tier.value,
        policy_version=decision.policy_version,
        throttle_ms=decision.throttle_ms,
        reason=reason,
    )
    latency_ms = max(0, int((time.perf_counter() - started_at) * 1000))
    return EvaluateResponse(
        allow=bool(orchestrated.allow),
        session_id=req.session_id,
        flow_state=flow_state_value,  # type: ignore[arg-type]
        defense_tier=decision.tier.value,  # type: ignore[arg-type]
        action=action,  # type: ignore[arg-type]
        actions=[action],  # type: ignore[list-item]
        reason=reason,
        rule_hits=rule_hits,
        risk_score=float(out.guard_output.r_new),
        policy_version=decision.policy_version,
        headers_to_add=headers,
        decision_id=f"dec-{uuid.uuid4().hex[:12]}",
        latency_ms=latency_ms,
        version="v2",
    )


def _legacy_snapshot_from_d0_state(
    *,
    session_id: str,
    d0_state: Any,
    policy_version: str,
    challenge_max_attempts: int,
    now_ms: int,
) -> RuntimeStateSnapshot:
    if d0_state is None:
        return RuntimeStateSnapshot(updated_ts_ms=now_ms, policy_version=policy_version)

    grace = _d0_runtime.session_state.get_s3_grace(session_id) or {}
    last_result: Optional[str] = None
    if bool(getattr(d0_state, "s3_passed", False)):
        last_result = "PASSED"
    elif int(getattr(d0_state, "challenge_fail_count", 0)) > 0:
        last_result = "FAILED"

    return RuntimeStateSnapshot(
        flow_state=d0_state.flow_state.value,  # type: ignore[arg-type]
        defense_tier=d0_state.defense_tier.value,  # type: ignore[arg-type]
        risk_score=float(d0_state.risk_score),
        challenge_fail_count=int(d0_state.challenge_fail_count),
        seat_taken_streak=int(d0_state.seat_taken_streak),
        hold_fail_streak=int(d0_state.hold_fail_streak),
        heavy_budget_left=2,
        replan_budget_left=3,
        probation_until_ms=d0_state.probation_until_ms,
        policy_version=policy_version,
        updated_ts_ms=now_ms,
        vqa_required=not bool(d0_state.s3_passed),
        vqa_passed=bool(d0_state.s3_passed),
        vqa_attempt_count=int(d0_state.challenge_fail_count),
        vqa_retry_limit=max(1, int(challenge_max_attempts)),
        vqa_last_result=last_result,  # type: ignore[arg-type]
        active_challenge_id=_opt_str(grace.get("lastChallengeId")),
        active_challenge_expires_at_ms=_opt_int(grace.get("graceUntilMs")),
    )


def _collect_rule_hits(out: Any) -> list[str]:
    collected: list[str] = []
    candidates = (
        list(getattr(out.guard_output, "rule_hits", ())),
        list(getattr(out.analyzer_output.evidence_update, "rule_hits", ())),
        [getattr(out.planner_plan, "reason", None)],
        [getattr(out.orchestrator_result.decision, "reason", None)],
        [
            out.orchestrator_result.reason_code.value
            if getattr(out.orchestrator_result, "reason_code", None) is not None
            else None
        ],
    )
    for group in candidates:
        for item in group:
            if not item:
                continue
            value = str(item)
            if value not in collected:
                collected.append(value)
    return collected


def _legacy_reason(*, orchestrated: Any, decision: Any) -> Optional[str]:
    if getattr(orchestrated, "reason_code", None) is not None:
        return orchestrated.reason_code.value
    if getattr(orchestrated, "error", None) is not None and getattr(
        orchestrated.error, "reason_code", None
    ):
        return str(orchestrated.error.reason_code)
    if getattr(decision, "reason", None):
        return str(decision.reason).upper()
    return None


def _legacy_action_from_d0(action: D0DefenseAction) -> str:
    if action == D0DefenseAction.REQUIRE_S3:
        return "CHALLENGE"
    if action == D0DefenseAction.THROTTLE:
        return "THROTTLE"
    if action == D0DefenseAction.BLOCK:
        return "BLOCK"
    return "NONE"


def _legacy_headers_from_d0(
    *,
    action: str,
    tier: str,
    policy_version: str,
    throttle_ms: Optional[int],
    reason: Optional[str],
) -> dict[str, str]:
    headers = {
        "x-defense-policy-version": policy_version,
        "x-defense-tier": tier,
        "x-defense-action": action.lower(),
        "x-defense-actions": action.lower(),
    }
    if throttle_ms is not None:
        headers["x-throttle-ms"] = str(int(throttle_ms))
    if action == "CHALLENGE":
        headers["x-challenge-required"] = "true"
        headers["x-challenge-type"] = "queue_gate"
    if action == "BLOCK":
        headers["x-block-reason"] = (reason or "blocked").lower()
    return headers


def _to_d0_flow_state(value: Optional[str]) -> D0FlowState:
    if value is None:
        return D0FlowState.S0
    normalized = {"S4R": "S4", "S5R": "S5"}.get(value, value)
    try:
        return D0FlowState(normalized)
    except ValueError:
        return D0FlowState.S0


def _to_api_category(method: str) -> str:
    method_upper = method.upper()
    if method_upper in {"GET", "HEAD", "OPTIONS"}:
        return "READ"
    return "WRITE"


def _legacy_features_to_d0(req: EvaluateRequest) -> Optional[dict[str, Any]]:
    if req.telemetry_features is None:
        return None
    raw = req.telemetry_features.model_dump(by_alias=True, exclude_none=True)
    if not raw:
        return None

    features: dict[str, Any] = {}
    for key in ("tremorStdDev", "linearityRatio", "avgVelocity", "dwellTime"):
        value = raw.get(key)
        if value is not None:
            features[key] = value

    total_dist = _to_float(raw.get("totalDist"))
    linear_dist = _to_float(raw.get("linearDist"))
    if total_dist is not None:
        features["totalDist"] = total_dist
    if linear_dist is not None:
        features["linearDist"] = linear_dist
    if total_dist is not None and linear_dist is not None and linear_dist > 0:
        features["pathRatio"] = total_dist / max(linear_dist, 1e-6)

    timestamp = _opt_int(raw.get("timestamp"))
    if timestamp is not None:
        features["timestamp"] = timestamp

    return features or None


def _opt_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except Exception:  # noqa: BLE001 - defensive decode fallback
            return None
    text = str(value).strip()
    return text or None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sync_mark_to_d0_runtime(*, req: RuntimeVqaMarkRequest, now_ms: int) -> None:
    session_id = req.session_id
    existing = _d0_runtime.session_state.get_or_create(session_id)
    flow_state = _to_d0_flow_state(req.flow_state) if req.flow_state else existing.flow_state
    if req.vqa_passed:
        _d0_runtime.session_state.update_by_role(
            "orchestrator",
            session_id,
            {
                "flowState": flow_state.value,
                "s3Passed": 1,
                "s3PassedAtMs": now_ms,
                "lastDecisionAction": "NONE",
            },
            is_allow=True,
        )
        _d0_runtime.session_state.update_by_role(
            "analyzer",
            session_id,
            {
                "challengeFailCount": 0,
            },
            is_allow=True,
        )
        return

    _d0_runtime.session_state.update_by_role(
        "orchestrator",
        session_id,
        {
            "flowState": flow_state.value,
            "s3Passed": 0,
            "lastDecisionAction": "REQUIRE_S3",
        },
        is_allow=False,
    )
