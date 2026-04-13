import os
import json
import sys
import types
from types import SimpleNamespace

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

import traffic_master_ai.defense.api.main as api_main
from traffic_master_ai.defense.api.audit import DefenseDecisionAuditLogger
from traffic_master_ai.defense.api.models import EvaluateResponse, RuntimeStateSnapshot
from traffic_master_ai.defense.d0_mvp.core.enums import DefenseTier, FlowState

client = TestClient(api_main.app)
MATCH_ID = 687


def _evaluate_payload(*, sid: str, event_type: str, path: str, method: str) -> dict:
    return {
        "event": {
            "eventType": event_type,
            "requestPath": path,
            "requestMethod": method,
        },
        "context": {"sid": sid},
    }


def _headers(*, session_id: str | None = None, user_id: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if session_id is not None:
        headers["X-Session-Id"] = session_id
    if user_id is not None:
        headers["X-User-Id"] = user_id
    return headers


def _read_audit_rows(log_path) -> list[dict]:
    if not log_path.exists():
        return []
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _queue_bot_like_events() -> list[dict[str, float | int | str]]:
    return [
        {"type": "mousemove", "tsMs": 0, "xNorm": 0.10, "yNorm": 0.50},
        {"type": "mousemove", "tsMs": 80, "xNorm": 0.18, "yNorm": 0.50},
        {"type": "mousemove", "tsMs": 160, "xNorm": 0.26, "yNorm": 0.50},
        {"type": "mousemove", "tsMs": 240, "xNorm": 0.34, "yNorm": 0.50},
        {"type": "mousemove", "tsMs": 320, "xNorm": 0.42, "yNorm": 0.50},
        {"type": "mousemove", "tsMs": 400, "xNorm": 0.50, "yNorm": 0.50},
        {"type": "mousemove", "tsMs": 480, "xNorm": 0.58, "yNorm": 0.50},
        {"type": "click", "tsMs": 560, "xNorm": 0.66, "yNorm": 0.50, "button": 0},
    ]


def test_queue_enter_blocks_without_precheck() -> None:
    sid = "sess-eval-precheck-block-1"
    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="QUEUE_ENTER",
            path=f"/queue/matches/{MATCH_ID}/enter",
            method="POST",
        ),
    )
    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "BLOCK"}}


def test_storage_meta_exposes_snapshot_and_decision_state_backends() -> None:
    response = client.get("/meta/storage")

    assert response.status_code == 200
    assert response.json() == {
        "runtime_state_backend": "memory",
        "decision_state_backend": "memory",
    }


def test_queue_enter_block_invokes_auth_guard(monkeypatch) -> None:
    sid = "sess-eval-precheck-block-auth-1"
    captured: dict[str, str] = {}

    def _stub_block_user_in_auth_guard(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(api_main, "_block_user_in_auth_guard", _stub_block_user_in_auth_guard)

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="QUEUE_ENTER",
            path=f"/queue/matches/{MATCH_ID}/enter",
            method="POST",
        ),
        headers=_headers(user_id="42"),
    )

    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "BLOCK"}}
    assert captured["user_id"] == "42"
    assert captured["session_id"] == f"{sid}:{MATCH_ID}"
    assert captured["trigger"] == "ai_evaluate_precheck_block"


def test_queue_enter_precheck_block_emits_canonical_audit(tmp_path, monkeypatch) -> None:
    sid = "sess-eval-precheck-audit-1"
    log_path = tmp_path / "decision_audit.jsonl"
    monkeypatch.setattr(api_main, "_audit", DefenseDecisionAuditLogger(str(log_path)))
    monkeypatch.setattr(api_main, "_block_user_in_auth_guard", lambda **kwargs: None)

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="QUEUE_ENTER",
            path=f"/queue/matches/{MATCH_ID}/enter",
            method="POST",
        ),
    )

    assert response.status_code == 200
    rows = _read_audit_rows(log_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "EVALUATE"
    assert row["session_id"] == f"{sid}:{MATCH_ID}"
    assert row["flow_state"] == "F1"
    assert row["action"] == "BLOCK"
    assert row["reason_code"] == "PRECHECK_REQUIRED"
    assert row["raw_payload"]["decision_source"] == "target_api_early_return"
    assert row["raw_payload"]["decision_reason"] == "precheck_block"
    assert row["raw_payload"]["target_event_type"] == "QUEUE_ENTER"
    assert row["raw_payload"]["precheck_valid"] is False


def test_seat_entry_immediate_return_emits_canonical_audit(tmp_path, monkeypatch) -> None:
    sid = "sess-eval-seat-entry-audit-1"
    state_key = f"{sid}:{MATCH_ID}"
    log_path = tmp_path / "decision_audit.jsonl"
    monkeypatch.setattr(api_main, "_audit", DefenseDecisionAuditLogger(str(log_path)))
    api_main._state_store.upsert(
        state_key,
        RuntimeStateSnapshot(
            flow_state="F1",
            policy_version="policy-seat-entry",
            vqa_passed=False,
        ),
    )

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="SEAT_ENTRY",
            path=f"/seat/matches/{MATCH_ID}/entry",
            method="POST",
        ),
    )

    assert response.status_code == 200
    rows = _read_audit_rows(log_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "EVALUATE"
    assert row["action"] == "REQUIRE_S3"
    assert row["flow_state"] == "F2"
    assert row["reason_code"] == "SEAT_ENTRY_VQA_REQUIRED"
    assert row["policy_version"] == "policy-seat-entry"
    assert row["raw_payload"]["decision_reason"] == "seat_entry_immediate"
    assert row["raw_payload"]["target_event_type"] == "SEAT_ENTRY"
    assert row["raw_payload"]["vqa_passed"] is False


def test_soft_action_early_return_emits_canonical_audit(tmp_path, monkeypatch) -> None:
    sid = "sess-eval-soft-action-audit-1"
    state_key = f"{sid}:{MATCH_ID}"
    log_path = tmp_path / "decision_audit.jsonl"
    monkeypatch.setattr(api_main, "_audit", DefenseDecisionAuditLogger(str(log_path)))
    api_main._state_store.upsert(
        state_key,
        RuntimeStateSnapshot(
            flow_state="F3",
            policy_version="policy-soft-action",
            latest_seat_stage_summary={
                "mousePointCount": 4,
                "botRisk": 0.61,
            },
        ),
    )

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="SEAT_HOLDS",
            path=f"/seat/matches/{MATCH_ID}/seat-holds",
            method="POST",
        ),
    )

    assert response.status_code == 200
    rows = _read_audit_rows(log_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "EVALUATE"
    assert row["action"] == "THROTTLE"
    assert row["flow_state"] == "F4M"
    assert row["reason_code"] == "TARGET_SOFT_ACTION"
    assert row["policy_version"] == row["raw_payload"]["runtime_state"]["policy_version"]
    assert row["raw_payload"]["decision_reason"] == "soft_action"
    assert row["raw_payload"]["decision_source"] == "target_api_early_return"
    assert row["raw_payload"]["target_event_type"] == "SEAT_HOLDS"
    assert row["raw_payload"]["feature_summary"] == {
        "mouse_point_count": 4,
        "bot_risk": 0.61,
    }

    runtime = client.get(f"/runtime/{sid}:{MATCH_ID}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["flow_state"] == "F4M"
    assert runtime_body["seat_mode"] == "MANUAL"


def test_post_vqa_events_require_s3_when_vqa_not_passed(monkeypatch) -> None:
    sid = "sess-eval-post-vqa-guard-1"
    captured: list[dict[str, str | None]] = []

    def _stub_block_user_in_auth_guard(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(api_main, "_block_user_in_auth_guard", _stub_block_user_in_auth_guard)
    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="RECOMMENDATION_BLOCKS",
            path=f"/seat/matches/{MATCH_ID}/recommendations/blocks",
            method="GET",
        ),
    )
    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "REQUIRE_S3"}}
    assert captured == []


def test_legacy_snapshot_restores_seat_mode_from_flow_hint() -> None:
    session_id = "sess-legacy-seat-mode-hint"
    d0_state = SimpleNamespace(
        flow_state=FlowState.S5,
        defense_tier=DefenseTier.T1,
        risk_score=0.33,
        last_step_risk=0.33,
        last_guard_ts_ms=1710000000000,
        challenge_fail_count=0,
        seat_taken_streak=0,
        hold_fail_streak=0,
        probation_until_ms=None,
        s3_passed=False,
    )

    snap = api_main._legacy_snapshot_from_d0_state(
        session_id=session_id,
        d0_state=d0_state,
        policy_version="def-pol-2.0.0",
        challenge_max_attempts=3,
        now_ms=1710000001234,
        user_id=None,
        flow_state_hint="F4M",
    )

    assert snap.flow_state == "F4M"
    assert snap.seat_mode == "MANUAL"


def test_queue_enter_soft_action_still_persists_d0_score_and_audit(tmp_path, monkeypatch) -> None:
    sid = "sess-eval-soft-score-1"
    state_key = f"{sid}:{MATCH_ID}"
    log_path = tmp_path / "decision_audit.jsonl"
    monkeypatch.setattr(api_main, "_audit", DefenseDecisionAuditLogger(str(log_path)))
    precheck = client.post(
        "/ai/precheck",
        json={"matchId": MATCH_ID, "cfToken": "ok-token"},
        headers=_headers(session_id=sid),
    )
    assert precheck.status_code == 200
    ingest = client.post(
        "/ai/telemetry/ingest",
        json={
            "matchId": MATCH_ID,
            "stage": "QUEUE_ENTER_PRECLICK",
            "events": _queue_bot_like_events(),
        },
        headers=_headers(session_id=sid),
    )
    assert ingest.status_code == 200

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="QUEUE_ENTER",
            path=f"/queue/matches/{MATCH_ID}/enter",
            method="POST",
        ),
        headers=_headers(session_id=sid),
    )

    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "REQUIRE_S3"}}

    decision_state = api_main._decision_engine.session_state.get(state_key)
    assert decision_state is not None
    assert decision_state.risk_score > 0.0
    assert decision_state.last_step_risk is not None
    rows = _read_audit_rows(log_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == state_key
    assert row["action"] == "REQUIRE_S3"
    assert row["reason_code"] == "TARGET_SOFT_ACTION"
    assert row["raw_payload"]["decision_source"] == "target_api_early_return"
    assert row["raw_payload"]["runtime_state"]["risk_score"] == decision_state.risk_score
    assert row["raw_payload"]["runtime_state"]["last_step_risk"] == decision_state.last_step_risk


def test_legacy_challenge_action_does_not_emit_require_s3(monkeypatch) -> None:
    sid = "sess-eval-legacy-challenge-1"
    captured: list[dict[str, str | None]] = []
    precheck = client.post(
        "/ai/precheck",
        json={"matchId": MATCH_ID, "cfToken": "ok-token"},
        headers=_headers(session_id=sid),
    )
    assert precheck.status_code == 200
    assert precheck.json()["allowed"] is True

    def _stub_block_user_in_auth_guard(**kwargs):
        captured.append(kwargs)

    def _stub_execute_legacy_evaluate(_req, audit=True):
        return (
            EvaluateResponse(
                allow=False,
                session_id=f"{sid}:{MATCH_ID}",
                flow_state="F1",
                defense_tier="T1",
                action="CHALLENGE",
                actions=["CHALLENGE"],
                reason="CHALLENGE_REQUIRED",
                rule_hits=[],
                risk_score=0.7,
                policy_version="def-pol-2.0.0",
                headers_to_add={},
                decision_id="dec-test",
                latency_ms=1,
                version="v2",
            ),
            RuntimeStateSnapshot(updated_ts_ms=0),
        )

    monkeypatch.setattr(api_main, "_execute_legacy_evaluate", _stub_execute_legacy_evaluate)
    monkeypatch.setattr(api_main, "_block_user_in_auth_guard", _stub_block_user_in_auth_guard)

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="QUEUE_ENTER",
            path=f"/queue/matches/{MATCH_ID}/enter",
            method="POST",
        ),
    )
    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "THROTTLE"}}
    assert captured == []


def test_post_vqa_guard_is_bypassed_after_vqa_pass(monkeypatch) -> None:
    sid = "sess-eval-post-vqa-pass-1"
    state_key = f"{sid}:{MATCH_ID}"
    captured: list[dict[str, str | None]] = []
    marked = client.post(
        "/runtime/vqa/mark",
        json={"session_id": state_key, "vqa_passed": True, "flow_state": "F3"},
    )
    assert marked.status_code == 200
    assert marked.json()["vqa_passed"] is True

    def _stub_block_user_in_auth_guard(**kwargs):
        captured.append(kwargs)

    def _stub_execute_legacy_evaluate(_req, audit=True):
        return (
            EvaluateResponse(
                allow=True,
                session_id=state_key,
                flow_state="F3",
                defense_tier="T0",
                action="NONE",
                actions=["NONE"],
                reason=None,
                rule_hits=[],
                risk_score=0.0,
                policy_version="def-pol-2.0.0",
                headers_to_add={},
                decision_id="dec-test-pass",
                latency_ms=1,
                version="v2",
            ),
            RuntimeStateSnapshot(updated_ts_ms=0, vqa_passed=True),
        )

    monkeypatch.setattr(api_main, "_execute_legacy_evaluate", _stub_execute_legacy_evaluate)
    monkeypatch.setattr(api_main, "_block_user_in_auth_guard", _stub_block_user_in_auth_guard)

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="SEAT_HOLDS",
            path=f"/seat/matches/{MATCH_ID}/seat-holds",
            method="POST",
        ),
    )
    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "NONE"}}
    assert captured == []


def test_post_vqa_risky_seat_stage_is_throttled_instead_of_rechallenged(monkeypatch) -> None:
    sid = "sess-eval-post-vqa-risky-seat-stage-1"
    state_key = f"{sid}:{MATCH_ID}"
    captured: list[dict[str, str | None]] = []
    api_main._state_store.upsert(
        state_key,
        RuntimeStateSnapshot(
            updated_ts_ms=1,
            flow_state="S4",
            vqa_required=False,
            vqa_passed=True,
            vqa_last_result="PASSED",
            latest_seat_stage_summary={"mousePointCount": 3, "botRisk": 0.95},
            latest_seat_stage_at_ms=1,
        ),
    )

    def _stub_block_user_in_auth_guard(**kwargs):
        captured.append(kwargs)

    def _stub_execute_legacy_evaluate(_req):
        raise AssertionError("legacy evaluation should not run for soft-action post-VQA flow")

    monkeypatch.setattr(api_main, "_block_user_in_auth_guard", _stub_block_user_in_auth_guard)
    monkeypatch.setattr(api_main, "_execute_legacy_evaluate", _stub_execute_legacy_evaluate)

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="SEAT_HOLDS",
            path=f"/seat/matches/{MATCH_ID}/seat-holds",
            method="POST",
        ),
    )
    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "THROTTLE"}}
    assert captured == []


def test_post_vqa_guard_uses_sid_level_vqa_mark(monkeypatch) -> None:
    sid = "sess-eval-post-vqa-sid-mark-1"
    state_key = f"{sid}:{MATCH_ID}"
    marked = client.post(
        "/runtime/vqa/mark",
        json={"session_id": sid, "vqa_passed": True, "flow_state": "F3"},
    )
    assert marked.status_code == 200
    assert marked.json()["vqa_passed"] is True

    def _stub_execute_legacy_evaluate(_req, audit=True):
        return (
            EvaluateResponse(
                allow=True,
                session_id=state_key,
                flow_state="F3",
                defense_tier="T0",
                action="NONE",
                actions=["NONE"],
                reason=None,
                rule_hits=[],
                risk_score=0.0,
                policy_version="def-pol-2.0.0",
                headers_to_add={},
                decision_id="dec-test-sid-pass",
                latency_ms=1,
                version="v2",
            ),
            RuntimeStateSnapshot(updated_ts_ms=0, vqa_passed=True),
        )

    monkeypatch.setattr(api_main, "_execute_legacy_evaluate", _stub_execute_legacy_evaluate)

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="SEAT_HOLDS",
            path=f"/seat/matches/{MATCH_ID}/seat-holds",
            method="POST",
        ),
    )
    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "NONE"}}


def test_legacy_block_forwards_user_id_to_decision_engine(monkeypatch) -> None:
    sid = "sess-eval-legacy-block-user-1"
    state_key = f"{sid}:{MATCH_ID}"
    precheck = client.post(
        "/ai/precheck",
        json={"matchId": MATCH_ID, "cfToken": "ok-token"},
        headers=_headers(session_id=sid, user_id="42"),
    )
    assert precheck.status_code == 200

    captured: dict[str, str | None] = {}
    block_sync_calls: list[dict[str, str | None]] = []

    def _stub_block_user_in_auth_guard(**kwargs):
        block_sync_calls.append(kwargs)

    def _stub_execute_legacy_evaluate(req, audit=True):
        captured["user_id"] = req.user_id
        return (
            EvaluateResponse(
                allow=False,
                session_id=state_key,
                flow_state="F1",
                defense_tier="T3",
                action="BLOCK",
                actions=["BLOCK"],
                reason="BLOCKED",
                rule_hits=[],
                risk_score=0.95,
                policy_version="def-pol-2.0.0",
                headers_to_add={},
                decision_id="dec-test-block",
                latency_ms=1,
                version="v2",
            ),
            RuntimeStateSnapshot(updated_ts_ms=0, user_id=req.user_id),
        )

    monkeypatch.setattr(api_main, "_execute_legacy_evaluate", _stub_execute_legacy_evaluate)
    monkeypatch.setattr(api_main, "_block_user_in_auth_guard", _stub_block_user_in_auth_guard)

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="QUEUE_ENTER",
            path=f"/queue/matches/{MATCH_ID}/enter",
            method="POST",
        ),
        headers=_headers(user_id="42"),
    )

    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "BLOCK"}}
    assert captured["user_id"] == "42"
    assert len(block_sync_calls) == 1
    assert block_sync_calls[0]["user_id"] == "42"
    assert block_sync_calls[0]["session_id"] == state_key
    assert block_sync_calls[0]["trigger"] == "ai_evaluate_decision_block"
    assert block_sync_calls[0]["trace_id"]


def test_legacy_evaluate_exception_fails_open_without_runtime_refresh(monkeypatch) -> None:
    sid = "sess-eval-legacy-exception-1"
    state_key = f"{sid}:{MATCH_ID}"
    snap = RuntimeStateSnapshot(
        flow_state="F3M",
        seat_mode="MANUAL",
        defense_tier="T1",
        risk_score=0.31,
        updated_ts_ms=1710000000000,
    )
    api_main._state_store.upsert(state_key, snap)

    refresh_call_count = 0

    def _stub_execute_legacy_evaluate(_req, audit=True):
        raise RuntimeError("legacy evaluate exploded")

    def _stub_refresh_runtime_snapshot_from_decision_engine(**kwargs):
        nonlocal refresh_call_count
        refresh_call_count += 1
        return kwargs["snap"]

    monkeypatch.setattr(api_main, "_execute_legacy_evaluate", _stub_execute_legacy_evaluate)
    monkeypatch.setattr(
        api_main,
        "_refresh_runtime_snapshot_from_decision_engine",
        _stub_refresh_runtime_snapshot_from_decision_engine,
    )

    response = client.post(
        "/ai/evaluate",
        json=_evaluate_payload(
            sid=sid,
            event_type="SEAT_HOLDS",
            path=f"/seat/matches/{MATCH_ID}/seat-holds",
            method="POST",
        ),
    )

    assert response.status_code == 200
    assert response.json() == {"decision": {"action": "NONE"}}
    assert refresh_call_count == 1
