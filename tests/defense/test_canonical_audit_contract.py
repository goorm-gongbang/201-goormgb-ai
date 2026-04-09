from __future__ import annotations

import json

from traffic_master_ai.defense.api.audit import DefenseDecisionAuditLogger
from traffic_master_ai.defense.api.models import EvaluateRequest, EvaluateResponse, RuntimeStateSnapshot


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
            flow_state="S3",
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
            flow_state="S3",
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
    assert row["flow_state"] == "S3"
    assert row["risk_tier"] == "T2"
    assert row["action"] == "CHALLENGE"
    assert row["reason_code"] == "BOT_SIGNAL"
    assert row["policy_version"] == "policy-v1"
    assert row["raw_payload"]["decision_id"] == "decision-1"
    assert row["raw_payload"]["path"] == "/api/check"
    assert row["raw_payload"]["method"] == "POST"
    assert row["raw_payload"]["allow"] is False
    assert row["raw_payload"]["runtime_state"]["flow_state"] == "S3"


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
