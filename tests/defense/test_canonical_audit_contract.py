from __future__ import annotations

import json

import pytest

from traffic_master_ai.defense.audit_contract import normalize_audit_row, validate_canonical_audit_row
from traffic_master_ai.defense.api.audit import DefenseDecisionAuditLogger
from traffic_master_ai.defense.api.models import EvaluateRequest, EvaluateResponse, RuntimeStateSnapshot
from traffic_master_ai.defense.d0_mvp.observability.schemas import AuditEntry


def test_defense_api_audit_logger_emits_canonical_snake_case_row(tmp_path) -> None:
    logger = DefenseDecisionAuditLogger(str(tmp_path / "decision_audit.jsonl"))

    logger.log(
        EvaluateRequest(
            session_id="sess-1",
            trace_id="trace-1",
            request_id="req-1",
            correlation_id="corr-1",
            path="/api/check",
            method="post",
            timestamp=1710000000000,
        ),
        EvaluateResponse(
            allow=False,
            session_id="sess-1",
            flow_state="F2",
            defense_tier="T2",
            action="CHALLENGE",
            reason="BOT_SIGNAL",
            rule_hits=["rule-a"],
            risk_score=0.9,
            policy_version="policy-v1",
            decision_id="decision-1",
            latency_ms=10,
        ),
        RuntimeStateSnapshot(
            flow_state="F2",
            defense_tier="T2",
            policy_version="policy-v1",
        ),
    )

    rows = [
        json.loads(line)
        for line in (tmp_path / "decision_audit.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == "sess-1"
    assert row["trace_id"] == "trace-1"
    assert row["request_id"] == "req-1"
    assert row["correlation_id"] == "corr-1"
    assert row["event_type"] == "EVALUATE"
    assert row["flow_state"] == "F2"
    assert row["risk_tier"] == "T2"
    assert row["action"] == "CHALLENGE"
    assert row["reason_code"] == "BOT_SIGNAL"
    assert row["policy_version"] == "policy-v1"
    assert row["raw_payload"]["decision_id"] == "decision-1"
    assert row["raw_payload"]["path"] == "/api/check"
    assert row["raw_payload"]["method"] == "POST"
    assert row["raw_payload"]["allow"] is False
    assert row["raw_payload"]["runtime_state"]["flow_state"] == "F2"


def test_defense_api_challenge_logger_emits_canonical_raw_payload(tmp_path) -> None:
    logger = DefenseDecisionAuditLogger(str(tmp_path / "decision_audit.jsonl"))

    logger.log_challenge_event(
        session_id="sess-2",
        challenge_id="challenge-1",
        event_type="CHALLENGE_VERIFIED",
        payload={"result": "PASS", "matchId": 42},
    )

    row = json.loads((tmp_path / "decision_audit.jsonl").read_text(encoding="utf-8").strip())

    assert row["session_id"] == "sess-2"
    assert row["challenge_id"] == "challenge-1"
    assert row["event_type"] == "CHALLENGE_VERIFIED"
    assert row["raw_payload"] == {"result": "PASS", "match_id": 42}


def test_defense_api_target_early_return_logger_emits_canonical_row(tmp_path) -> None:
    logger = DefenseDecisionAuditLogger(str(tmp_path / "decision_audit.jsonl"))

    logger.log_target_evaluate_event(
        session_id="sess-early-return",
        trace_id="trace-early-return",
        request_path="/seat/matches/687/seat-entry",
        request_method="post",
        target_event_type="SEAT_ENTRY",
        action="REQUIRE_S3",
        flow_state="F2",
        runtime_state=RuntimeStateSnapshot(
            flow_state="F1",
            policy_version="policy-v7",
            vqa_passed=False,
        ),
        reason_code="SEAT_ENTRY_VQA_REQUIRED",
        raw_payload={
            "decision_reason": "seat_entry_immediate",
            "vqa_passed": False,
        },
    )

    row = json.loads((tmp_path / "decision_audit.jsonl").read_text(encoding="utf-8").strip())

    assert row["session_id"] == "sess-early-return"
    assert row["trace_id"] == "trace-early-return"
    assert row["event_type"] == "EVALUATE"
    assert row["flow_state"] == "F2"
    assert row["action"] == "REQUIRE_S3"
    assert row["reason_code"] == "SEAT_ENTRY_VQA_REQUIRED"
    assert row["policy_version"] == "policy-v7"
    assert row["raw_payload"]["decision_source"] == "target_api_early_return"
    assert row["raw_payload"]["target_event_type"] == "SEAT_ENTRY"
    assert row["raw_payload"]["decision_reason"] == "seat_entry_immediate"
    assert row["raw_payload"]["runtime_state"]["flow_state"] == "F1"


def test_validate_canonical_audit_row_rejects_unknown_top_level_field() -> None:
    with pytest.raises(ValueError, match="unknown canonical audit top-level fields"):
        validate_canonical_audit_row(
            {
                "ts_ms": 1710000000000,
                "session_id": "sess-unknown",
                "event_type": "EVALUATE",
                "raw_payload": {},
                "unexpected": "value",
            }
        )


def test_validate_canonical_audit_row_rejects_non_object_raw_payload() -> None:
    with pytest.raises(ValueError, match="raw_payload must be an object"):
        validate_canonical_audit_row(
            {
                "ts_ms": 1710000000000,
                "session_id": "sess-bad-payload",
                "event_type": "EVALUATE",
                "raw_payload": "bad",
            }
        )


def test_normalize_audit_row_rejects_legacy_shape_when_strict_contract_is_required() -> None:
    with pytest.raises(ValueError, match="unified snake_case contract"):
        normalize_audit_row(
            {
                "tsMs": 1710000000000,
                "sessionId": "sess-legacy",
                "eventType": "DEF_ORCH_EXECUTED",
                "payload": {},
            },
            allow_legacy=False,
        )


def test_runtime_audit_entry_serializes_to_canonical_shape() -> None:
    row = AuditEntry(
        ts_ms=1710000000000,
        session_id="sess-runtime",
        event_type="DEF_ORCH_EXECUTED",
        trace_id="trace-runtime",
        flow_state="F4",
        risk_tier="T2",
        action="THROTTLE",
        reason_code="RULE_HIT",
        policy_version="policy-v9",
        raw_payload={"source": "runtime"},
    ).to_dict()

    assert set(row.keys()) == {
        "ts_ms",
        "session_id",
        "event_type",
        "trace_id",
        "flow_state",
        "risk_tier",
        "action",
        "reason_code",
        "policy_version",
        "raw_payload",
    }
    assert "tsMs" not in row
    assert "eventType" not in row
    assert row["raw_payload"] == {"source": "runtime"}
    assert validate_canonical_audit_row(row) == row
