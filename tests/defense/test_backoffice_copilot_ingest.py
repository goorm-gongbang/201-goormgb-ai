from __future__ import annotations

import json

from traffic_master_ai.defense.backoffice_copilot.core.models import DefenseAuditEventRow
from traffic_master_ai.defense.backoffice_copilot.core.state import PostReviewRunInput
from traffic_master_ai.defense.backoffice_copilot.ingest import (
    classify_event_type,
    interpret_event,
    load_analysis_input,
    map_event_semantics,
    parse_canonical_defense_audit_event_row,
    parse_defense_audit_event_row,
)


def test_load_analysis_input_applies_window_before_limit(tmp_path) -> None:
    jsonl_path = tmp_path / "defense_audit_events.jsonl"
    rows = [
        {
            "tsMs": 90,
            "traceId": "trace-0",
            "sessionId": "sess-0",
            "eventType": "DEF_GUARD_SCORED",
            "flowState": "F1",
        },
        {
            "tsMs": 100,
            "traceId": "trace-1",
            "sessionId": "sess-1",
            "eventType": "DEF_GUARD_SCORED",
            "flowState": "F2",
            "serverDecision": {"riskTier": "T1", "action": "NONE"},
        },
        {
            "tsMs": 110,
            "traceId": "trace-2",
            "sessionId": "sess-2",
            "eventType": "DEF_ORCH_EXECUTED",
            "flowState": "F3",
            "serverDecision": {"riskTier": "T2", "action": "THROTTLE"},
        },
        {
            "tsMs": 120,
            "traceId": "trace-3",
            "sessionId": "sess-3",
            "eventType": "DEF_BLOCK_ENFORCED",
            "flowState": "FX",
            "serverDecision": {"riskTier": "T3", "action": "BLOCK"},
        },
    ]
    jsonl_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    analysis_input = load_analysis_input(
        jsonl_path,
        run_input=PostReviewRunInput(
            match_id="match-1",
            window_start_ms=100,
            window_end_ms=120,
            limit=2,
            use_raw_audit_fallback=True,
        ),
    )

    assert analysis_input.raw_audit_available is True
    assert tuple(row.session_id for row in analysis_input.defense_audit_events) == (
        "sess-1",
        "sess-2",
    )
    assert tuple(row.event_type for row in analysis_input.defense_audit_events) == (
        "DEF_GUARD_SCORED",
        "DEF_ORCH_EXECUTED",
    )
    assert analysis_input.defense_audit_events[0].payload["flowState"] == "F2"
    assert not hasattr(analysis_input.defense_audit_events[0], "latest_flow_state")


def test_semantic_mapping_and_interpreter_keep_unused_events_separate() -> None:
    row = DefenseAuditEventRow(
        ts_ms=100,
        trace_id="trace-1",
        session_id="sess-1",
        event_type="S3_CHALLENGE_HALTED",
        payload={
            "flowState": "F4M",
            "result": {
                "terminalReason": "CHALLENGE_TEMPORARILY_LOCKED",
                "reasonCode": "CHALLENGE_TEMPORARILY_LOCKED",
            },
            "serverDecision": {"riskTier": "T2", "action": "THROTTLE"},
        },
    )

    semantics = map_event_semantics(row)
    interpreted = interpret_event(row)

    assert semantics.flow_state == "F4M"
    assert semantics.terminal_reason == "CHALLENGE_TEMPORARILY_LOCKED"
    assert semantics.reason_code == "CHALLENGE_TEMPORARILY_LOCKED"
    assert semantics.latest_action == "THROTTLE"
    assert semantics.latest_tier == "T2"
    assert semantics.terminal_outcome == "NOT_BLOCKED"
    assert classify_event_type("S3_CHALLENGE_HALTED") == "UNUSED"
    assert interpreted.usage == "UNUSED"


def test_semantic_mapping_finds_nested_values_inside_lists() -> None:
    row = DefenseAuditEventRow(
        ts_ms=200,
        trace_id="trace-2",
        session_id="sess-2",
        event_type="DEF_ORCH_EXECUTED",
        payload={
            "events": [
                {
                    "flowState": "F4M",
                    "result": {
                        "terminalReason": "CHALLENGE_TIMEOUT",
                        "reasonCode": "CHALLENGE_TIMEOUT",
                    },
                }
            ],
            "serverDecision": {"riskTier": "T2", "action": "THROTTLE"},
        },
    )

    semantics = map_event_semantics(row)

    assert semantics.flow_state == "F4M"
    assert semantics.terminal_reason == "CHALLENGE_TIMEOUT"
    assert semantics.reason_code == "CHALLENGE_TIMEOUT"
    assert semantics.latest_action == "THROTTLE"
    assert semantics.latest_tier == "T2"


def test_semantic_mapping_prefers_known_contract_paths_over_unrelated_nested_keys() -> None:
    row = DefenseAuditEventRow(
        ts_ms=300,
        trace_id="trace-3",
        session_id="sess-3",
        event_type="DEF_GUARD_SCORED",
        payload={
            "metadata": {"action": "IGNORE_ME", "riskTier": "T9"},
            "latestAction": "NONE",
            "serverDecision": {"action": "THROTTLE", "riskTier": "T2"},
            "result": {"reasonCode": "SAFE_CODE", "terminalReason": "SAFE_REASON"},
        },
    )

    semantics = map_event_semantics(row)

    assert semantics.latest_action == "NONE"
    assert semantics.latest_tier == "T2"
    assert semantics.reason_code == "SAFE_CODE"
    assert semantics.terminal_reason == "SAFE_REASON"


def test_loader_compatibility_read_keeps_legacy_row_support() -> None:
    row = parse_defense_audit_event_row(
        {
            "tsMs": 1710000000000,
            "traceId": "trace-legacy",
            "sessionId": "sess-legacy",
            "eventType": "DEF_GUARD_SCORED",
            "flowState": "F2",
            "serverDecision": {"riskTier": "T1", "action": "NONE"},
        }
    )

    assert row.ts_ms == 1710000000000
    assert row.trace_id == "trace-legacy"
    assert row.session_id == "sess-legacy"
    assert row.event_type == "DEF_GUARD_SCORED"
    assert row.payload["flowState"] == "F2"
    assert row.payload["serverDecision"]["riskTier"] == "T1"


def test_strict_canonical_loader_only_accepts_unified_contract() -> None:
    row = parse_canonical_defense_audit_event_row(
        {
            "ts_ms": 1710000000000,
            "session_id": "sess-canonical",
            "trace_id": "trace-canonical",
            "event_type": "DEF_ORCH_EXECUTED",
            "flow_state": "F4",
            "raw_payload": {
                "server_decision": {"risk_tier": "T2", "action": "THROTTLE"},
            },
        }
    )

    assert row.ts_ms == 1710000000000
    assert row.trace_id == "trace-canonical"
    assert row.session_id == "sess-canonical"
    assert row.event_type == "DEF_ORCH_EXECUTED"
    assert row.payload == {
        "server_decision": {"risk_tier": "T2", "action": "THROTTLE"},
    }


def test_strict_canonical_loader_rejects_legacy_shape() -> None:
    try:
        parse_canonical_defense_audit_event_row(
            {
                "tsMs": 1710000000000,
                "sessionId": "sess-legacy",
                "eventType": "DEF_ORCH_EXECUTED",
                "payload": {},
            }
        )
    except ValueError as exc:
        assert "unified snake_case contract" in str(exc)
    else:
        raise AssertionError("strict canonical loader must reject legacy rows")
