import base64
import json
import os
import sys
import types
import uuid

from fastapi.testclient import TestClient

os.environ.setdefault("CI", "true")

if "pythonjsonlogger" not in sys.modules:
    class _JsonFormatter:
        def __init__(self, *args, **kwargs):
            pass

        def add_fields(self, log_record, record, message_dict):
            return None

    sys.modules["pythonjsonlogger"] = types.SimpleNamespace(
        jsonlogger=types.SimpleNamespace(JsonFormatter=_JsonFormatter)
    )

if "jwt" not in sys.modules:
    def _jwt_encode(payload, key, algorithm=None):
        sid = payload.get("sid", "")
        return f"stub-jwt:{sid}"

    def _jwt_decode(token, options=None, **kwargs):
        if isinstance(token, str) and token.startswith("stub-jwt:"):
            return {"sid": token.split(":", 1)[1]}
        return {}

    sys.modules["jwt"] = types.SimpleNamespace(
        decode=_jwt_decode,
        encode=_jwt_encode,
    )

if "opentelemetry" not in sys.modules:
    class _NoOp:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return None

        def add_span_processor(self, *args, **kwargs):
            return None

    class _Resource:
        @staticmethod
        def create(payload):
            return payload

    class _FastAPIInstrumentor:
        @staticmethod
        def instrument_app(app):
            return app

    root = types.ModuleType("opentelemetry")
    root.metrics = types.SimpleNamespace(set_meter_provider=lambda provider: None)
    root.trace = types.SimpleNamespace(set_tracer_provider=lambda provider: None)
    sys.modules["opentelemetry"] = root
    sys.modules["opentelemetry.metrics"] = root.metrics
    sys.modules["opentelemetry.trace"] = root.trace
    sys.modules["opentelemetry.exporter"] = types.ModuleType("opentelemetry.exporter")
    sys.modules["opentelemetry.exporter.otlp"] = types.ModuleType("opentelemetry.exporter.otlp")
    sys.modules["opentelemetry.exporter.otlp.proto"] = types.ModuleType("opentelemetry.exporter.otlp.proto")
    sys.modules["opentelemetry.exporter.otlp.proto.grpc"] = types.ModuleType("opentelemetry.exporter.otlp.proto.grpc")
    sys.modules["opentelemetry.exporter.otlp.proto.grpc.metric_exporter"] = types.SimpleNamespace(
        OTLPMetricExporter=_NoOp
    )
    sys.modules["opentelemetry.exporter.otlp.proto.grpc.trace_exporter"] = types.SimpleNamespace(
        OTLPSpanExporter=_NoOp
    )
    sys.modules["opentelemetry.instrumentation"] = types.ModuleType("opentelemetry.instrumentation")
    sys.modules["opentelemetry.instrumentation.fastapi"] = types.SimpleNamespace(
        FastAPIInstrumentor=_FastAPIInstrumentor
    )
    sys.modules["opentelemetry.sdk"] = types.ModuleType("opentelemetry.sdk")
    sys.modules["opentelemetry.sdk.metrics"] = types.SimpleNamespace(MeterProvider=_NoOp)
    sys.modules["opentelemetry.sdk.metrics.export"] = types.SimpleNamespace(
        PeriodicExportingMetricReader=_NoOp
    )
    sys.modules["opentelemetry.sdk.resources"] = types.SimpleNamespace(Resource=_Resource)
    sys.modules["opentelemetry.sdk.trace"] = types.SimpleNamespace(TracerProvider=_NoOp)
    sys.modules["opentelemetry.sdk.trace.export"] = types.SimpleNamespace(
        BatchSpanProcessor=_NoOp
    )
    sys.modules["opentelemetry.semconv"] = types.ModuleType("opentelemetry.semconv")
    sys.modules["opentelemetry.semconv.resource"] = types.SimpleNamespace(
        ResourceAttributes=types.SimpleNamespace(
            SERVICE_NAME="service.name",
            SERVICE_NAMESPACE="service.namespace",
            SERVICE_VERSION="service.version",
        )
    )

import jwt

import traffic_master_ai.defense.api.main as api_main
from traffic_master_ai.defense.api.main import _decision_engine, _state_store
from traffic_master_ai.defense.api.models import RuntimeStateSnapshot

client = TestClient(api_main.app)
MATCH_ID = 687


def _headers(session_id: str) -> dict[str, str]:
    return {"X-Session-Id": session_id}


def _encode_test_jwt(payload: dict[str, str]) -> str:
    def _b64url(data: dict[str, str]) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url(payload)}."


def _decode_test_jwt(token: str, options=None) -> dict[str, str]:
    del options
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))


def _headers_with_authorization(session_id: str, auth_sid: str) -> dict[str, str]:
    encode = getattr(jwt, "encode", None)
    if callable(encode):
        token = encode({"sid": auth_sid}, "test-secret-that-is-long-enough-32b", algorithm="HS256")
    else:
        token = _encode_test_jwt({"sid": auth_sid})
        api_main.jwt = type("JWTStub", (), {"decode": staticmethod(_decode_test_jwt)})()
    return {
        "X-Session-Id": session_id,
        "Authorization": f"Bearer {token}",
    }


def _headers_with_user(session_id: str, user_id: str) -> dict[str, str]:
    return {"X-Session-Id": session_id, "X-User-Id": user_id}


def _session_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _state_key(session_id: str) -> str:
    return f"{session_id}:{MATCH_ID}"


def _vqa_events() -> list[dict[str, float | int | str]]:
    return [
        {"type": "mousemove", "tsMs": 0, "xNorm": 0.10, "yNorm": 0.50},
        {"type": "mousemove", "tsMs": 80, "xNorm": 0.18, "yNorm": 0.53},
        {"type": "mousemove", "tsMs": 170, "xNorm": 0.27, "yNorm": 0.47},
        {"type": "mousemove", "tsMs": 280, "xNorm": 0.35, "yNorm": 0.55},
        {"type": "mousemove", "tsMs": 410, "xNorm": 0.44, "yNorm": 0.48},
        {"type": "mousemove", "tsMs": 560, "xNorm": 0.52, "yNorm": 0.52},
    ]


def test_ai_challenge_start_returns_target_contract() -> None:
    session_id = _session_id("sess-ai-start")
    response = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    body = response.json()

    assert set(body.keys()) == {"challengeId", "remainingAttempts", "expiresAtMs"}
    assert isinstance(body["challengeId"], str)
    assert body["challengeId"]
    assert isinstance(body["remainingAttempts"], int)
    assert body["remainingAttempts"] >= 0
    assert isinstance(body["expiresAtMs"], int)
    assert body["expiresAtMs"] > 0


def test_ai_challenge_verify_retries_then_blocks() -> None:
    session_id = _session_id("sess-ai-verify-block")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    verify_1 = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": False,
            "catchTsMs": 1,
            "catchXNorm": 0.5,
            "catchYNorm": 0.5,
        },
        headers=_headers(session_id),
    )
    assert verify_1.status_code == 200
    body_1 = verify_1.json()
    assert body_1["success"] is False
    assert body_1["remainingAttempts"] == 2
    assert body_1["reason"] == "missing_vqa_telemetry"

    verify_2 = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": False,
            "catchTsMs": 2,
            "catchXNorm": 0.5,
            "catchYNorm": 0.5,
        },
        headers=_headers(session_id),
    )
    assert verify_2.status_code == 200
    body_2 = verify_2.json()
    assert body_2["success"] is False
    assert body_2["remainingAttempts"] == 1
    assert body_2["reason"] == "missing_vqa_telemetry"

    verify_3 = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": False,
            "catchTsMs": 3,
            "catchXNorm": 0.5,
            "catchYNorm": 0.5,
        },
        headers=_headers(session_id),
    )
    assert verify_3.status_code == 200
    body_3 = verify_3.json()
    assert body_3["success"] is False
    assert body_3["remainingAttempts"] == 0
    assert body_3["reason"] == "missing_vqa_telemetry"

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_last_result"] == "BLOCKED"
    assert runtime_body["vqa_passed"] is False
    assert runtime_body["active_challenge_id"] is None


def test_ai_challenge_verify_missing_vqa_telemetry_fails_and_records_risk() -> None:
    session_id = _session_id("sess-ai-verify-missing-telemetry")
    state_key = _state_key(session_id)
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    verify = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": 1,
            "catchXNorm": 0.45,
            "catchYNorm": 0.55,
        },
        headers=_headers(session_id),
    )
    assert verify.status_code == 200
    body = verify.json()
    assert body["success"] is False
    assert body["reason"] == "missing_vqa_telemetry"

    runtime = client.get(f"/runtime/{state_key}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_passed"] is False
    assert runtime_body["risk_score"] > 0.0
    assert runtime_body["last_step_risk"] is not None


def test_runtime_state_refreshes_stale_snapshot_from_decision_engine() -> None:
    session_id = _session_id("sess-runtime-refresh")
    state_key = _state_key(session_id)
    policy_version = _decision_engine.policy_loader.load(session_id=state_key).policy_version

    _state_store.upsert(
        state_key,
        RuntimeStateSnapshot(
            flow_state="F4M",
            seat_mode="MANUAL",
            defense_tier="T0",
            risk_score=0.0,
            updated_ts_ms=1,
        ),
    )

    _decision_engine.session_state.get_or_create(state_key, policy_version=policy_version)
    _decision_engine.session_state.update_by_role(
        "guard",
        state_key,
        {
            "riskScore": 0.82,
            "defenseTier": "T2",
            "lastStepRisk": 0.82,
            "lastGuardTsMs": 1710000000000,
        },
        is_allow=True,
    )
    _decision_engine.session_state.update_by_role(
        "orchestrator",
        state_key,
        {"flowState": "S4"},
        is_allow=True,
    )

    runtime = client.get(f"/runtime/{state_key}")
    assert runtime.status_code == 200
    body = runtime.json()
    assert body["flow_state"] == "F3M"
    assert body["seat_mode"] == "MANUAL"
    assert body["defense_tier"] == "T2"
    assert body["risk_score"] == 0.82
    assert body["last_step_risk"] == 0.82
    assert body["last_guard_ts_ms"] == 1710000000000

    refreshed = _state_store.get(state_key)
    assert refreshed is not None
    assert refreshed.flow_state == "F3M"
    assert refreshed.seat_mode == "MANUAL"
    assert refreshed.defense_tier == "T2"
    assert refreshed.risk_score == 0.82


def test_runtime_state_skips_refresh_for_fresh_snapshot_without_runtime_drift(monkeypatch) -> None:
    session_id = _session_id("sess-runtime-fresh")
    state_key = _state_key(session_id)
    now_ms = 1710000005000
    policy_version = _decision_engine.policy_loader.load(session_id=state_key).policy_version

    snap = RuntimeStateSnapshot(
        flow_state="F3M",
        seat_mode="MANUAL",
        defense_tier="T2",
        risk_score=0.82,
        last_step_risk=0.82,
        last_guard_ts_ms=1710000000000,
        policy_version=policy_version,
        updated_ts_ms=now_ms,
    )
    _state_store.upsert(state_key, snap)

    _decision_engine.session_state.get_or_create(state_key, policy_version=policy_version)
    _decision_engine.session_state.update_by_role(
        "guard",
        state_key,
        {
            "riskScore": 0.82,
            "defenseTier": "T2",
            "lastStepRisk": 0.82,
            "lastGuardTsMs": 1710000000000,
        },
        is_allow=True,
    )
    _decision_engine.session_state.update_by_role(
        "orchestrator",
        state_key,
        {"flowState": "S4"},
        is_allow=True,
    )

    upsert_calls = 0
    original_upsert = _state_store.upsert

    def _counting_upsert(session_id: str, snapshot: RuntimeStateSnapshot) -> None:
        nonlocal upsert_calls
        upsert_calls += 1
        original_upsert(session_id, snapshot)

    monkeypatch.setattr(api_main, "time", types.SimpleNamespace(time=lambda: now_ms / 1000.0))
    monkeypatch.setattr(_state_store, "upsert", _counting_upsert)

    runtime = client.get(f"/runtime/{state_key}")
    assert runtime.status_code == 200
    body = runtime.json()
    assert body["flow_state"] == "F3M"
    assert body["defense_tier"] == "T2"
    assert body["risk_score"] == 0.82
    assert upsert_calls == 0


def test_ai_challenge_verify_success_marks_runtime_passed() -> None:
    session_id = _session_id("sess-ai-verify-pass")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    ingest = client.post(
        "/ai/telemetry/ingest",
        json={
            "matchId": MATCH_ID,
            "stage": "VQA_CHALLENGE",
            "events": _vqa_events(),
        },
        headers=_headers(session_id),
    )
    assert ingest.status_code == 200

    verify = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": 1,
            "catchXNorm": 0.45,
            "catchYNorm": 0.55,
        },
        headers=_headers(session_id),
    )
    assert verify.status_code == 200
    body = verify.json()
    assert body["success"] is True
    assert body["remainingAttempts"] == 3
    assert body.get("reason") is None

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_passed"] is True
    assert runtime_body["vqa_required"] is False
    assert runtime_body["vqa_attempt_count"] == 0
    assert runtime_body["active_challenge_id"] is None


def test_ai_challenge_verify_success_on_last_remaining_attempt_does_not_block() -> None:
    session_id = _session_id("sess-ai-verify-last-success")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    for attempt in range(1, 3):
        verify_fail = client.post(
            "/ai/challenge/verify",
            json={
                "matchId": MATCH_ID,
                "challengeId": challenge_id,
                "caught": False,
                "catchTsMs": attempt,
                "catchXNorm": 0.5,
                "catchYNorm": 0.5,
            },
            headers=_headers(session_id),
        )
        assert verify_fail.status_code == 200
        assert verify_fail.json()["success"] is False

    ingest = client.post(
        "/ai/telemetry/ingest",
        json={
            "matchId": MATCH_ID,
            "stage": "VQA_CHALLENGE",
            "events": _vqa_events(),
        },
        headers=_headers(session_id),
    )
    assert ingest.status_code == 200

    verify_pass = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": 3,
            "catchXNorm": 0.45,
            "catchYNorm": 0.55,
        },
        headers=_headers(session_id),
    )
    assert verify_pass.status_code == 200
    body = verify_pass.json()
    assert body["success"] is True
    assert body["remainingAttempts"] == 1
    assert body.get("reason") is None

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_passed"] is True
    assert runtime_body["vqa_last_result"] == "PASSED"
    assert runtime_body["vqa_attempt_count"] == 2


def test_ai_challenge_verify_pass_applies_vqa_risk_and_seat_entry_does_not_recompute() -> None:
    session_id = _session_id("sess-ai-verify-pass-risk")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    ingest = client.post(
        "/ai/telemetry/ingest",
        json={
            "matchId": MATCH_ID,
            "stage": "VQA_CHALLENGE",
            "events": _vqa_events(),
        },
        headers=_headers(session_id),
    )
    assert ingest.status_code == 200

    verify = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": 560,
            "catchXNorm": 0.52,
            "catchYNorm": 0.52,
        },
        headers=_headers(session_id),
    )
    assert verify.status_code == 200
    assert verify.json()["success"] is True

    runtime_before = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime_before.status_code == 200
    risk_before = runtime_before.json()["risk_score"]
    assert risk_before > 0.0
    assert runtime_before.json()["last_step_risk"] is not None

    seat_entry = client.post(
        "/ai/evaluate",
        json={
            "event": {
                "eventType": "SEAT_ENTRY",
                "requestPath": f"/seat/matches/{MATCH_ID}/recommendations/seat-entry",
                "requestMethod": "GET",
            },
            "context": {"sid": session_id},
        },
    )
    assert seat_entry.status_code == 200
    assert seat_entry.json() == {"decision": {"action": "NONE"}}

    runtime_after = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime_after.status_code == 200
    assert runtime_after.json()["risk_score"] == risk_before


def test_ai_challenge_verify_pass_with_user_header_does_not_500() -> None:
    session_id = _session_id("sess-ai-verify-pass-user")
    headers = _headers_with_user(session_id, "user-123")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=headers,
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    ingest = client.post(
        "/ai/telemetry/ingest",
        json={
            "matchId": MATCH_ID,
            "stage": "VQA_CHALLENGE",
            "events": _vqa_events(),
        },
        headers=headers,
    )
    assert ingest.status_code == 200

    verify = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": 560,
            "catchXNorm": 0.52,
            "catchYNorm": 0.52,
        },
        headers=headers,
    )
    assert verify.status_code == 200
    assert verify.json()["success"] is True


def test_ai_challenge_verify_pass_survives_runtime_policy_sync_failure(monkeypatch) -> None:
    session_id = _session_id("sess-ai-verify-sync-fail-open")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    ingest = client.post(
        "/ai/telemetry/ingest",
        json={
            "matchId": MATCH_ID,
            "stage": "VQA_CHALLENGE",
            "events": _vqa_events(),
        },
        headers=_headers(session_id),
    )
    assert ingest.status_code == 200

    original_load = _decision_engine.policy_loader.load

    def _raise_policy_unavailable(session_id: str):
        raise RuntimeError(f"runtime policy unavailable for {session_id}")

    monkeypatch.setattr(_decision_engine.policy_loader, "load", _raise_policy_unavailable)
    try:
        verify = client.post(
            "/ai/challenge/verify",
            json={
                "matchId": MATCH_ID,
                "challengeId": challenge_id,
                "caught": True,
                "catchTsMs": 560,
                "catchXNorm": 0.52,
                "catchYNorm": 0.52,
            },
            headers=_headers(session_id),
        )
    finally:
        monkeypatch.setattr(_decision_engine.policy_loader, "load", original_load)

    assert verify.status_code == 200
    assert verify.json()["success"] is True

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_passed"] is True
    assert runtime_body["vqa_last_result"] == "PASSED"


def test_ai_challenge_verify_pass_survives_decision_engine_mark_sync_failure(monkeypatch) -> None:
    session_id = _session_id("sess-ai-verify-mark-sync-fail-open")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    ingest = client.post(
        "/ai/telemetry/ingest",
        json={
            "matchId": MATCH_ID,
            "stage": "VQA_CHALLENGE",
            "events": _vqa_events(),
        },
        headers=_headers(session_id),
    )
    assert ingest.status_code == 200

    def _raise_mark_sync_failure(*, req, now_ms):  # noqa: ANN001
        raise RuntimeError(f"decision-engine mark sync unavailable for {req.session_id} at {now_ms}")

    monkeypatch.setattr(api_main, "_sync_mark_to_decision_engine", _raise_mark_sync_failure)

    verify = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": 560,
            "catchXNorm": 0.52,
            "catchYNorm": 0.52,
        },
        headers=_headers(session_id),
    )

    assert verify.status_code == 200
    assert verify.json()["success"] is True

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_passed"] is True
    assert runtime_body["vqa_last_result"] == "PASSED"



def test_ai_challenge_verify_pass_refreshes_anonymous_session_ttl() -> None:
    session_id = _session_id("sess-ai-verify-pass-anon")
    state_key = _state_key(session_id)
    session_state = _decision_engine.session_state
    redis = session_state._redis
    session_redis_key = session_state.session_key(state_key)

    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    ingest = client.post(
        "/ai/telemetry/ingest",
        json={
            "matchId": MATCH_ID,
            "stage": "VQA_CHALLENGE",
            "events": _vqa_events(),
        },
        headers=_headers(session_id),
    )
    assert ingest.status_code == 200

    policy_version = _decision_engine.policy_loader.load(session_id=state_key).policy_version
    session_state.get_or_create(state_key, policy_version=policy_version)
    assert redis.expire(session_redis_key, 1) is True
    ttl_before = redis.ttl(session_redis_key)
    assert ttl_before <= 1

    verify = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": 560,
            "catchXNorm": 0.52,
            "catchYNorm": 0.52,
        },
        headers=_headers(session_id),
    )
    assert verify.status_code == 200
    assert verify.json()["success"] is True

    ttl_after = redis.ttl(session_redis_key)
    assert ttl_after > ttl_before


def test_ai_challenge_verify_terminal_abnormal_pattern_returns_exhaustion_style_failure() -> None:
    session_id = _session_id("sess-ai-verify-abnormal")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    ingest = client.post(
        "/ai/telemetry/ingest",
        json={
            "matchId": MATCH_ID,
            "stage": "VQA_CHALLENGE",
            "events": [
                {"type": "mousemove", "tsMs": 0, "xNorm": 0.10, "yNorm": 0.50},
                {"type": "mousemove", "tsMs": 5, "xNorm": 0.22, "yNorm": 0.50},
                {"type": "mousemove", "tsMs": 10, "xNorm": 0.34, "yNorm": 0.50},
                {"type": "mousemove", "tsMs": 15, "xNorm": 0.46, "yNorm": 0.50},
                {"type": "mousemove", "tsMs": 20, "xNorm": 0.58, "yNorm": 0.50},
                {"type": "mousemove", "tsMs": 25, "xNorm": 0.70, "yNorm": 0.50},
            ],
        },
        headers=_headers(session_id),
    )
    assert ingest.status_code == 200
    assert ingest.json()["accepted"] is True

    verify = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": 25,
            "catchXNorm": 0.70,
            "catchYNorm": 0.50,
        },
        headers=_headers(session_id),
    )
    assert verify.status_code == 200
    body = verify.json()
    assert body["success"] is False
    assert body["remainingAttempts"] == 0
    assert body["reason"] == "abnormal_pattern"

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_last_result"] == "BLOCKED"
    assert runtime_body["vqa_passed"] is False
    assert runtime_body["active_challenge_id"] is None
    assert runtime_body["vqa_attempt_count"] == 1
    assert runtime_body["vqa_behavior_score"] >= 0.84
    assert runtime_body["risk_score"] > 0.0


def test_ai_challenge_verify_pass_survives_sid_source_drift() -> None:
    header_sid = _session_id("sess-ai-verify-header")
    auth_sid = _session_id("sess-ai-verify-auth")
    start_headers = _headers_with_authorization(header_sid, auth_sid)

    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=start_headers,
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    verify_headers = {
        "Authorization": start_headers["Authorization"],
    }
    ingest = client.post(
        "/ai/telemetry/ingest",
        json={
            "matchId": MATCH_ID,
            "stage": "VQA_CHALLENGE",
            "events": _vqa_events(),
        },
        headers=verify_headers,
    )
    assert ingest.status_code == 200

    verify = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": 560,
            "catchXNorm": 0.52,
            "catchYNorm": 0.52,
        },
        headers=verify_headers,
    )
    assert verify.status_code == 200
    assert verify.json()["success"] is True

    alias_runtime = client.get(f"/runtime/{auth_sid}")
    assert alias_runtime.status_code == 200
    assert alias_runtime.json()["vqa_passed"] is True

    evaluate = client.post(
        "/ai/evaluate",
        json={
            "event": {
                "eventType": "RECOMMENDATION_BLOCKS",
                "requestPath": f"/seat/matches/{MATCH_ID}/recommendations/blocks",
                "requestMethod": "GET",
            },
            "context": {"sid": auth_sid},
        },
    )
    assert evaluate.status_code == 200
    assert evaluate.json() == {"decision": {"action": "NONE"}}


def test_ai_challenge_verify_rejects_mismatched_challenge_id() -> None:
    session_id = _session_id("sess-ai-verify-mismatch")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    failed = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": False,
            "catchTsMs": 1,
            "catchXNorm": 0.5,
            "catchYNorm": 0.5,
        },
        headers=_headers(session_id),
    )
    assert failed.status_code == 200
    assert failed.json()["remainingAttempts"] == 2

    verify = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": "CH_INVALID",
            "caught": True,
            "catchTsMs": 1,
            "catchXNorm": 0.4,
            "catchYNorm": 0.6,
        },
        headers=_headers(session_id),
    )
    assert verify.status_code == 200
    body = verify.json()
    assert body["success"] is False
    assert body["remainingAttempts"] == 0
    assert body["reason"] == "invalid_challenge"

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_attempt_count"] == 1

    restarted = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert restarted.status_code == 200
    assert restarted.json()["remainingAttempts"] == 2


def test_ai_challenge_verify_rejects_expired_challenge_without_consuming_attempt() -> None:
    session_id = _session_id("sess-ai-verify-expired")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    failed = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": False,
            "catchTsMs": 1,
            "catchXNorm": 0.5,
            "catchYNorm": 0.5,
        },
        headers=_headers(session_id),
    )
    assert failed.status_code == 200
    assert failed.json()["remainingAttempts"] == 2

    runtime_before = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime_before.status_code == 200
    expires_at_ms = runtime_before.json()["active_challenge_expires_at_ms"]

    snap = _state_store.get(_state_key(session_id))
    assert snap is not None
    _state_store.upsert(
        _state_key(session_id),
        snap.model_copy(update={"active_challenge_expires_at_ms": 1}),
    )

    verify = client.post(
        "/ai/challenge/verify",
        json={
            "matchId": MATCH_ID,
            "challengeId": challenge_id,
            "caught": True,
            "catchTsMs": expires_at_ms,
            "catchXNorm": 0.4,
            "catchYNorm": 0.6,
        },
        headers=_headers(session_id),
    )
    assert verify.status_code == 200
    body = verify.json()
    assert body["success"] is False
    assert body["remainingAttempts"] == 0
    assert body["reason"] == "expired_challenge"

    runtime_after = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime_after.status_code == 200
    assert runtime_after.json()["vqa_attempt_count"] == 1

    restarted = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert restarted.status_code == 200
    assert restarted.json()["remainingAttempts"] == 2


def test_ai_challenge_verify_exhaustion_does_not_invoke_auth_guard(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def _stub_block_user_in_auth_guard(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "traffic_master_ai.defense.api.main._block_user_in_auth_guard",
        _stub_block_user_in_auth_guard,
    )

    session_id = _session_id("sess-ai-verify-auth-guard")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers_with_user(session_id, "42"),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    for attempt in range(1, 4):
        verify = client.post(
            "/ai/challenge/verify",
            json={
                "matchId": MATCH_ID,
                "challengeId": challenge_id,
                "caught": False,
                "catchTsMs": attempt,
                "catchXNorm": 0.5,
                "catchYNorm": 0.5,
            },
            headers=_headers(session_id),
        )
        assert verify.status_code == 200

    assert captured == {}


def test_ai_precheck_resets_exhausted_vqa_state_for_new_booking_attempt() -> None:
    session_id = _session_id("sess-ai-precheck-reset")
    start = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert start.status_code == 200
    challenge_id = start.json()["challengeId"]

    for attempt in range(1, 4):
        verify = client.post(
            "/ai/challenge/verify",
            json={
                "matchId": MATCH_ID,
                "challengeId": challenge_id,
                "caught": False,
                "catchTsMs": attempt,
                "catchXNorm": 0.5,
                "catchYNorm": 0.5,
            },
            headers=_headers(session_id),
        )
        assert verify.status_code == 200

    precheck = client.post(
        "/ai/precheck",
        json={"matchId": MATCH_ID, "cfToken": "ok-token"},
        headers=_headers(session_id),
    )
    assert precheck.status_code == 200
    assert precheck.json()["allowed"] is True

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_attempt_count"] == 0
    assert runtime_body["vqa_last_result"] is None
    assert runtime_body["turnstile_verified"] is True

    restarted = client.post(
        "/ai/challenge/start",
        json={"matchId": MATCH_ID},
        headers=_headers(session_id),
    )
    assert restarted.status_code == 200
    assert restarted.json()["remainingAttempts"] == 3


def test_ai_precheck_clears_sid_level_vqa_pass_marker_for_new_booking_attempt() -> None:
    session_id = _session_id("sess-ai-precheck-sid-reset")
    marked = client.post(
        "/runtime/vqa/mark",
        json={"session_id": session_id, "vqa_passed": True, "flow_state": "F3"},
    )
    assert marked.status_code == 200
    assert marked.json()["vqa_passed"] is True

    precheck = client.post(
        "/ai/precheck",
        json={"matchId": MATCH_ID, "cfToken": "ok-token"},
        headers=_headers(session_id),
    )
    assert precheck.status_code == 200
    assert precheck.json()["allowed"] is True

    response = client.post(
        "/ai/evaluate",
        json={
            "event": {
                "eventType": "SEAT_ENTRY",
                "requestPath": f"/seat/matches/{MATCH_ID}/seat-groups",
                "requestMethod": "GET",
            },
            "context": {"sid": session_id},
        },
    )
    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "REQUIRE_S3"}}
