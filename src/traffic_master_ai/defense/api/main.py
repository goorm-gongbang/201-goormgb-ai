"""Unified FastAPI app for AI Defense.

Primary runtime logic follows teammate D0-MVP implementation.
Legacy endpoints are preserved as compatibility routes.
Includes Prometheus metrics instrumentation + OpenTelemetry.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
import jwt
from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

# OpenTelemetry imports
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.resource import ResourceAttributes

from ..d0_mvp.api.runtime import DefenseRuntime as DecisionEngineRuntime
from ..d0_mvp.core.enums import DefenseAction as D0DefenseAction
from ..d0_mvp.core.enums import FlowState as D0FlowState
from ..d0_mvp.core.models import CheckRequest as D0CheckRequest
from ..d0_mvp.events.common import RuntimeEvent as D0RuntimeEvent
from ..d0_mvp.state.redis_client import build_runtime_redis_from_env
from ..auth_guard import AuthGuardBlockService
from .audit import (
    DefenseDecisionAuditLogger,
    S3Uploader,
    rotate_and_upload_audit_log,
)
from .challenge_runtime import ChallengeConfig, ChallengeRuntime
from .models import (
    AiChallengeStartRequest,
    AiChallengeStartResponse,
    AiChallengeVerifyRequest,
    AiChallengeVerifyResponse,
    AiEvaluateRequest,
    AiEvaluateResponse,
    AiPrecheckRequest,
    AiPrecheckResponse,
    AiTelemetryIngestRequest,
    AiTelemetryIngestResponse,
    ChallengeEventIngestRequest,
    ChallengeEventIngestResponse,
    ChallengeStartRequest,
    ChallengeStartResponse,
    ChallengeVerifyRequest,
    ChallengeVerifyResponse,
    EvaluateRequest,
    EvaluateResponse,
    EvaluateTelemetryFeatures,
    HealthResponse,
    RawTelemetryEvent,
    RuntimeStateSnapshot,
    RuntimeVqaMarkRequest,
    RuntimeVqaMarkResponse,
)
from .state import build_runtime_store_from_env

# Custom Prometheus Metrics
EVALUATE_REQUESTS = Counter(
    "ai_defense_evaluate_total",
    "Total evaluate requests by decision",
    ["decision"],
)

PRECHECK_REQUESTS = Counter(
    "ai_defense_precheck_total",
    "Total precheck requests by result",
    ["result"],  # pass, fail
)

CHALLENGE_START_REQUESTS = Counter(
    "ai_defense_challenge_start_total",
    "Total challenge start requests",
)

CHALLENGE_VERIFY_REQUESTS = Counter(
    "ai_defense_challenge_verify_total",
    "Total challenge verify requests by result",
    ["result"],  # pass, fail
)

VQA_TELEMETRY_SCORE_REQUESTS = Counter(
    "ai_defense_vqa_telemetry_score_total",
    "Total VQA telemetry scoring outcomes",
    ["decision"],  # skip, observe, allow, terminal
)

TELEMETRY_INGEST_REQUESTS = Counter(
    "ai_defense_telemetry_ingest_total",
    "Total telemetry ingest requests by stage",
    ["stage"],  # QUEUE_ENTER_PRECLICK, VQA_CHALLENGE, SEAT_STAGE
)

instrumentator = Instrumentator()

# =============================================================================
# OpenTelemetry Setup
# =============================================================================
_OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector.monitoring.svc.cluster.local:4317")
_OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "ai-defense")
_OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"


def _setup_opentelemetry() -> None:
    """Configure OpenTelemetry with OTLP exporters."""
    if not _OTEL_ENABLED:
        logging.getLogger(__name__).info("OpenTelemetry disabled (OTEL_ENABLED=false)")
        return

    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: _OTEL_SERVICE_NAME,
        ResourceAttributes.SERVICE_NAMESPACE: os.getenv("OTEL_SERVICE_NAMESPACE", "dev-ai"),
        ResourceAttributes.SERVICE_VERSION: "v2",
    })

    # Tracer setup
    tracer_provider = TracerProvider(resource=resource)
    try:
        span_exporter = OTLPSpanExporter(endpoint=_OTEL_ENDPOINT, insecure=True)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to setup OTLP trace exporter: %s", exc)

    # Meter setup
    try:
        metric_exporter = OTLPMetricExporter(endpoint=_OTEL_ENDPOINT, insecure=True)
        metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=15000)
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to setup OTLP metric exporter: %s", exc)

    logging.getLogger(__name__).info("OpenTelemetry configured: endpoint=%s, service=%s", _OTEL_ENDPOINT, _OTEL_SERVICE_NAME)


# Initialize OpenTelemetry at module load
_setup_opentelemetry()


logger = logging.getLogger(__name__)

_MATCH_ID_PATH_RE = re.compile(r"/matches/(?P<match_id>\d+)(?:/|$)")

# S3 Archiver Config
_S3_BUCKET = os.getenv("TM_S3_BUCKET")
_S3_PREFIX = os.getenv("TM_S3_PREFIX", "ai-defense/audit/")
_S3_REGION = os.getenv("TM_S3_REGION")
_S3_INTERVAL = int(os.getenv("TM_S3_ARCHIVE_INTERVAL_SECONDS", "3600"))
_TURNSTILE_SECRET_KEY = os.getenv("TM_TURNSTILE_SECRET_KEY", "").strip()
_TURNSTILE_SITEVERIFY_URL = os.getenv(
    "TM_TURNSTILE_SITEVERIFY_URL",
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
)
_TURNSTILE_TIMEOUT_MS = int(os.getenv("TM_TURNSTILE_VERIFY_TIMEOUT_MS", "500"))
_PRECHECK_TTL_MS = int(os.getenv("TM_PRECHECK_TTL_MS", "300000"))
_VQA_TERMINAL_RISK_THRESHOLD = float(os.getenv("TM_VQA_TERMINAL_RISK_THRESHOLD", "0.92"))
_VQA_REVIEW_RISK_FLOOR = float(os.getenv("TM_VQA_REVIEW_RISK_FLOOR", "0.84"))
_VQA_EXTREME_LINEARITY_THRESHOLD = float(os.getenv("TM_VQA_EXTREME_LINEARITY_THRESHOLD", "0.985"))
_VQA_EXTREME_PATH_RATIO_THRESHOLD = float(os.getenv("TM_VQA_EXTREME_PATH_RATIO_THRESHOLD", "1.03"))
_VQA_LOW_TREMOR_THRESHOLD = float(os.getenv("TM_VQA_LOW_TREMOR_THRESHOLD", "0.20"))
_VQA_HIGH_VELOCITY_THRESHOLD = float(os.getenv("TM_VQA_HIGH_VELOCITY_THRESHOLD", "2200"))
_VQA_LOW_DWELL_THRESHOLD = float(os.getenv("TM_VQA_LOW_DWELL_THRESHOLD", "80"))
_VQA_MIN_POINTS_FOR_ABNORMAL_TERMINAL = int(os.getenv("TM_VQA_MIN_POINTS_FOR_ABNORMAL_TERMINAL", "6"))
_VQA_MIN_STRONG_SIGNALS_FOR_TERMINAL = int(os.getenv("TM_VQA_MIN_STRONG_SIGNALS_FOR_TERMINAL", "3"))

_S3_UPLOADER = S3Uploader(bucket=_S3_BUCKET, prefix=_S3_PREFIX, region=_S3_REGION) if _S3_BUCKET else None

_DEFAULT_CORS_ALLOW_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://staging.playball.one",
    "https://playball.one",
)


def _cors_allow_origins_from_env() -> list[str]:
    raw = os.getenv("TM_CORS_ALLOW_ORIGINS", "")
    configured = [origin.strip() for origin in raw.split(",") if origin.strip()]
    merged = list(dict.fromkeys([*_DEFAULT_CORS_ALLOW_ORIGINS, *configured]))
    return merged


async def _s3_archive_loop():
    """Background loop to periodically upload logs to S3."""
    if not _S3_UPLOADER:
        logger.info("S3 Archiving is disabled (TM_S3_BUCKET not set).")
        return

    logger.info("Starting S3 Archiving Loop (Interval: %ds)", _S3_INTERVAL)
    while True:
        try:
            await asyncio.sleep(_S3_INTERVAL)
            rotate_and_upload_audit_log(_audit, _S3_UPLOADER)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Error in S3 archiving loop: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI lifespan: Startup/Shutdown hooks."""
    archive_task = asyncio.create_task(_s3_archive_loop())
    yield
    archive_task.cancel()
    try:
        await archive_task
    except asyncio.CancelledError:
        pass
    auth_guard_close = getattr(_auth_guard_blocker, "close", None)
    if callable(auth_guard_close):
        auth_guard_close()
    decision_engine_close = getattr(_decision_engine, "close", None)
    if callable(decision_engine_close):
        decision_engine_close()


app = FastAPI(
    title="Traffic Master AI Defense API",
    version="v2",
    description=(
        "Unified defense API. D0-MVP runtime is canonical; legacy challenge/runtime "
        "contracts remain for compatibility."
    ),
    lifespan=lifespan,
)

_cors_allow_origins = _cors_allow_origins_from_env()
if _cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS enabled for origins: %s", ", ".join(_cors_allow_origins))

# [Gap Closing] Instrument app at the start (to allow middleware addition)
instrumentator.instrument(app)

# OpenTelemetry FastAPI instrumentation (adds http_server_request_duration_seconds_* metrics)
if _OTEL_ENABLED:
    FastAPIInstrumentor.instrument_app(app)

_state_store, _state_backend = build_runtime_store_from_env()
_decision_state_redis, _decision_state_backend = build_runtime_redis_from_env()
_audit = DefenseDecisionAuditLogger.from_env()
_challenge_runtime = ChallengeRuntime(ChallengeConfig.from_env())
_decision_engine = DecisionEngineRuntime(
    redis=_decision_state_redis,
    close_redis_on_close=_decision_state_backend == "redis",
)
_auth_guard_blocker = AuthGuardBlockService.from_env()


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service="ai-defense", version="v2")


@app.get("/readyz", response_model=HealthResponse, tags=["health"], include_in_schema=False)
async def readyz() -> HealthResponse:
    return HealthResponse(status="ok", service="ai-defense", version="v2")


@app.get("/runtime/{session_id}", response_model=RuntimeStateSnapshot, tags=["state"], include_in_schema=False)
async def runtime_state(session_id: str) -> RuntimeStateSnapshot:
    snap = _state_store.get(session_id)
    if snap is not None:
        return snap

    decision_state = _decision_engine.session_state.get(session_id)
    if decision_state is None:
        raise HTTPException(status_code=404, detail="session not found")
    policy = _decision_engine.policy_loader.load(session_id=session_id)
    bridged = _legacy_snapshot_from_d0_state(
        session_id=session_id,
        d0_state=decision_state,
        policy_version=policy.policy_version,
        challenge_max_attempts=policy.challenge_max_attempts,
        now_ms=int(time.time() * 1000),
    )
    _state_store.upsert(session_id, bridged)
    return bridged


async def _start_challenge_internal(req: ChallengeStartRequest) -> ChallengeStartResponse:
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


async def _verify_challenge_internal(req: ChallengeVerifyRequest) -> ChallengeVerifyResponse:
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


@app.post("/ai/precheck", response_model=AiPrecheckResponse, tags=["precheck"])
async def ai_precheck(
    request: Request,
    req: AiPrecheckRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> AiPrecheckResponse:
    sid = _resolve_session_id(
        request.headers.get("X-Auth-Sid") or request.headers.get("X-Session-Id"),
        authorization,
    )
    state_key = _build_state_key(sid, req.match_id)
    now_ms = int(time.time() * 1000)
    user_id = _resolve_user_id(
        explicit_user_id=None,
        x_user_id=x_user_id,
        authorization=authorization,
    )
    _remember_runtime_user_id(session_id=sid, user_id=user_id, now_ms=now_ms)
    passed = await _verify_turnstile_token(req.cf_token)
    snap = _get_or_create_snapshot(state_key, now_ms)
    if passed:
        next_snap = _reset_match_state_for_new_booking_attempt(
            snap=snap,
            now_ms=now_ms,
            user_id=user_id,
        ).model_copy(
            update={
                "turnstile_verified": True,
                "turnstile_verified_at_ms": now_ms,
            }
        )
        _reset_sid_level_vqa_state(
            sid=sid,
            now_ms=now_ms,
            user_id=user_id,
        )
        _decision_engine.session_state.delete(state_key)
        _decision_engine.session_state.delete(sid)
    else:
        next_snap = snap.model_copy(
            update={
                "turnstile_verified": False,
                "turnstile_verified_at_ms": 0,
                "updated_ts_ms": now_ms,
                "user_id": user_id or snap.user_id,
            }
        )
    _state_store.upsert(state_key, next_snap)
    PRECHECK_REQUESTS.labels(result="pass" if passed else "fail").inc()
    return AiPrecheckResponse(allowed=passed)


@app.post("/ai/telemetry/ingest", response_model=AiTelemetryIngestResponse, tags=["telemetry"])
async def ai_telemetry_ingest(
    request: Request,
    req: AiTelemetryIngestRequest = Body(
        ...,
        openapi_examples={
            "queueEnterPreclick": {
                "summary": "QUEUE_ENTER_PRECLICK raw batch 예시",
                "description": "queue enter 직전 segment raw event batch를 보내고, AI가 summary를 계산하는 형태",
                "value": {
                    "matchId": 687,
                    "stage": "QUEUE_ENTER_PRECLICK",
                    "events": [
                        {
                            "type": "mousemove",
                            "tsMs": 1773817200000,
                            "xNorm": 0.42,
                            "yNorm": 0.77,
                        },
                        {
                            "type": "mousemove",
                            "tsMs": 1773817200050,
                            "xNorm": 0.43,
                            "yNorm": 0.78,
                        },
                        {
                            "type": "click",
                            "tsMs": 1773817200200,
                            "xNorm": 0.47,
                            "yNorm": 0.80,
                            "button": 0,
                        },
                    ],
                },
            },
            "seatStage": {
                "summary": "SEAT_STAGE raw batch 예시",
                "description": "좌석 탐색 segment의 raw event batch를 보내고, AI가 최신 summary를 갱신하는 형태",
                "value": {
                    "matchId": 687,
                    "stage": "SEAT_STAGE",
                    "events": [
                        {
                            "type": "mousemove",
                            "tsMs": 1773817230000,
                            "xNorm": 0.62,
                            "yNorm": 0.54,
                        },
                        {
                            "type": "mousemove",
                            "tsMs": 1773817230050,
                            "xNorm": 0.64,
                            "yNorm": 0.55,
                        },
                        {
                            "type": "click",
                            "tsMs": 1773817230100,
                            "xNorm": 0.66,
                            "yNorm": 0.56,
                            "button": 0,
                        },
                    ],
                },
            },
        },
    ),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> AiTelemetryIngestResponse:
    sid = _resolve_session_id(
        request.headers.get("X-Auth-Sid") or request.headers.get("X-Session-Id"),
        authorization,
    )
    state_key = _build_state_key(sid, req.match_id)
    now_ms = int(time.time() * 1000)
    user_id = _resolve_user_id(
        explicit_user_id=None,
        x_user_id=x_user_id,
        authorization=authorization,
    )
    _remember_runtime_user_id(session_id=sid, user_id=user_id, now_ms=now_ms)
    snap = _get_or_create_snapshot(state_key, now_ms)
    update: dict[str, Any] = {
        "updated_ts_ms": now_ms,
        "user_id": user_id or snap.user_id,
    }
    summary = _compute_summary_from_raw_events(req.events)
    summary["stage"] = req.stage
    summary["matchId"] = float(req.match_id)
    summary["ingestedAtMs"] = float(now_ms)
    summary["eventCount"] = float(len(req.events))
    if req.stage == "QUEUE_ENTER_PRECLICK":
        update["latest_queue_enter_preclick_summary"] = summary
        update["latest_queue_enter_preclick_at_ms"] = now_ms
    elif req.stage == "VQA_CHALLENGE":
        update["latest_vqa_challenge_summary"] = summary
        update["latest_vqa_challenge_at_ms"] = now_ms
    else:
        update["latest_seat_stage_summary"] = summary
        update["latest_seat_stage_at_ms"] = now_ms
    _state_store.upsert(state_key, snap.model_copy(update=update))
    TELEMETRY_INGEST_REQUESTS.labels(stage=req.stage).inc()
    return AiTelemetryIngestResponse(accepted=True)


@app.post("/ai/evaluate", response_model=AiEvaluateResponse, tags=["decision"])
async def ai_evaluate(
    request: Request,
    req: AiEvaluateRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> AiEvaluateResponse:
    sid = req.context.sid
    match_id = _extract_match_id_from_request_path(req.event.request_path)
    state_key = _build_state_key(sid, match_id)
    now_ms = int(time.time() * 1000)
    trace_id = _resolve_trace_id(request)
    user_id = _resolve_user_id(
        explicit_user_id=req.context.user_id,
        x_user_id=x_user_id,
        authorization=authorization,
    ) or _lookup_runtime_user_id(sid=sid, state_key=state_key)
    _remember_runtime_user_id(session_id=sid, user_id=user_id, now_ms=now_ms)
    snap = _get_or_create_snapshot(state_key, now_ms)
    if user_id and snap.user_id != user_id:
        snap = snap.model_copy(update={"user_id": user_id, "updated_ts_ms": now_ms})
        _state_store.upsert(state_key, snap)
    snap = _hydrate_match_state_from_sid_vqa_mark(
        sid=sid,
        state_key=state_key,
        snap=snap,
        now_ms=now_ms,
    )

    if req.event.event_type == "QUEUE_ENTER" and not _precheck_is_valid(snap, now_ms):
        EVALUATE_REQUESTS.labels(decision="BLOCK").inc()
        background_tasks.add_task(
            _block_user_in_auth_guard,
            user_id=user_id,
            session_id=state_key,
            trace_id=trace_id,
            trigger="ai_evaluate_precheck_block",
        )
        return AiEvaluateResponse(decision={"action": "BLOCK"})


    if req.event.event_type == "SEAT_ENTRY":
        if not snap.vqa_passed:
            EVALUATE_REQUESTS.labels(decision="REQUIRE_S3").inc()
            return AiEvaluateResponse(decision={"action": "REQUIRE_S3"})
        EVALUATE_REQUESTS.labels(decision="NONE").inc()
        return AiEvaluateResponse(decision={"action": "NONE"})

    soft_action = _feature_soft_action(event_type=req.event.event_type, snap=snap)
    if soft_action is not None:
        EVALUATE_REQUESTS.labels(decision=soft_action).inc()
        return AiEvaluateResponse(decision={"action": soft_action})

    legacy_req = _build_legacy_request_from_target(
        state_key=state_key,
        trace_id=trace_id,
        user_id=user_id,
        event_type=req.event.event_type,
        request_path=req.event.request_path,
        request_method=req.event.request_method,
        now_ms=now_ms,
        snap=snap,
    )
 
    legacy_resp, _ = await run_in_threadpool(_execute_legacy_evaluate, legacy_req)
    action = _target_action_from_legacy(legacy_resp.action)
    if req.event.event_type == "QUEUE_ENTER" and action == "REQUIRE_S3":
        action = "THROTTLE"
    EVALUATE_REQUESTS.labels(decision=action).inc()
    return AiEvaluateResponse(decision={"action": action})


@app.post("/ai/challenge/start", response_model=AiChallengeStartResponse, tags=["challenge"])
async def ai_challenge_start(
    request: Request,
    req: AiChallengeStartRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> AiChallengeStartResponse:
    session_id_candidates = _resolve_session_id_candidates(
        request.headers.get("X-Auth-Sid") or request.headers.get("X-Session-Id"),
        authorization,
    )
    if not session_id_candidates:
        raise HTTPException(status_code=401, detail="missing auth context")
    sid = session_id_candidates[0]
    state_key = _build_state_key(sid, req.match_id)
    now_ms = int(time.time() * 1000)
    user_id = _resolve_user_id(
        explicit_user_id=None,
        x_user_id=x_user_id,
        authorization=authorization,
    )
    _remember_runtime_user_id(session_id=sid, user_id=user_id, now_ms=now_ms)
    start_req = ChallengeStartRequest(
        session_id=state_key,
        flow_state="S3",
        challenge_type="catch_ball",
    )
    resp = await _start_challenge_internal(start_req)
    challenge_update = {
        "active_challenge_id": resp.challenge_id,
        "active_challenge_token": resp.challenge_token,
        "active_challenge_expires_at_ms": resp.expires_at_ms,
        "updated_ts_ms": resp.issued_at_ms,
    }
    _upsert_match_state_aliases(
        session_ids=session_id_candidates,
        match_id=req.match_id,
        now_ms=now_ms,
        update=challenge_update,
        user_id=user_id,
    )
    snap = _get_or_create_snapshot(state_key, now_ms)
    CHALLENGE_START_REQUESTS.inc()
    return AiChallengeStartResponse(
        challengeId=resp.challenge_id,
        remainingAttempts=max(resp.attempt_limit - snap.vqa_attempt_count, 0),
        expiresAtMs=resp.expires_at_ms,
    )


@app.post("/ai/challenge/verify", response_model=AiChallengeVerifyResponse, tags=["challenge"])
async def ai_challenge_verify(
    request: Request,
    req: AiChallengeVerifyRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> AiChallengeVerifyResponse:
    session_id_candidates = _resolve_session_id_candidates(
        request.headers.get("X-Auth-Sid") or request.headers.get("X-Session-Id"),
        authorization,
    )
    if not session_id_candidates:
        raise HTTPException(status_code=401, detail="missing auth context")
    sid = session_id_candidates[0]
    state_key = _build_state_key(sid, req.match_id)
    now_ms = int(time.time() * 1000)
    trace_id = _resolve_trace_id(request)
    user_id = _resolve_user_id(
        explicit_user_id=None,
        x_user_id=x_user_id,
        authorization=authorization,
    ) or _lookup_runtime_user_id(sid=sid, state_key=state_key)
    _remember_runtime_user_id(session_id=sid, user_id=user_id, now_ms=now_ms)
    snap = _get_or_create_snapshot(state_key, now_ms)
    if user_id and snap.user_id != user_id:
        snap = snap.model_copy(update={"user_id": user_id, "updated_ts_ms": now_ms})
        _state_store.upsert(state_key, snap)

    if not snap.active_challenge_id or snap.active_challenge_id != req.challenge_id:
        CHALLENGE_VERIFY_REQUESTS.labels(result="invalid").inc()
        return AiChallengeVerifyResponse(
            success=False,
            remainingAttempts=0,
            reason="invalid_challenge",
        )
    if snap.active_challenge_expires_at_ms and snap.active_challenge_expires_at_ms < now_ms:
        CHALLENGE_VERIFY_REQUESTS.labels(result="expired").inc()
        return AiChallengeVerifyResponse(
            success=False,
            remainingAttempts=0,
            reason="expired_challenge",
        )

    feature_summary = snap.latest_vqa_challenge_summary or {}
    in_bounds = 0.0 <= req.catch_x_norm <= 1.0 and 0.0 <= req.catch_y_norm <= 1.0
    timely = req.catch_ts_ms <= (snap.active_challenge_expires_at_ms or now_ms)
    plausible = True
    if feature_summary:
        plausible = bool(feature_summary.get("mousePointCount", 0.0) >= 2.0)
    passed = req.caught and in_bounds and timely and plausible
    vqa_attempt_score, vqa_reason_codes, vqa_terminal_abnormal = _score_vqa_attempt(feature_summary)
    d0_result = "PASS" if passed and not vqa_terminal_abnormal else "FAIL"
    vqa_risk_applied = _apply_vqa_telemetry_to_decision_engine(
        session_id=state_key,
        trace_id=trace_id,
        user_id=user_id or snap.user_id,
        flow_state=snap.flow_state,
        now_ms=now_ms,
        feature_summary=feature_summary,
        vqa_attempt_score=vqa_attempt_score,
        result=d0_result,
    )

    if not feature_summary:
        VQA_TELEMETRY_SCORE_REQUESTS.labels(decision="skip").inc()
    elif passed and vqa_terminal_abnormal:
        VQA_TELEMETRY_SCORE_REQUESTS.labels(decision="terminal").inc()
    elif passed:
        VQA_TELEMETRY_SCORE_REQUESTS.labels(decision="allow").inc()
    else:
        VQA_TELEMETRY_SCORE_REQUESTS.labels(decision="observe").inc()

    if passed and vqa_terminal_abnormal:
        next_attempts = snap.vqa_attempt_count + 1
        next_snap = snap.model_copy(
            update={
                "vqa_required": True,
                "vqa_passed": False,
                "vqa_last_result": "BLOCKED",
                "vqa_attempt_count": next_attempts,
                "challenge_fail_count": snap.challenge_fail_count + 1,
                "updated_ts_ms": now_ms,
                "active_challenge_id": None,
                "active_challenge_token": "",
                "active_challenge_expires_at_ms": None,
                "user_id": user_id or snap.user_id,
                "vqa_behavior_score": vqa_attempt_score,
            }
        )
        _state_store.upsert(state_key, next_snap)
        _sync_mark_to_decision_engine(
            req=RuntimeVqaMarkRequest(
                session_id=state_key,
                vqa_passed=False,
                flow_state=next_snap.flow_state,
            ),
            now_ms=now_ms,
        )
        runtime_overlay = _decision_engine_runtime_overlay(
            session_id=state_key,
            now_ms=now_ms,
            user_id=user_id or snap.user_id,
        ) if vqa_risk_applied else {}
        _audit.log_challenge_event(
            session_id=state_key,
            challenge_id=req.challenge_id,
            event_type="CHALLENGE_VERIFIED",
            payload={
                "matchId": req.match_id,
                "result": "ABNORMAL_TERMINAL",
                "caught": req.caught,
                "catchTsMs": req.catch_ts_ms,
                "catchXNorm": req.catch_x_norm,
                "catchYNorm": req.catch_y_norm,
                "featureSummary": feature_summary,
                "vqaAttemptScore": vqa_attempt_score,
                "reasonCodes": vqa_reason_codes,
            },
        )
        CHALLENGE_VERIFY_REQUESTS.labels(result="abnormal_terminal").inc()
        _state_store.upsert(state_key, next_snap.model_copy(update=runtime_overlay))
        return AiChallengeVerifyResponse(
            success=False,
            remainingAttempts=0,
            reason="abnormal_pattern",
        )

    if passed:
        remaining = max(snap.vqa_retry_limit - snap.vqa_attempt_count, 0)
        next_flow = "S4" if snap.flow_state == "S3" else snap.flow_state
        pass_update = {
            "flow_state": next_flow,
            "vqa_required": False,
            "vqa_passed": True,
            "vqa_last_result": "PASSED",
            "vqa_attempt_count": snap.vqa_attempt_count,
            "vqa_behavior_score": vqa_attempt_score,
            "active_challenge_id": None,
            "active_challenge_token": "",
            "active_challenge_expires_at_ms": None,
            "updated_ts_ms": now_ms,
        }
        _upsert_match_state_aliases(
            session_ids=session_id_candidates,
            match_id=req.match_id,
            now_ms=now_ms,
            update=pass_update,
            user_id=user_id or snap.user_id,
        )
        _upsert_sid_level_vqa_pass_aliases(
            session_ids=session_id_candidates,
            now_ms=now_ms,
            flow_state=next_flow,
            user_id=user_id or snap.user_id,
        )
        _sync_mark_to_decision_engine(
            req=RuntimeVqaMarkRequest(
                session_id=state_key,
                vqa_passed=True,
                flow_state=next_flow,
            ),
            now_ms=now_ms,
        )
        runtime_overlay = _decision_engine_runtime_overlay(
            session_id=state_key,
            now_ms=now_ms,
            user_id=user_id or snap.user_id,
        ) if vqa_risk_applied else {}
        if runtime_overlay:
            pass_update.update(runtime_overlay)
            _upsert_match_state_aliases(
                session_ids=session_id_candidates,
                match_id=req.match_id,
                now_ms=now_ms,
                update=pass_update,
                user_id=user_id or snap.user_id,
            )
        _audit.log_challenge_event(
            session_id=state_key,
            challenge_id=req.challenge_id,
            event_type="CHALLENGE_VERIFIED",
            payload={
                "matchId": req.match_id,
                "result": "PASS",
                "caught": req.caught,
                "catchTsMs": req.catch_ts_ms,
                "catchXNorm": req.catch_x_norm,
                "catchYNorm": req.catch_y_norm,
                "featureSummary": feature_summary,
                "vqaAttemptScore": vqa_attempt_score,
                "reasonCodes": vqa_reason_codes,
            },
        )
        CHALLENGE_VERIFY_REQUESTS.labels(result="pass").inc()
        return AiChallengeVerifyResponse(success=True, remainingAttempts=remaining)

    next_attempts = snap.vqa_attempt_count + 1
    remaining = max(snap.vqa_retry_limit - next_attempts, 0)
    next_snap = snap.model_copy(
        update={
            "vqa_required": True,
            "vqa_passed": False,
            "vqa_last_result": "FAILED" if remaining > 0 else "BLOCKED",
            "vqa_attempt_count": next_attempts,
            "challenge_fail_count": snap.challenge_fail_count + 1,
            "updated_ts_ms": now_ms,
            "active_challenge_id": snap.active_challenge_id if remaining > 0 else None,
            "active_challenge_token": snap.active_challenge_token if remaining > 0 else "",
            "active_challenge_expires_at_ms": (
                snap.active_challenge_expires_at_ms if remaining > 0 else None
            ),
            "user_id": user_id or snap.user_id,
            "vqa_behavior_score": vqa_attempt_score,
        }
    )
    _state_store.upsert(state_key, next_snap)
    _sync_mark_to_decision_engine(
        req=RuntimeVqaMarkRequest(
            session_id=state_key,
            vqa_passed=False,
            flow_state=next_snap.flow_state,
        ),
        now_ms=now_ms,
    )
    runtime_overlay = _decision_engine_runtime_overlay(
        session_id=state_key,
        now_ms=now_ms,
        user_id=user_id or snap.user_id,
    ) if vqa_risk_applied else {}
    _audit.log_challenge_event(
        session_id=state_key,
        challenge_id=req.challenge_id,
        event_type="CHALLENGE_VERIFIED",
        payload={
            "matchId": req.match_id,
            "result": "FAIL",
            "caught": req.caught,
            "catchTsMs": req.catch_ts_ms,
            "catchXNorm": req.catch_x_norm,
            "catchYNorm": req.catch_y_norm,
            "featureSummary": feature_summary,
            "vqaAttemptScore": vqa_attempt_score,
            "reasonCodes": vqa_reason_codes,
        },
    )
    CHALLENGE_VERIFY_REQUESTS.labels(result="fail").inc()
    _state_store.upsert(state_key, next_snap.model_copy(update=runtime_overlay))
    return AiChallengeVerifyResponse(
        success=False,
        remainingAttempts=remaining,
        reason="challenge_fail" if remaining > 0 else "max_attempts",
    )


@app.get("/meta/storage", tags=["state"], include_in_schema=False)
async def storage_meta() -> dict[str, str]:
    return {
        "runtime_state_backend": _state_backend,
        "decision_state_backend": _decision_state_backend,
    }


@app.post("/runtime/vqa/mark", response_model=RuntimeVqaMarkResponse, tags=["state"], include_in_schema=False)
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
    _sync_mark_to_decision_engine(req=req, now_ms=now_ms)
    return RuntimeVqaMarkResponse(
        session_id=req.session_id,
        vqa_passed=next_snap.vqa_passed,
        flow_state=next_snap.flow_state,
        defense_tier=next_snap.defense_tier,
        updated_ts_ms=next_snap.updated_ts_ms,
    )


def _get_or_create_snapshot(session_id: str, now_ms: int) -> RuntimeStateSnapshot:
    snap = _state_store.get(session_id)
    if snap is not None:
        return snap
    return RuntimeStateSnapshot(updated_ts_ms=now_ms)


def _reset_match_state_for_new_booking_attempt(
    *,
    snap: RuntimeStateSnapshot,
    now_ms: int,
    user_id: Optional[str],
) -> RuntimeStateSnapshot:
    return snap.model_copy(
        update={
            "flow_state": "S0",
            "defense_tier": "T0",
            "risk_score": 0.0,
            "challenge_fail_count": 0,
            "seat_taken_streak": 0,
            "hold_fail_streak": 0,
            "heavy_budget_left": 2,
            "replan_budget_left": 3,
            "probation_until_ms": None,
            "updated_ts_ms": now_ms,
            "user_id": user_id or snap.user_id,
            "vqa_required": True,
            "vqa_passed": False,
            "vqa_attempt_count": 0,
            "vqa_last_result": None,
            "active_challenge_id": None,
            "active_challenge_expires_at_ms": None,
            "active_challenge_token": "",
            "latest_queue_enter_preclick_summary": {},
            "latest_queue_enter_preclick_at_ms": 0,
            "latest_seat_stage_summary": {},
            "latest_seat_stage_at_ms": 0,
            "latest_vqa_challenge_summary": {},
            "latest_vqa_challenge_at_ms": 0,
            "vqa_behavior_score": 0.0,
        }
    )


def _reset_sid_level_vqa_state(
    *,
    sid: str,
    now_ms: int,
    user_id: Optional[str],
) -> None:
    snap = _state_store.get(sid) or RuntimeStateSnapshot(updated_ts_ms=now_ms)
    _state_store.upsert(
        sid,
        snap.model_copy(
            update={
                "flow_state": "S0",
                "updated_ts_ms": now_ms,
                "user_id": user_id or snap.user_id,
                "vqa_required": True,
                "vqa_passed": False,
                "vqa_attempt_count": 0,
                "vqa_last_result": None,
                "active_challenge_id": None,
                "active_challenge_expires_at_ms": None,
                "active_challenge_token": "",
                "latest_vqa_challenge_summary": {},
                "latest_vqa_challenge_at_ms": 0,
                "vqa_behavior_score": 0.0,
            }
        ),
    )


def _hydrate_match_state_from_sid_vqa_mark(
    *,
    sid: str,
    state_key: str,
    snap: RuntimeStateSnapshot,
    now_ms: int,
) -> RuntimeStateSnapshot:
    """Project sid-level /runtime/vqa/mark result into sid:matchId state.

    Backend SecurityService currently syncs VQA pass/fail by sid only.
    /ai/evaluate uses sid:matchId state key, so we mirror sid-level PASS state
    into the scoped key before applying post-VQA guard.
    """
    if snap.vqa_passed or sid == state_key:
        return snap

    sid_snap = _state_store.get(sid)
    if sid_snap is None or not sid_snap.vqa_passed:
        return snap

    next_flow = sid_snap.flow_state if sid_snap.flow_state != "S0" else snap.flow_state
    promoted = snap.model_copy(
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
    _state_store.upsert(state_key, promoted)
    _sync_mark_to_decision_engine(
        req=RuntimeVqaMarkRequest(
            session_id=state_key,
            vqa_passed=True,
            flow_state=promoted.flow_state,
        ),
        now_ms=now_ms,
    )
    return promoted


def _build_state_key(sid: str, match_id: int) -> str:
    return f"{sid}:{match_id}"


def _resolve_session_id_candidates(
    x_auth_sid: Optional[str],
    authorization: Optional[str],
) -> list[str]:
    candidates: list[str] = []
    header_sid = _opt_str(x_auth_sid)
    if header_sid:
        candidates.append(header_sid)

    payload = _decode_bearer_payload(authorization)
    if payload:
        token_sid = _opt_str(payload.get("sid"))
        if token_sid and token_sid not in candidates:
            candidates.append(token_sid)

    return candidates


def _upsert_match_state_aliases(
    *,
    session_ids: list[str],
    match_id: int,
    now_ms: int,
    update: dict[str, Any],
    user_id: Optional[str],
) -> None:
    for session_id in session_ids:
        state_key = _build_state_key(session_id, match_id)
        snap = _get_or_create_snapshot(state_key, now_ms)
        next_update = dict(update)
        next_update["user_id"] = user_id or snap.user_id
        _state_store.upsert(state_key, snap.model_copy(update=next_update))


def _upsert_sid_level_vqa_pass_aliases(
    *,
    session_ids: list[str],
    now_ms: int,
    flow_state: str,
    user_id: Optional[str],
) -> None:
    for session_id in session_ids:
        snap = _state_store.get(session_id) or RuntimeStateSnapshot(updated_ts_ms=now_ms)
        _state_store.upsert(
            session_id,
            snap.model_copy(
                update={
                    "flow_state": flow_state,
                    "vqa_required": False,
                    "vqa_passed": True,
                    "vqa_last_result": "PASSED",
                    "active_challenge_id": None,
                    "active_challenge_expires_at_ms": None,
                    "updated_ts_ms": now_ms,
                    "user_id": user_id or snap.user_id,
                }
            ),
        )


def _extract_match_id_from_request_path(request_path: str) -> int:
    match = _MATCH_ID_PATH_RE.search(request_path)
    if match is None:
        raise HTTPException(status_code=400, detail="matchId not found in requestPath")
    return int(match.group("match_id"))


def _resolve_session_id(
    x_auth_sid: Optional[str],
    authorization: Optional[str],
) -> str:
    candidates = _resolve_session_id_candidates(x_auth_sid, authorization)
    if candidates:
        return candidates[0]
    raise HTTPException(status_code=401, detail="missing auth context")


def _decode_bearer_payload(authorization: Optional[str]) -> Optional[dict[str, Any]]:
    token = (authorization or "").removeprefix("Bearer").strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_user_id(
    *,
    explicit_user_id: Optional[str],
    x_user_id: Optional[str],
    authorization: Optional[str],
) -> Optional[str]:
    resolved = _opt_str(explicit_user_id)
    if resolved:
        return resolved
    resolved = _opt_str(x_user_id)
    if resolved:
        return resolved
    payload = _decode_bearer_payload(authorization)
    if payload is None:
        return None
    for key in ("sub", "userId", "user_id"):
        resolved = _opt_str(payload.get(key))
        if resolved:
            return resolved
    return None


def _remember_runtime_user_id(
    *,
    session_id: str,
    user_id: Optional[str],
    now_ms: int,
) -> None:
    resolved_user_id = _opt_str(user_id)
    if not resolved_user_id:
        return
    snap = _state_store.get(session_id) or RuntimeStateSnapshot(updated_ts_ms=now_ms)
    if snap.user_id == resolved_user_id:
        return
    _state_store.upsert(
        session_id,
        snap.model_copy(update={"user_id": resolved_user_id, "updated_ts_ms": now_ms}),
    )


def _lookup_runtime_user_id(*, sid: str, state_key: str) -> Optional[str]:
    for key in (state_key, sid):
        snap = _state_store.get(key)
        if snap is None:
            continue
        resolved = _opt_str(snap.user_id)
        if resolved:
            return resolved
    return None


def _resolve_trace_id(request: Request) -> str:
    header_trace_id = _opt_str(request.headers.get("X-Trace-Id"))
    if header_trace_id:
        return header_trace_id
    correlation_id = _opt_str(request.headers.get("X-Correlation-Id"))
    if correlation_id:
        return correlation_id
    return f"trace-{uuid.uuid4().hex[:12]}"


def _block_user_in_auth_guard(
    *,
    user_id: Optional[str],
    session_id: str,
    trace_id: str,
    trigger: str,
) -> None:
    _auth_guard_blocker.block_user(
        user_id=user_id or "",
        session_id=session_id,
        trace_id=trace_id,
        trigger=trigger,
    )


async def _verify_turnstile_token(turnstile_token: str) -> bool:
    token = turnstile_token.strip()
    if not token:
        return False

    if _TURNSTILE_SECRET_KEY:
        try:
            timeout = max(_TURNSTILE_TIMEOUT_MS / 1000.0, 0.1)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    _TURNSTILE_SITEVERIFY_URL,
                    data={"secret": _TURNSTILE_SECRET_KEY, "response": token},
                )
                resp.raise_for_status()
                payload = resp.json()
                return bool(payload.get("success"))
        except Exception:
            return False

    # Local/dev fallback semantics when external secret is not configured.
    lowered = token.lower()
    if lowered.startswith(("invalid", "error", "timeout", "fail")):
        return False
    return True


def _extract_pointer_points(events: list[RawTelemetryEvent]) -> list[tuple[int, float, float]]:
    points: list[tuple[int, float, float]] = []
    virtual_canvas_px = 1000.0
    for event in events:
        if event.type not in {"mousemove", "mousedown", "mouseup", "click"}:
            continue
        if event.x_norm is None or event.y_norm is None:
            continue
        points.append(
            (
                int(event.ts_ms),
                float(event.x_norm) * virtual_canvas_px,
                float(event.y_norm) * virtual_canvas_px,
            )
        )
    points.sort(key=lambda item: item[0])
    return points


def _perpendicular_distance(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    px: float,
    py: float,
) -> float:
    dx = bx - ax
    dy = by - ay
    denom = math.hypot(dx, dy)
    if denom <= 1e-6:
        return 0.0
    return abs(dx * (ay - py) - (ax - px) * dy) / denom


def _stddev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(variance, 0.0))


def _compute_summary_from_raw_events(events: list[RawTelemetryEvent]) -> dict[str, float]:
    points = _extract_pointer_points(events)
    summary: dict[str, float] = {
        "mousePointCount": float(len(points)),
        "totalDist": 0.0,
        "linearDist": 0.0,
        "linearityRatio": 0.0,
        "avgVelocity": 0.0,
        "tremorStdDev": 0.0,
        "dwellTime": 0.0,
        "pathRatio": 0.0,
    }
    if len(points) < 2:
        return summary

    total_dist = 0.0
    dwell_time_ms = 0.0
    dwell_radius_px = 3.0
    dwell_speed_px_per_sec = 30.0
    for (ts0, x0, y0), (ts1, x1, y1) in zip(points, points[1:]):
        segment_dist = math.hypot(x1 - x0, y1 - y0)
        total_dist += segment_dist
        dt_ms = max(float(ts1 - ts0), 0.0)
        speed_px_per_sec = (segment_dist / (dt_ms / 1000.0)) if dt_ms > 1e-6 else 0.0
        if segment_dist <= dwell_radius_px or speed_px_per_sec <= dwell_speed_px_per_sec:
            dwell_time_ms += dt_ms

    _, ax, ay = points[0]
    first_ts, _, _ = points[0]
    last_ts, bx, by = points[-1]
    linear_dist = math.hypot(bx - ax, by - ay)
    duration_s = max((last_ts - first_ts) / 1000.0, 1e-6)
    linearity_ratio = linear_dist / total_dist if total_dist > 1e-6 else 0.0
    avg_velocity = total_dist / duration_s if duration_s > 1e-6 else 0.0
    path_ratio = total_dist / max(linear_dist, 1e-6) if total_dist > 1e-6 else 0.0

    tremor_samples: list[float] = []
    if linear_dist > 20.0:
        for _, px, py in points[1:-1]:
            tremor_samples.append(_perpendicular_distance(ax, ay, bx, by, px, py))

    summary.update(
        {
            "totalDist": total_dist,
            "linearDist": linear_dist,
            "linearityRatio": linearity_ratio,
            "avgVelocity": avg_velocity,
            "tremorStdDev": _stddev(tremor_samples),
            "dwellTime": dwell_time_ms,
            "pathRatio": path_ratio,
        }
    )
    summary["isLinearPath"] = _is_linear_path(linearity_ratio, path_ratio)
    summary["botRisk"] = _compute_bot_risk(summary)
    return summary


def _summary_to_legacy_features(summary: dict[str, float]) -> Optional[EvaluateTelemetryFeatures]:
    if not summary:
        return None
    point_count = _opt_int(summary.get("mousePointCount"))
    if point_count is not None and point_count < 2:
        return None
    payload: dict[str, float] = {}
    for key in (
        "tremorStdDev",
        "linearityRatio",
        "avgVelocity",
        "dwellTime",
        "pathRatio",
        "totalDist",
        "linearDist",
    ):
        value = summary.get(key)
        if value is not None:
            payload[key] = float(value)
    if not payload:
        return None
    return EvaluateTelemetryFeatures.model_validate(payload)


def _target_event_to_flow_state(event_type: str) -> str:
    mapping = {
        "QUEUE_ENTER": "S2",
        "SEAT_ENTRY": "S3",
        "RECOMMENDATION_BLOCKS": "S4",
        "SECTION_BLOCKS": "S4",
        "ASSIGN_HOLD": "S5",
        "SEAT_HOLDS": "S5",
    }
    return mapping.get(event_type, "S0")


def _normalize(value: float, lower: float, upper: float) -> float:
    if upper <= lower:
        return 0.0
    return max(0.0, min(1.0, (value - lower) / (upper - lower)))


def _is_unnatural_velocity(avg_velocity: float) -> float:
    if avg_velocity <= 50.0:
        return 0.0
    if avg_velocity >= 1500.0:
        return 1.0
    return (avg_velocity - 50.0) / (1500.0 - 50.0)


def _is_linear_path(linearity_ratio: float, path_ratio: float) -> float:
    return 1.0 if linearity_ratio >= 0.92 and path_ratio <= 1.10 else 0.0


def _compute_bot_risk(summary: dict[str, float]) -> float:
    tremor = max(0.0, min(6.0, float(summary.get("tremorStdDev", 0.0))))
    linearity = max(0.0, min(1.0, float(summary.get("linearityRatio", 0.0))))
    velocity = max(0.0, min(4000.0, float(summary.get("avgVelocity", 0.0))))
    dwell = max(0.0, min(2000.0, float(summary.get("dwellTime", 0.0))))
    path_ratio = max(1.0, min(3.0, float(summary.get("pathRatio", 1.0))))
    linear_path = _is_linear_path(linearity, path_ratio)
    risk = (
        0.35 * (1.0 - _normalize(tremor, 0.0, 6.0))
        + 0.25 * linearity
        + 0.15 * _is_unnatural_velocity(velocity)
        + 0.15 * (1.0 - _normalize(dwell, 0.0, 2000.0))
        + 0.10 * linear_path
    )
    return max(0.0, min(1.0, risk))


def _score_vqa_attempt(summary: dict[str, float]) -> tuple[float, list[str], bool]:
    if not summary:
        return 0.0, [], False

    point_count = _opt_int(summary.get("mousePointCount")) or 0
    if point_count < 2:
        return 0.0, [], False

    base_risk = _to_float(summary.get("botRisk"))
    if base_risk is None:
        base_risk = _compute_bot_risk(summary)

    linearity = max(0.0, min(1.0, float(summary.get("linearityRatio", 0.0))))
    path_ratio = max(1.0, min(3.0, float(summary.get("pathRatio", 1.0))))
    tremor = max(0.0, min(6.0, float(summary.get("tremorStdDev", 0.0))))
    velocity = max(0.0, min(4000.0, float(summary.get("avgVelocity", 0.0))))
    dwell = max(0.0, min(2000.0, float(summary.get("dwellTime", 0.0))))

    boosted_risk = (
        0.40 * linearity
        + 0.25 * (1.0 - _normalize(path_ratio, 1.0, 1.20))
        + 0.15 * (1.0 - _normalize(tremor, 0.0, 1.5))
        + 0.10 * _normalize(velocity, 600.0, 2400.0)
        + 0.10 * (1.0 - _normalize(dwell, 50.0, 500.0))
    )
    attempt_score = max(0.0, min(1.0, max(base_risk, boosted_risk)))

    reason_codes: list[str] = []
    if linearity >= _VQA_EXTREME_LINEARITY_THRESHOLD:
        reason_codes.append("linearity_extreme")
    if path_ratio <= _VQA_EXTREME_PATH_RATIO_THRESHOLD:
        reason_codes.append("path_ratio_extreme")
    if tremor <= _VQA_LOW_TREMOR_THRESHOLD:
        reason_codes.append("tremor_low")
    if velocity >= _VQA_HIGH_VELOCITY_THRESHOLD:
        reason_codes.append("velocity_high")
    if dwell <= _VQA_LOW_DWELL_THRESHOLD:
        reason_codes.append("dwell_low")

    terminal = point_count >= _VQA_MIN_POINTS_FOR_ABNORMAL_TERMINAL and (
        attempt_score >= _VQA_TERMINAL_RISK_THRESHOLD
        or (
            attempt_score >= _VQA_REVIEW_RISK_FLOOR
            and len(reason_codes) >= _VQA_MIN_STRONG_SIGNALS_FOR_TERMINAL
            and "linearity_extreme" in reason_codes
        )
    )
    return attempt_score, reason_codes, terminal


def _apply_vqa_telemetry_to_decision_engine(
    *,
    session_id: str,
    trace_id: str,
    user_id: Optional[str],
    flow_state: str,
    now_ms: int,
    feature_summary: dict[str, float],
    vqa_attempt_score: float,
    result: str,
) -> bool:
    point_count = _opt_int(feature_summary.get("mousePointCount")) or 0
    if point_count < 2:
        return False

    policy = _decision_engine.policy_loader.load(session_id=session_id)
    external_score = max(0.0, min(1.0, 1.0 - vqa_attempt_score))
    event = D0RuntimeEvent(
        event_type="S3_RESULT",
        ts_ms=now_ms,
        flow_state=_to_d0_flow_state(flow_state),
        session_id=session_id,
        trace_id=trace_id,
        source="AI_RUNTIME",
        payload={"result": result},
    )

    with _decision_engine.session_state.session_lock(session_id):
        state = _decision_engine.session_state.get_or_create(
            session_id,
            policy_version=policy.policy_version,
        )
        guard_output = _decision_engine.guard.score(
            trace_id=trace_id,
            event=event,
            state=state,
            policy=policy,
            features=feature_summary,
            external_score=external_score,
        )
        _decision_engine.guard.persist(
            state_manager=_decision_engine.session_state,
            session_id=session_id,
            ts_ms=now_ms,
            output=guard_output,
        )
        state.risk_score = guard_output.r_new
        state.defense_tier = guard_output.tier
        _decision_engine.analyzer.analyze(
            session_id=session_id,
            trace_id=trace_id,
            event=event,
            state=state,
            policy=policy,
        )
        if user_id:
            _decision_engine.session_state.sync_policy_version(
                session_id,
                policy.policy_version,
                refresh_ttl=result == "PASS",
            )
    return True


def _decision_engine_runtime_overlay(
    *,
    session_id: str,
    now_ms: int,
    user_id: Optional[str],
) -> dict[str, Any]:
    d0_state = _decision_engine.session_state.get(session_id)
    if d0_state is None:
        return {}

    return {
        "flow_state": d0_state.flow_state.value,
        "defense_tier": d0_state.defense_tier.value,
        "risk_score": float(d0_state.risk_score),
        "challenge_fail_count": int(d0_state.challenge_fail_count),
        "seat_taken_streak": int(d0_state.seat_taken_streak),
        "hold_fail_streak": int(d0_state.hold_fail_streak),
        "probation_until_ms": d0_state.probation_until_ms,
        "policy_version": d0_state.policy_version or "v2.0.0-mvp",
        "updated_ts_ms": now_ms,
        "user_id": user_id,
    }


def _feature_soft_action(
    *,
    event_type: str,
    snap: RuntimeStateSnapshot,
) -> Optional[str]:
    if event_type == "QUEUE_ENTER":
        summary = snap.latest_queue_enter_preclick_summary
        require_s3_threshold = 0.78
        throttle_threshold = 0.62
    elif event_type in {"RECOMMENDATION_BLOCKS", "SECTION_BLOCKS", "ASSIGN_HOLD", "SEAT_HOLDS"}:
        summary = snap.latest_seat_stage_summary
        require_s3_threshold = 0.74
        throttle_threshold = 0.58
    else:
        return None

    if not summary:
        return None

    point_count = _opt_int(summary.get("mousePointCount"))
    if point_count is None or point_count < 2:
        return None

    risk = _to_float(summary.get("botRisk"))
    if risk is None:
        return None

    if risk >= require_s3_threshold:
        return "REQUIRE_S3"
    if risk >= throttle_threshold:
        return "THROTTLE"
    return None


def _precheck_is_valid(snap: RuntimeStateSnapshot, now_ms: int) -> bool:
    if not snap.turnstile_verified:
        return False
    return now_ms - snap.turnstile_verified_at_ms <= _PRECHECK_TTL_MS


def _target_action_from_legacy(action: str) -> str:
    if action == "CHALLENGE":
        return "REQUIRE_S3"
    return action


def _build_legacy_request_from_target(
    *,
    state_key: str,
    trace_id: str,
    user_id: Optional[str],
    event_type: str,
    request_path: str,
    request_method: str,
    now_ms: int,
    snap: RuntimeStateSnapshot,
) -> EvaluateRequest:
    telemetry_features: dict[str, float] | None = None
    if event_type == "QUEUE_ENTER":
        telemetry_features = snap.latest_queue_enter_preclick_summary
    elif event_type in {"RECOMMENDATION_BLOCKS", "SECTION_BLOCKS", "ASSIGN_HOLD", "SEAT_HOLDS"}:
        telemetry_features = snap.latest_seat_stage_summary

    return EvaluateRequest(
        session_id=state_key,
        trace_id=trace_id,
        path=request_path,
        method=request_method.upper(),
        user_id=user_id,
        timestamp=now_ms,
        headers={},
        flow_state=_target_event_to_flow_state(event_type),
        telemetry_features=_summary_to_legacy_features(telemetry_features or {}),
    )


def _execute_legacy_evaluate(req: EvaluateRequest) -> tuple[EvaluateResponse, RuntimeStateSnapshot]:
    started_at = time.perf_counter()
    now_ms = int(time.time() * 1000)
    existing_snapshot = _state_store.get(req.session_id)

    decision_check_request = _legacy_request_to_d0_check(req)
    decision_eval_request = _decision_engine.check_request_to_evaluate(decision_check_request)
    telemetry_features = _legacy_features_to_d0(req)
    if telemetry_features:
        decision_eval_request.context.features = telemetry_features
    try:
        out = _decision_engine.evaluate(decision_eval_request)
    except Exception as exc:  # noqa: BLE001 - fail-open policy
        out = _decision_engine.fail_open_on_unavailable(request=decision_eval_request, error=exc)

    resp = _legacy_response_from_d0(req=req, started_at=started_at, out=out)
    snap = _legacy_snapshot_from_d0_state(
        session_id=req.session_id,
        d0_state=_decision_engine.session_state.get(req.session_id),
        policy_version=out.policy.policy_version,
        challenge_max_attempts=out.policy.challenge_max_attempts,
        now_ms=now_ms,
        user_id=req.user_id or (existing_snapshot.user_id if existing_snapshot is not None else None),
    )
    _state_store.upsert(req.session_id, snap)
    _audit.log(req, resp, snap)
    return resp, snap


def _legacy_request_to_d0_check(req: EvaluateRequest) -> D0CheckRequest:
    trace_id = req.trace_id or req.request_id or f"trace-{uuid.uuid4().hex[:12]}"
    return D0CheckRequest(
        session_id=req.session_id,
        trace_id=trace_id,
        user_id=req.user_id,
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
    user_id: Optional[str],
) -> RuntimeStateSnapshot:
    if d0_state is None:
        return RuntimeStateSnapshot(
            updated_ts_ms=now_ms,
            policy_version=policy_version,
            user_id=user_id,
        )

    grace = _decision_engine.session_state.get_s3_grace(session_id) or {}
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
        user_id=user_id,
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


def _sync_mark_to_decision_engine(*, req: RuntimeVqaMarkRequest, now_ms: int) -> None:
    session_id = req.session_id
    existing = _decision_engine.session_state.get_or_create(session_id)
    flow_state = _to_d0_flow_state(req.flow_state) if req.flow_state else existing.flow_state
    if req.vqa_passed:
        _decision_engine.session_state.update_by_role(
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
        _decision_engine.session_state.update_by_role(
            "analyzer",
            session_id,
            {
                "challengeFailCount": 0,
            },
            is_allow=True,
        )
        return

    _decision_engine.session_state.update_by_role(
        "orchestrator",
        session_id,
        {
            "flowState": flow_state.value,
            "s3Passed": 0,
            "lastDecisionAction": "REQUIRE_S3",
        },
        is_allow=False,
    )

@app.get("/metrics", tags=["infrastructure"], include_in_schema=False)
async def metrics():
    """Expose Prometheus metrics."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from fastapi import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
