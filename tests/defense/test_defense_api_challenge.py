import hashlib
import hmac
import random

from fastapi.testclient import TestClient

from traffic_master_ai.defense.api.main import app

client = TestClient(app)


def _derive_target(
    session_id: str,
    challenge_id: str,
    challenge_type: str,
    issued_at_ms: int,
) -> tuple[float, float, int]:
    seed_src = f"{session_id}:{challenge_id}:{challenge_type}:{issued_at_ms}"
    digest = hmac.new(
        b"tm-local-dev-secret",
        seed_src.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    rng = random.Random(int.from_bytes(digest[:8], byteorder="big", signed=False))
    return (
        round(rng.uniform(220.0, 580.0), 2),
        round(rng.uniform(120.0, 330.0), 2),
        rng.randint(920, 1360),
    )


def _make_pass_events(target_x: float, target_y: float, click_ts: int) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    start_x = target_x - 120.0
    start_y = target_y + 90.0
    events.append({"t_ms": 0, "x": start_x, "y": start_y, "event": "down"})
    for idx in range(1, 33):
        ratio = idx / 32
        events.append(
            {
                "t_ms": idx * 20,
                "x": round(start_x + (target_x - start_x) * ratio, 2),
                "y": round(start_y + (target_y - start_y) * ratio, 2),
                "event": "move",
            }
        )
    events.append({"t_ms": click_ts, "x": target_x, "y": target_y, "event": "click"})
    return events


def test_evaluate_requires_vqa_once_after_queue() -> None:
    response = client.post(
        "/evaluate",
        json={
            "session_id": "sess-vqa-gate-1",
            "path": "/api/holds",
            "method": "POST",
            "timestamp": 1772500000000,
            "flow_state": "S4",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["allow"] is False
    assert body["action"] == "CHALLENGE"
    assert body["headers_to_add"]["x-defense-action"] == "challenge"


def test_challenge_token_binding_and_signature_check() -> None:
    start = client.post(
        "/challenge/start",
        json={"session_id": "sess-bind-1", "flow_state": "S3", "challenge_type": "catch_ball"},
    )
    assert start.status_code == 200
    payload = start.json()

    bad_last = "A" if payload["challenge_token"][-1] != "A" else "B"
    bad_token = payload["challenge_token"][:-1] + bad_last
    bad_event = client.post(
        "/challenge/event",
        json={
            "session_id": "sess-bind-1",
            "challenge_id": payload["challenge_id"],
            "challenge_token": bad_token,
            "events": [],
        },
    )
    assert bad_event.status_code == 400

    mismatch = client.post(
        "/challenge/event",
        json={
            "session_id": "sess-bind-2",
            "challenge_id": payload["challenge_id"],
            "challenge_token": payload["challenge_token"],
            "events": [],
        },
    )
    assert mismatch.status_code == 400


def test_challenge_verify_retries_then_blocks() -> None:
    session_id = "sess-verify-1"
    start = client.post(
        "/challenge/start",
        json={"session_id": session_id, "flow_state": "S3", "challenge_type": "catch_ball"},
    )
    assert start.status_code == 200
    payload = start.json()

    ingest = client.post(
        "/challenge/event",
        json={
            "session_id": session_id,
            "challenge_id": payload["challenge_id"],
            "challenge_token": payload["challenge_token"],
            "events": [
                {"t_ms": 0, "x": 10, "y": 10, "event": "down"},
                {"t_ms": 10, "x": 20, "y": 20, "event": "click"},
            ],
        },
    )
    assert ingest.status_code == 200
    assert ingest.json()["accepted_events"] == 2

    verify_1 = client.post(
        "/challenge/verify",
        json={
            "session_id": session_id,
            "challenge_id": payload["challenge_id"],
            "challenge_token": payload["challenge_token"],
        },
    )
    assert verify_1.status_code == 200
    body_1 = verify_1.json()
    assert body_1["result"] == "FAILED"
    assert body_1["passed"] is False
    assert body_1["attempts_left"] == 1
    assert body_1["action"] == "CHALLENGE"

    verify_2 = client.post(
        "/challenge/verify",
        json={
            "session_id": session_id,
            "challenge_id": payload["challenge_id"],
            "challenge_token": payload["challenge_token"],
        },
    )
    assert verify_2.status_code == 200
    body_2 = verify_2.json()
    assert body_2["result"] == "BLOCKED"
    assert body_2["passed"] is False
    assert body_2["attempts_left"] == 0
    assert body_2["action"] == "BLOCK"

    runtime = client.get(f"/runtime/{session_id}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["flow_state"] == "SX"
    assert runtime_body["defense_tier"] == "T3"


def test_challenge_verify_passes_with_server_consistent_events() -> None:
    session_id = "sess-pass-1"
    start = client.post(
        "/challenge/start",
        json={"session_id": session_id, "flow_state": "S3", "challenge_type": "catch_ball"},
    )
    assert start.status_code == 200
    payload = start.json()
    target_x, target_y, timing_target_ms = _derive_target(
        session_id=session_id,
        challenge_id=payload["challenge_id"],
        challenge_type=payload["challenge_type"],
        issued_at_ms=payload["issued_at_ms"],
    )
    events = _make_pass_events(target_x, target_y, timing_target_ms)

    ingest = client.post(
        "/challenge/event",
        json={
            "session_id": session_id,
            "challenge_id": payload["challenge_id"],
            "challenge_token": payload["challenge_token"],
            "events": events,
        },
    )
    assert ingest.status_code == 200
    assert ingest.json()["accepted_events"] == len(events)

    verify = client.post(
        "/challenge/verify",
        json={
            "session_id": session_id,
            "challenge_id": payload["challenge_id"],
            "challenge_token": payload["challenge_token"],
            "final_click_ts_ms": timing_target_ms,
        },
    )
    assert verify.status_code == 200
    body = verify.json()
    assert body["result"] == "PASSED"
    assert body["action"] == "NONE"

    runtime = client.get(f"/runtime/{session_id}")
    assert runtime.status_code == 200
    runtime_body = runtime.json()
    assert runtime_body["vqa_passed"] is True
    assert runtime_body["flow_state"] == "S4"


def test_runtime_vqa_mark_endpoint_updates_state() -> None:
    session_id = "sess-mark-vqa-1"
    marked = client.post(
        "/runtime/vqa/mark",
        json={
            "session_id": session_id,
            "vqa_passed": True,
            "flow_state": "S4",
        },
    )
    assert marked.status_code == 200
    mark_body = marked.json()
    assert mark_body["vqa_passed"] is True
    assert mark_body["flow_state"] == "S4"

    runtime = client.get(f"/runtime/{session_id}")
    assert runtime.status_code == 200
    body = runtime.json()
    assert body["vqa_passed"] is True
    assert body["vqa_required"] is False
