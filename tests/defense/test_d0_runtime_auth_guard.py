from __future__ import annotations

from pathlib import Path

from traffic_master_ai.defense.auth_guard import BlockUserResult
from traffic_master_ai.defense.d0_mvp.api.runtime import (
    DefenseRuntime,
    build_check_request,
    build_evaluate_request,
)
from traffic_master_ai.defense.d0_mvp.observability.audit_logger import AuditLogger
from traffic_master_ai.defense.d0_mvp.observability.warehouse import AuditWarehouse
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis


class RecordingBlocker:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def block_user(
        self,
        *,
        user_id: str,
        session_id: str,
        trace_id: str,
        trigger: str,
    ) -> BlockUserResult:
        self.calls.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "trace_id": trace_id,
                "trigger": trigger,
            }
        )
        return BlockUserResult(outcome="blocked", http_status=200)


def _runtime(tmp_path: Path, blocker: RecordingBlocker) -> DefenseRuntime:
    return DefenseRuntime(
        redis=InMemoryRedis(),
        audit_logger=AuditLogger(file_path=str(tmp_path / "decision_audit.jsonl")),
        audit_warehouse=AuditWarehouse(file_path=str(tmp_path / "warehouse.jsonl")),
        user_blocker=blocker,
    )


def test_build_requests_capture_user_id() -> None:
    eval_request = build_evaluate_request(
        session_id="sess-eval-1",
        trace_id="trace-eval-1",
        body={
            "event": {
                "eventType": "API_CALL_OBS",
                "tsMs": 1710000000000,
                "flowState": "S1",
                "requestPath": "/api/availability",
                "requestMethod": "GET",
            },
            "context": {
                "policyVersion": "v2.0.0-mvp",
                "userId": "42",
            },
        },
    )
    check_request = build_check_request(
        session_id="sess-check-1",
        trace_id="trace-check-1",
        body={
            "upstreamPath": "/api/availability",
            "upstreamMethod": "GET",
            "flowState": "S0",
            "userId": "99",
        },
    )

    assert eval_request.user_id == "42"
    assert check_request.user_id == "99"


def test_runtime_persisted_block_syncs_to_auth_guard(tmp_path: Path) -> None:
    blocker = RecordingBlocker()
    runtime = _runtime(tmp_path, blocker)
    runtime.block_state.set_block(
        session_id="sess-blocked-1",
        blocked_at_ms=1710000000000,
        policy_version="v2.0.0-mvp",
    )
    req = build_evaluate_request(
        session_id="sess-blocked-1",
        trace_id="trace-blocked-1",
        body={
            "event": {
                "eventType": "API_CALL_OBS",
                "tsMs": 1710000000100,
                "flowState": "S1",
                "requestPath": "/api/availability",
                "requestMethod": "GET",
            },
            "context": {
                "policyVersion": "v2.0.0-mvp",
                "userId": "42",
            },
        },
    )

    out = runtime.evaluate(req)

    assert out.orchestrator_result.decision.action.value == "BLOCK"
    assert blocker.calls == [
        {
            "user_id": "42",
            "session_id": "sess-blocked-1",
            "trace_id": "trace-blocked-1",
            "trigger": "d0_runtime_persisted_block",
        }
    ]
