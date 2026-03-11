from fastapi import FastAPI
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="Traffic Master AI Defense API", version="bootstrap-v1")

# Prometheus metrics 자동 계측 및 /metrics 엔드포인트 노출
Instrumentator().instrument(app).expose(app)


class EvaluateRequest(BaseModel):
    session_id: str
    path: str
    method: str
    headers: dict[str, str] = Field(default_factory=dict)
    timestamp: int | None = None


class EvaluateResponse(BaseModel):
    allow: bool
    session_id: str
    flow_state: str
    defense_tier: str
    action: str | None
    headers_to_add: dict[str, str] = Field(default_factory=dict)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "ai-defense", "version": "bootstrap-v1"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ready", "service": "ai-defense"}


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    return EvaluateResponse(
        allow=True,
        session_id=req.session_id,
        flow_state="S5",
        defense_tier="T0",
        action=None,
        headers_to_add={},
    )
