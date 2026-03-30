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

from ..d0_mvp.api.runtime import DefenseRuntime as D0DefenseRuntime
from ..d0_mvp.core.enums import DefenseAction as D0DefenseAction
from ..d0_mvp.core.enums import FlowState as D0FlowState
from ..d0_mvp.core.models import CheckRequest as D0CheckRequest
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

# Custom Metrics
EVALUATE_REQUESTS = Counter(
    "ai_defense_evaluate_total",
    "Total evaluate requests by path, method, and decision",
    ["path", "method", "decision"],
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

_S3_UPLOADER = S3Uploader(bucket=_S3_BUCKET, prefix=_S3_PREFIX, region=_S3_REGION) if _S3_BUCKET else None


def _cors_allow_origins_from_env() -> list[str]:
    raw = os.getenv("TM_CORS_ALLOW_ORIGINS", "https://dev.goormgb.space")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


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
async def lifespan(app: FastAPI):
    """FastAPI lifespan: Startup/Shutdown hooks."""
    archive_task = asyncio.create_task(_s3_archive_loop())
    yield
    archive_task.cancel()
    try:
        await archive_task
    except asyncio.CancelledError:
        pass


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
_audit = DefenseDecisionAuditLogger.from_env()
_challenge_runtime = ChallengeRuntime(ChallengeConfig.from_env())
_d0_runtime = D0DefenseRuntime()

# Backend runtime sanction endpoint
BE_RUNTIME_SANCTIONS_URL = os.getenv("TM_BACKEND_RUNTIME_SANCTIONS_URL") or os.getenv(
    "TM_BACKEND_SANCTION_URL"
)


async def _send_be_runtime_sanction(sid: str):
    """Asynchronously notify backend to apply runtime sanction by sid."""
    if not BE_RUNTIME_SANCTIONS_URL or not sid:
        return

    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            await client.post(BE_RUNTIME_SANCTIONS_URL, json={"sid": sid})
        except Exception:
            # Shield AI performance from BE failures
            pass


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
) -> AiPrecheckResponse:
    sid = _resolve_session_id(
        request.headers.get("X-Auth-Sid") or request.headers.get("X-Session-Id"),
        authorization,
    )
    state_key = _build_state_key(sid, req.match_id)
    now_ms = int(time.time() * 1000)
    passed = await _verify_turnstile_token(req.cf_token)
    snap = _get_or_create_snapshot(state_key, now_ms)
    next_snap = snap.model_copy(
        update={
            "turnstile_verified": passed,
            "turnstile_verified_at_ms": now_ms if passed else 0,
            "updated_ts_ms": now_ms,
        }
    )
    _state_store.upsert(state_key, next_snap)
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
) -> AiTelemetryIngestResponse:
    sid = _resolve_session_id(
        request.headers.get("X-Auth-Sid") or request.headers.get("X-Session-Id"),
        authorization,
    )
    state_key = _build_state_key(sid, req.match_id)
    now_ms = int(time.time() * 1000)
    snap = _get_or_create_snapshot(state_key, now_ms)
    update: dict[str, Any] = {"updated_ts_ms": now_ms}
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
    return AiTelemetryIngestResponse(accepted=True)


@app.post("/ai/evaluate", response_model=AiEvaluateResponse, tags=["decision"])
async def ai_evaluate(
    req: AiEvaluateRequest,
    background_tasks: BackgroundTasks,
) -> AiEvaluateResponse:
    sid = req.context.sid
    match_id = _extract_match_id_from_request_path(req.event.request_path)
    state_key = _build_state_key(sid, match_id)
    now_ms = int(time.time() * 1000)
    snap = _get_or_create_snapshot(state_key, now_ms)
    snap = _hydrate_match_state_from_sid_vqa_mark(
        sid=sid,
        state_key=state_key,
        snap=snap,
        now_ms=now_ms,
    )

    if req.event.event_type == "QUEUE_ENTER" and not _precheck_is_valid(snap, now_ms):
        return AiEvaluateResponse(decision={"action": "BLOCK"})

    if req.event.event_type == "SEAT_ENTRY" and not snap.vqa_passed:
        return AiEvaluateResponse(decision={"action": "REQUIRE_S3"})

    soft_action = _feature_soft_action(event_type=req.event.event_type, snap=snap)
    if soft_action is not None:
        return AiEvaluateResponse(decision={"action": soft_action})

    legacy_req = _build_legacy_request_from_target(
        state_key=state_key,
        event_type=req.event.event_type,
        request_path=req.event.request_path,
        request_method=req.event.request_method,
        now_ms=now_ms,
        snap=snap,
    )
    legacy_resp, _ = _execute_legacy_evaluate(legacy_req)
    action = _target_action_from_legacy(legacy_resp.action)
    if action == "BLOCK":
        background_tasks.add_task(_send_be_runtime_sanction, sid=sid)
    return AiEvaluateResponse(decision={"action": action})


@app.post("/ai/challenge/start", response_model=AiChallengeStartResponse, tags=["challenge"])
async def ai_challenge_start(
    request: Request,
    req: AiChallengeStartRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AiChallengeStartResponse:
    sid = _resolve_session_id(
        request.headers.get("X-Auth-Sid") or request.headers.get("X-Session-Id"),
        authorization,
    )
    state_key = _build_state_key(sid, req.match_id)
    start_req = ChallengeStartRequest(
        session_id=state_key,
        flow_state="S3",
        challenge_type="catch_ball",
    )
    resp = await _start_challenge_internal(start_req)
    snap = _get_or_create_snapshot(state_key, int(time.time() * 1000))
    _state_store.upsert(
        state_key,
        snap.model_copy(
            update={
                "active_challenge_id": resp.challenge_id,
                "active_challenge_token": resp.challenge_token,
                "active_challenge_expires_at_ms": resp.expires_at_ms,
                "updated_ts_ms": resp.issued_at_ms,
            }
        ),
    )
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
) -> AiChallengeVerifyResponse:
    sid = _resolve_session_id(
        request.headers.get("X-Auth-Sid") or request.headers.get("X-Session-Id"),
        authorization,
    )
    state_key = _build_state_key(sid, req.match_id)
    now_ms = int(time.time() * 1000)
    snap = _get_or_create_snapshot(state_key, now_ms)

    if not snap.active_challenge_id or snap.active_challenge_id != req.challenge_id:
        return AiChallengeVerifyResponse(success=False, remainingAttempts=0)
    if snap.active_challenge_expires_at_ms and snap.active_challenge_expires_at_ms < now_ms:
        return AiChallengeVerifyResponse(success=False, remainingAttempts=0)

    feature_summary = snap.latest_vqa_challenge_summary or {}
    in_bounds = 0.0 <= req.catch_x_norm <= 1.0 and 0.0 <= req.catch_y_norm <= 1.0
    timely = req.catch_ts_ms <= (snap.active_challenge_expires_at_ms or now_ms)
    plausible = True
    if feature_summary:
        plausible = bool(feature_summary.get("mousePointCount", 0.0) >= 2.0)
    passed = req.caught and in_bounds and timely and plausible

    next_attempts = snap.vqa_attempt_count + 1
    remaining = max(snap.vqa_retry_limit - next_attempts, 0)
    if passed:
        next_flow = "S4" if snap.flow_state == "S3" else snap.flow_state
        next_snap = snap.model_copy(
            update={
                "flow_state": next_flow,
                "vqa_required": False,
                "vqa_passed": True,
                "vqa_last_result": "PASSED",
                "vqa_attempt_count": next_attempts,
                "vqa_behavior_score": float(feature_summary.get("linearityRatio", 0.0)),
                "active_challenge_id": None,
                "active_challenge_token": "",
                "active_challenge_expires_at_ms": None,
                "updated_ts_ms": now_ms,
            }
        )
        _state_store.upsert(state_key, next_snap)
        _sync_mark_to_d0_runtime(
            req=RuntimeVqaMarkRequest(
                session_id=state_key,
                vqa_passed=True,
                flow_state=next_flow,
            ),
            now_ms=now_ms,
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
            },
        )
        return AiChallengeVerifyResponse(success=True, remainingAttempts=remaining)

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
        }
    )
    _state_store.upsert(state_key, next_snap)
    _sync_mark_to_d0_runtime(
        req=RuntimeVqaMarkRequest(
            session_id=state_key,
            vqa_passed=False,
            flow_state=next_snap.flow_state,
        ),
        now_ms=now_ms,
    )
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
        },
    )
    return AiChallengeVerifyResponse(success=False, remainingAttempts=remaining)


@app.get("/meta/storage", tags=["state"], include_in_schema=False)
async def storage_meta() -> dict[str, str]:
    return {"runtime_state_backend": _state_backend}


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
    _sync_mark_to_d0_runtime(req=req, now_ms=now_ms)
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
    _sync_mark_to_d0_runtime(
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


def _extract_match_id_from_request_path(request_path: str) -> int:
    match = _MATCH_ID_PATH_RE.search(request_path)
    if match is None:
        raise HTTPException(status_code=400, detail="matchId not found in requestPath")
    return int(match.group("match_id"))


def _resolve_session_id(
    x_auth_sid: Optional[str],
    authorization: Optional[str],
) -> str:
    sid = (x_auth_sid or "").strip()
    if sid:
        return sid
    token = (authorization or "").removeprefix("Bearer").strip()
    if token:
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            token_sid = str(payload.get("sid", "")).strip()
            if token_sid:
                return token_sid
        except Exception:
            pass
    raise HTTPException(status_code=401, detail="missing auth context")


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
        path=request_path,
        method=request_method.upper(),
        timestamp=now_ms,
        headers={},
        flow_state=_target_event_to_flow_state(event_type),
        telemetry_features=_summary_to_legacy_features(telemetry_features or {}),
    )


def _execute_legacy_evaluate(req: EvaluateRequest) -> tuple[EvaluateResponse, RuntimeStateSnapshot]:
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
    snap = _legacy_snapshot_from_d0_state(
        session_id=req.session_id,
        d0_state=_d0_runtime.session_state.get(req.session_id),
        policy_version=out.policy.policy_version,
        challenge_max_attempts=out.policy.challenge_max_attempts,
        now_ms=now_ms,
    )
    _state_store.upsert(req.session_id, snap)
    _audit.log(req, resp, snap)
    return resp, snap


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

@app.get("/metrics", tags=["infrastructure"], include_in_schema=False)
async def metrics():
    """Expose Prometheus metrics."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from fastapi import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
