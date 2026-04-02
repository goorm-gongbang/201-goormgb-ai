import os
import uuid

import jwt
from fastapi.testclient import TestClient

os.environ.setdefault("CI", "true")

from traffic_master_ai.defense.api.main import app

client = TestClient(app)
MATCH_ID = 687


def _headers(session_id: str) -> dict[str, str]:
    return {"X-Session-Id": session_id}


def _headers_with_authorization(session_id: str, auth_sid: str) -> dict[str, str]:
    token = jwt.encode({"sid": auth_sid}, "test-secret-that-is-long-enough-32b", algorithm="HS256")
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

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_last_result"] == "BLOCKED"
    assert runtime_body["vqa_passed"] is False
    assert runtime_body["active_challenge_id"] is None


def test_ai_challenge_verify_success_marks_runtime_passed() -> None:
    session_id = _session_id("sess-ai-verify-pass")
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
    assert body["success"] is True
    assert body["remainingAttempts"] == 3

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

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_passed"] is True
    assert runtime_body["vqa_last_result"] == "PASSED"
    assert runtime_body["vqa_attempt_count"] == 2


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

    runtime = client.get(f"/runtime/{_state_key(session_id)}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_attempt_count"] == 0


def test_ai_challenge_verify_block_invokes_auth_guard_with_stored_user_id(monkeypatch) -> None:
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

    assert captured["user_id"] == "42"
    assert captured["session_id"] == _state_key(session_id)
    assert captured["trigger"] == "ai_challenge_verify_exhausted_block"
