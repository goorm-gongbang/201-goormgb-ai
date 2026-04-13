from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from traffic_master_ai.defense.d0_mvp.api.app import create_app
from traffic_master_ai.defense.d0_mvp.api.runtime import DefenseRuntime
from traffic_master_ai.defense.d0_mvp.observability.audit_logger import AuditLogger
from traffic_master_ai.defense.d0_mvp.observability.warehouse import AuditWarehouse
from traffic_master_ai.defense.d0_mvp.state.keyspace import CHALLENGE_KEY_PREFIX
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis


def _runtime(tmp_path: Path) -> DefenseRuntime:
    return DefenseRuntime(
        redis=InMemoryRedis(),
        audit_logger=AuditLogger(file_path=str(tmp_path / "decision_audit.jsonl")),
        audit_warehouse=AuditWarehouse(file_path=str(tmp_path / "warehouse.jsonl")),
    )


def _issue_s3(runtime: DefenseRuntime, *, session_id: str, trace_id: str) -> str:
    runtime.session_state.update_by_role(
        "orchestrator",
        session_id,
        {"flowState": "S2", "lastDecisionAction": "NONE"},
        is_allow=True,
    )
    out = runtime.issue_challenge(
        session_id=session_id,
        trace_id=trace_id,
        requested_flow_state=None,
        client_viewport={"w": 1200, "h": 800},
    )
    return out.challenge_id


def test_verify_unavailable_defaults_to_fail_close(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TM_S3_VERIFY_UNAVAILABLE_MODE", raising=False)
    runtime = _runtime(tmp_path)
    session_id = "sess-unavailable-close-1"
    challenge_id = _issue_s3(runtime, session_id=session_id, trace_id="trace-issue-close")

    original_get = runtime.redis.get

    def _broken_get(name: str):
        if name.startswith(CHALLENGE_KEY_PREFIX):
            raise RuntimeError("redis unavailable")
        return original_get(name)

    runtime.redis.get = _broken_get  # type: ignore[method-assign]

    result = runtime.verify_challenge(
        session_id=session_id,
        trace_id="trace-verify-close",
        challenge_id=challenge_id,
        client_answer={"catch_triggered": True},
    )
    assert result.reason_code == "CHALLENGE_VERIFY_UNAVAILABLE"
    assert result.http_status == 503


def test_verify_unavailable_allows_fail_open_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TM_S3_VERIFY_UNAVAILABLE_MODE", "fail_open")
    runtime = _runtime(tmp_path)
    session_id = "sess-unavailable-open-1"
    challenge_id = _issue_s3(runtime, session_id=session_id, trace_id="trace-issue-open")

    original_get = runtime.redis.get

    def _broken_get(name: str):
        if name.startswith(CHALLENGE_KEY_PREFIX):
            raise RuntimeError("redis unavailable")
        return original_get(name)

    runtime.redis.get = _broken_get  # type: ignore[method-assign]

    result = runtime.verify_challenge(
        session_id=session_id,
        trace_id="trace-verify-open",
        challenge_id=challenge_id,
        client_answer={"catch_triggered": True},
    )
    assert result.reason_code == "CHALLENGE_VERIFY_UNAVAILABLE"
    assert result.http_status == 200


def test_check_route_preserves_correlation_header_and_audit_meta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TM_TEST_MODE_ENABLED", "true")
    runtime = _runtime(tmp_path)
    app = create_app(runtime=runtime, include_admin=False)
    client = TestClient(app)

    resp = client.post(
        "/check/evaluate",
        headers={
            "X-Session-Id": "sess-meta-1",
            "X-Trace-Id": "trace-meta-1",
            "X-Correlation-Id": "corr-123",
            "X-TM-TestMode": "true",
        },
        json={
            "upstreamPath": "/api/availability",
            "upstreamMethod": "GET",
            "flowState": "S1",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("x-correlation-id") == "corr-123"

    audit_file = tmp_path / "decision_audit.jsonl"
    lines = [ln for ln in audit_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines
    rows = [json.loads(ln) for ln in lines]
    hit = [row for row in rows if row.get("trace_id") == "trace-meta-1"]
    assert hit
    assert any(row.get("correlation_id") == "corr-123" for row in hit)
    assert any(row.get("raw_payload", {}).get("request_meta", {}).get("correlation_id") == "corr-123" for row in hit)
    assert any(row.get("raw_payload", {}).get("request_meta", {}).get("test_mode") is True for row in hit)


def test_tm_test_mode_header_rejected_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TM_TEST_MODE_ENABLED", "false")
    runtime = _runtime(tmp_path)
    app = create_app(runtime=runtime, include_admin=False)
    client = TestClient(app)

    resp = client.post(
        "/check/evaluate",
        headers={
            "X-Session-Id": "sess-meta-2",
            "X-Trace-Id": "trace-meta-2",
            "X-TM-TestMode": "true",
        },
        json={
            "upstreamPath": "/api/availability",
            "upstreamMethod": "GET",
            "flowState": "S1",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("reasonCode") == "VALIDATION_ERROR"


def test_block_deny_response_contains_terminal_reason(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.block_state.set_block(
        session_id="sess-blocked-1",
        blocked_at_ms=1710000000000,
        policy_version="v2.0.0-mvp",
    )
    app = create_app(runtime=runtime, include_admin=False)
    client = TestClient(app)

    resp = client.post(
        "/check/evaluate",
        headers={
            "X-Session-Id": "sess-blocked-1",
            "X-Trace-Id": "trace-blocked-1",
        },
        json={
            "upstreamPath": "/api/availability",
            "upstreamMethod": "GET",
            "flowState": "S1",
        },
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body.get("reasonCode") == "BLOCKED"
    assert body.get("terminalReason") == "BLOCKED"
