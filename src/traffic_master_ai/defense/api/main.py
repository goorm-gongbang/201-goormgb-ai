from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

# 커스텀 메트릭: 검사된 요청 경로별 카운터
EVALUATE_REQUESTS = Counter(
    "ai_defense_evaluate_total",
    "Total evaluate requests by path, method, and decision",
    ["path", "method", "decision"],
)

# Prometheus instrumentator 인스턴스
instrumentator = Instrumentator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: 시작 시 Prometheus 메트릭 초기화"""
    # Startup: Prometheus 계측 및 /metrics 엔드포인트 노출
    # Note: /metrics는 클러스터 내부에서만 접근 가능 (Istio NetworkPolicy로 보호)
    instrumentator.instrument(app).expose(app)
    yield
    # Shutdown: 정리 작업 (필요시)


app = FastAPI(
    title="Traffic Master AI Defense API",
    version="bootstrap-v1",
    lifespan=lifespan,
)


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
    decision = "allow"  # TODO: 실제 로직에서 allow/deny 결정

    # 메트릭 기록: path, method, decision
    EVALUATE_REQUESTS.labels(path=req.path, method=req.method, decision=decision).inc()

    return EvaluateResponse(
        allow=True,
        session_id=req.session_id,
        flow_state="S5",
        defense_tier="T0",
        action=None,
        headers_to_add={},
    )
