from __future__ import annotations

import pytest

from traffic_master_ai.defense.api.audit import DefenseDecisionAuditLogger
from traffic_master_ai.defense.d0_mvp.observability.schemas import (
    CANONICAL_AUDIT_EVENT_TYPES,
    LEGACY_API_AUDIT_EVENT_TYPES,
    OPTIMIZER_INCLUDED_AUDIT_EVENT_TYPES,
    RUNTIME_AUDIT_EVENT_TYPES,
    AuditEntry,
)


def test_canonical_audit_taxonomy_is_explicit_and_exact() -> None:
    assert LEGACY_API_AUDIT_EVENT_TYPES == frozenset(
        {
            "EVALUATE",
            "CHALLENGE_ISSUED",
            "CHALLENGE_VERIFIED",
        }
    )
    assert RUNTIME_AUDIT_EVENT_TYPES == frozenset(
        {
            "DEF_GUARD_SCORED",
            "DEF_ANALYZER_EVIDENCE_UPDATED",
            "DEF_PLAN_COMPUTED",
            "DEF_ORCH_EXECUTED",
            "DEF_INVALID_TRANSITION",
            "DEF_THROTTLE_APPLIED",
            "DEF_BLOCK_DECIDED",
            "DEF_BLOCK_ENFORCED",
            "DEFENSE_UNAVAILABLE",
            "S3_CHALLENGE_ISSUED",
            "S3_CHALLENGE_RESULT",
            "S3_CHALLENGE_HALTED",
            "TURNSTILE_TRIGGERED",
            "TURNSTILE_VERIFIED",
        }
    )
    assert CANONICAL_AUDIT_EVENT_TYPES == frozenset(
        set(LEGACY_API_AUDIT_EVENT_TYPES) | set(RUNTIME_AUDIT_EVENT_TYPES)
    )


def test_optimizer_included_event_taxonomy_is_explicit_and_runtime_only() -> None:
    assert OPTIMIZER_INCLUDED_AUDIT_EVENT_TYPES == frozenset(
        {
            "DEF_ORCH_EXECUTED",
            "DEF_THROTTLE_APPLIED",
            "DEF_BLOCK_ENFORCED",
            "S3_CHALLENGE_RESULT",
            "S3_CHALLENGE_HALTED",
            "DEF_GUARD_SCORED",
        }
    )
    assert OPTIMIZER_INCLUDED_AUDIT_EVENT_TYPES <= RUNTIME_AUDIT_EVENT_TYPES


def test_runtime_audit_entry_rejects_legacy_api_event_types() -> None:
    entry = AuditEntry(
        ts_ms=1710000000000,
        session_id="sess-runtime",
        event_type="EVALUATE",
        raw_payload={},
    )

    assert entry.validate() == ["event_type not in audit catalog: EVALUATE"]


def test_legacy_api_logger_rejects_unknown_taxonomy_event(tmp_path) -> None:
    logger = DefenseDecisionAuditLogger(str(tmp_path / "decision_audit.jsonl"))

    with pytest.raises(ValueError, match="event_type not in canonical audit taxonomy"):
        logger.log_challenge_event(
            session_id="sess-1",
            challenge_id="challenge-1",
            event_type="UNKNOWN_NEW_EVENT",
            payload={"result": "PASS"},
        )

    log_path = tmp_path / "decision_audit.jsonl"
    assert not log_path.exists() or log_path.read_text(encoding="utf-8") == ""
