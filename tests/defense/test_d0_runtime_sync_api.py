from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from traffic_master_ai.defense.d0_mvp.api.app import create_app
from traffic_master_ai.defense.d0_mvp.api.runtime import DefenseRuntime
from traffic_master_ai.defense.d0_mvp.observability.audit_logger import AuditLogger
from traffic_master_ai.defense.d0_mvp.observability.warehouse import AuditWarehouse
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis


def _runtime(tmp_path: Path) -> DefenseRuntime:
    return DefenseRuntime(
        redis=InMemoryRedis(),
        audit_logger=AuditLogger(file_path=str(tmp_path / "decision_audit.jsonl")),
        audit_warehouse=AuditWarehouse(file_path=str(tmp_path / "warehouse.jsonl")),
    )


def test_runtime_vqa_mark_sets_s3_passed_and_resets_fail_count(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    session_id = "sess-runtime-sync-pass-1"
    runtime.session_state.update_by_role(
        "analyzer",
        session_id,
        {"challengeFailCount": 2},
        is_allow=False,
    )

    app = create_app(runtime=runtime, include_admin=False)
    client = TestClient(app)
    resp = client.post(
        "/runtime/vqa/mark",
        json={
            "session_id": session_id,
            "vqa_passed": True,
            "flow_state": "S4",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["vqa_passed"] is True
    assert body["flow_state"] == "S4"

    state = runtime.session_state.get_or_create(session_id)
    assert state.s3_passed is True
    assert state.flow_state.value == "S4"
    assert state.challenge_fail_count == 0


def test_runtime_vqa_mark_rejects_invalid_vqa_passed_type(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    app = create_app(runtime=runtime, include_admin=False)
    client = TestClient(app)

    resp = client.post(
        "/runtime/vqa/mark",
        json={
            "session_id": "sess-runtime-sync-invalid-1",
            "vqa_passed": "not-bool",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("reasonCode") == "VALIDATION_ERROR"
