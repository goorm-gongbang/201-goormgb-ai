"""FastAPI app for AI Defense mock evaluate API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi import HTTPException

from .audit import DefenseDecisionAuditLogger
from .models import EvaluateRequest, EvaluateResponse, HealthResponse, RuntimeStateSnapshot
from .policy import DecisionPolicy, PolicyConfig
from .state import build_runtime_store_from_env


app = FastAPI(
    title="Traffic Master AI Defense API",
    version="v1",
    description=(
        "Mock/stub API for cloud ext_authz integration. "
        "Deterministic rule-based decisions until full defense engine rollout. "
        "Contract fields are fixed; thresholds and policy defaults are tunable."
    ),
)
_state_store, _state_backend = build_runtime_store_from_env()
_policy = DecisionPolicy(PolicyConfig.from_env(), _state_store)
_audit = DefenseDecisionAuditLogger.from_env()


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service="ai-defense", version="v1")


@app.get("/readyz", response_model=HealthResponse, tags=["health"])
async def readyz() -> HealthResponse:
    return HealthResponse(status="ok", service="ai-defense", version="v1")


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


@app.get("/meta/storage", tags=["state"])
async def storage_meta() -> dict[str, str]:
    return {"runtime_state_backend": _state_backend}
