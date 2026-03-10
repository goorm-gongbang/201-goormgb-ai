"""FastAPI app for AI Defense runtime API."""

from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException

from .audit import DefenseDecisionAuditLogger
from .challenge_runtime import ChallengeConfig, ChallengeRuntime
from .models import (
    ChallengeEventIngestRequest,
    ChallengeEventIngestResponse,
    RuntimeVqaMarkRequest,
    RuntimeVqaMarkResponse,
    ChallengeStartRequest,
    ChallengeStartResponse,
    ChallengeVerifyRequest,
    ChallengeVerifyResponse,
    EvaluateRequest,
    EvaluateResponse,
    HealthResponse,
    RuntimeStateSnapshot,
)
from .policy import DecisionPolicy, PolicyConfig
from .state import build_runtime_store_from_env

app = FastAPI(
    title="Traffic Master AI Defense API",
    version="v2",
    description=(
        "Deterministic defense runtime API for ext_authz adapter integration. "
        "Includes evaluate + challenge start/verify/event contracts."
    ),
)
_state_store, _state_backend = build_runtime_store_from_env()
_policy = DecisionPolicy(PolicyConfig.from_env(), _state_store)
_audit = DefenseDecisionAuditLogger.from_env()
_challenge_runtime = ChallengeRuntime(ChallengeConfig.from_env())


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service="ai-defense", version="v2")


@app.get("/readyz", response_model=HealthResponse, tags=["health"])
async def readyz() -> HealthResponse:
    return HealthResponse(status="ok", service="ai-defense", version="v2")


@app.get("/runtime/{session_id}", response_model=RuntimeStateSnapshot, tags=["state"])
async def runtime_state(session_id: str) -> RuntimeStateSnapshot:
    snap = _state_store.get(session_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="session not found")
    return snap


@app.post("/evaluate", response_model=EvaluateResponse, tags=["decision"])
async def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    resp, snap = _policy.evaluate(req)
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
    return RuntimeVqaMarkResponse(
        session_id=req.session_id,
        vqa_passed=next_snap.vqa_passed,
        flow_state=next_snap.flow_state,
        defense_tier=next_snap.defense_tier,
        updated_ts_ms=next_snap.updated_ts_ms,
    )
