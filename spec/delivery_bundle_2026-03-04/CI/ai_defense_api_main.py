"""Reference FastAPI main for AI Defense Runtime API v2 (bundle snapshot)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi import HTTPException

from .audit import DefenseDecisionAuditLogger
from .challenge_runtime import ChallengeConfig
from .challenge_runtime import ChallengeRuntime
from .models import ChallengeEventIngestRequest
from .models import ChallengeEventIngestResponse
from .models import ChallengeStartRequest
from .models import ChallengeStartResponse
from .models import ChallengeVerifyRequest
from .models import ChallengeVerifyResponse
from .models import EvaluateRequest
from .models import EvaluateResponse
from .models import HealthResponse
from .models import RuntimeStateSnapshot
from .policy import DecisionPolicy
from .policy import PolicyConfig
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
