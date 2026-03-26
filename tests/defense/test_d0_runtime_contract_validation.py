from __future__ import annotations

from pathlib import Path

import pytest

from traffic_master_ai.defense.d0_mvp.api.runtime import (
    DefenseRuntime,
    RuntimeAPIError,
    build_check_request,
    build_evaluate_request,
)
from traffic_master_ai.defense.d0_mvp.core.enums import FlowState
from traffic_master_ai.defense.d0_mvp.observability.audit_logger import AuditLogger
from traffic_master_ai.defense.d0_mvp.observability.warehouse import AuditWarehouse
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis


def _runtime(tmp_path: Path) -> DefenseRuntime:
    return DefenseRuntime(
        redis=InMemoryRedis(),
        audit_logger=AuditLogger(file_path=str(tmp_path / "decision_audit.jsonl")),
        audit_warehouse=AuditWarehouse(file_path=str(tmp_path / "warehouse.jsonl")),
    )


def _issue_s3_challenge(runtime: DefenseRuntime, session_id: str, trace_id: str) -> str:
    runtime.session_state.update_by_role(
        "orchestrator",
        session_id,
        {"flowState": FlowState.S2.value, "lastDecisionAction": "NONE"},
        is_allow=True,
    )
    issued = runtime.issue_challenge(
        session_id=session_id,
        trace_id=trace_id,
        requested_flow_state=FlowState.S3,
        client_viewport={"w": 1200, "h": 800},
    )
    return issued.challenge_id


def test_build_check_request_requires_flow_state() -> None:
    with pytest.raises(ValueError, match="flowState is required"):
        build_check_request(
            session_id="sess-check-1",
            trace_id="trace-check-1",
            body={
                "upstreamPath": "/seat/matches/687/seat-groups",
                "upstreamMethod": "GET",
            },
        )


def test_build_evaluate_request_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="event.tsMs must be int"):
        build_evaluate_request(
            session_id="sess-eval-1",
            trace_id="trace-eval-1",
            body={
                "event": {
                    "eventType": "API_CALL_OBS",
                    "flowState": "S2",
                    "requestPath": "/seat/matches/687/seat-groups",
                    "requestMethod": "GET",
                },
                "context": {
                    "policyVersion": "v2.0.0-mvp",
                },
            },
        )

    with pytest.raises(ValueError, match="event.flowState is required"):
        build_evaluate_request(
            session_id="sess-eval-1",
            trace_id="trace-eval-1",
            body={
                "event": {
                    "eventType": "API_CALL_OBS",
                    "tsMs": 1710000000000,
                    "requestPath": "/seat/matches/687/seat-groups",
                    "requestMethod": "GET",
                },
                "context": {
                    "policyVersion": "v2.0.0-mvp",
                },
            },
        )


def test_build_evaluate_request_rejects_non_object_context_fields() -> None:
    with pytest.raises(ValueError, match="context.features must be object"):
        build_evaluate_request(
            session_id="sess-eval-2",
            trace_id="trace-eval-2",
            body={
                "event": {
                    "eventType": "API_CALL_OBS",
                    "tsMs": 1710000000001,
                    "flowState": "S2",
                    "requestPath": "/seat/matches/687/seat-groups",
                    "requestMethod": "GET",
                },
                "context": {
                    "policyVersion": "v2.0.0-mvp",
                    "features": [1, 2, 3],
                },
            },
        )


def test_runtime_rejects_event_flow_state_mismatch(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    req = build_evaluate_request(
        session_id="sess-flow-1",
        trace_id="trace-flow-1",
        body={
            "event": {
                "eventType": "S3_RESULT",
                "tsMs": 1710000001000,
                "flowState": "S4",
                "s3Result": "PASS",
            },
            "context": {
                "policyVersion": "v2.0.0-mvp",
                "features": {
                    "tremorStdDev": 0.5,
                },
            },
        },
    )

    with pytest.raises(ValueError, match="not allowed"):
        runtime.evaluate(req)


def test_verify_challenge_forwards_s3_feature_summary_to_evaluate(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    session_id = "sess-s3-feature-1"
    challenge_id = _issue_s3_challenge(runtime, session_id=session_id, trace_id="trace-issue-1")

    captured: dict[str, object] = {}
    original_evaluate = runtime.evaluate

    def _spy_evaluate(request):
        captured["features"] = request.context.features
        return original_evaluate(request)

    runtime.evaluate = _spy_evaluate  # type: ignore[method-assign]

    runtime.verify_challenge(
        session_id=session_id,
        trace_id="trace-verify-1",
        challenge_id=challenge_id,
        client_answer={
            "catch_ts_ms": 1710000001200,
            "glove_pos_norm": {"x": 0.45, "y": 0.88},
            "catch_triggered": True,
            "features": {
                "tremorStdDev": 1.2,
                "linearityRatio": 0.99,
                "avgVelocity": 850.5,
                "dwellTime": 120.0,
                "pathRatio": 1.01,
            },
        },
    )

    assert captured["features"] == {
        "tremorStdDev": 1.2,
        "linearityRatio": 0.99,
        "avgVelocity": 850.5,
        "dwellTime": 120.0,
        "pathRatio": 1.01,
    }


def test_verify_challenge_rejects_invalid_feature_types(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    session_id = "sess-s3-feature-2"
    challenge_id = _issue_s3_challenge(runtime, session_id=session_id, trace_id="trace-issue-2")

    with pytest.raises(RuntimeAPIError) as exc_info:
        runtime.verify_challenge(
            session_id=session_id,
            trace_id="trace-verify-2",
            challenge_id=challenge_id,
            client_answer={
                "catch_ts_ms": 1710000001300,
                "glove_pos_norm": {"x": 0.5, "y": 0.7},
                "catch_triggered": True,
                "features": {
                    "tremorStdDev": "bad-type",
                },
            },
        )

    err = exc_info.value
    assert err.status_code == 400
    assert err.reason_code == "VALIDATION_ERROR"
