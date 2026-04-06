import os

from fastapi.testclient import TestClient

os.environ.setdefault("CI", "true")

import traffic_master_ai.defense.api.main as api_main
from traffic_master_ai.defense.api.models import EvaluateResponse, RuntimeStateSnapshot

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

    def _stub_execute_legacy_evaluate(_req):
        return (
            EvaluateResponse(
                allow=False,
                session_id=f"{sid}:{MATCH_ID}",
                flow_state="S2",
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
        json={"session_id": state_key, "vqa_passed": True, "flow_state": "S4"},
    )
    assert marked.status_code == 200
    assert marked.json()["vqa_passed"] is True

    def _stub_block_user_in_auth_guard(**kwargs):
        captured.append(kwargs)

    def _stub_execute_legacy_evaluate(_req):
        return (
            EvaluateResponse(
                allow=True,
                session_id=state_key,
                flow_state="S4",
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


def test_post_vqa_guard_uses_sid_level_vqa_mark(monkeypatch) -> None:
    sid = "sess-eval-post-vqa-sid-mark-1"
    state_key = f"{sid}:{MATCH_ID}"
    marked = client.post(
        "/runtime/vqa/mark",
        json={"session_id": sid, "vqa_passed": True, "flow_state": "S4"},
    )
    assert marked.status_code == 200
    assert marked.json()["vqa_passed"] is True

    def _stub_execute_legacy_evaluate(_req):
        return (
            EvaluateResponse(
                allow=True,
                session_id=state_key,
                flow_state="S4",
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

    def _stub_execute_legacy_evaluate(req):
        captured["user_id"] = req.user_id
        return (
            EvaluateResponse(
                allow=False,
                session_id=state_key,
                flow_state="S2",
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
