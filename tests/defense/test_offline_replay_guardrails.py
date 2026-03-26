from __future__ import annotations

from traffic_master_ai.defense.offline.guardrails import GuardrailConfig, evaluate_guardrails
from traffic_master_ai.defense.offline.replay import (
    build_replay_dataset,
    evaluate_alignment,
    expected_label_from_aggregate,
)
from traffic_master_ai.defense.offline.pipeline import aggregate_sessions


def _sample_records() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    # Suspicious session
    for _ in range(3):
        rows.append(
            {
                "event_type": "EVALUATE",
                "session_id": "sess-bot-1",
                "allow": False,
                "action": "GATE",
                "risk_score": 0.81,
                "rule_hits": ["R1_REPETITIVE_PATTERN_T2"],
                "method": "POST",
                "path": "/seat/matches/687/seat-holds",
            }
        )
    rows.append(
        {
            "event_type": "CHALLENGE_VERIFIED",
            "session_id": "sess-bot-1",
            "payload": {"result": "FAILED"},
        }
    )
    rows.append(
        {
            "event_type": "CHALLENGE_VERIFIED",
            "session_id": "sess-bot-1",
            "payload": {"result": "FAILED"},
        }
    )
    # Human-like session
    for _ in range(3):
        rows.append(
            {
                "event_type": "EVALUATE",
                "session_id": "sess-human-1",
                "allow": True,
                "action": "NONE",
                "risk_score": 0.1,
                "rule_hits": [],
                "method": "GET",
                "path": "/seat/matches/687/seat-groups",
            }
        )
    rows.append(
        {
            "event_type": "CHALLENGE_VERIFIED",
            "session_id": "sess-human-1",
            "payload": {"result": "PASSED"},
        }
    )
    return rows


def test_build_replay_dataset_and_alignment() -> None:
    built = build_replay_dataset(
        _sample_records(),
        min_decisions_per_session=2,
        max_sessions=10,
    )
    assert built["selected_session_count"] == 2
    manifest = built["manifest"]
    by_session = {row["session_id"]: row for row in manifest}
    assert by_session["sess-bot-1"]["expected_label"] == "SUSPICIOUS"
    assert by_session["sess-human-1"]["expected_label"] == "HUMAN"

    alignment = evaluate_alignment(
        manifest_entries=manifest,
        offline_results=[
            {"session_id": "sess-bot-1", "verdict": "TRUE_BOT"},
            {"session_id": "sess-human-1", "verdict": "HUMAN"},
        ],
    )
    assert alignment["evaluable_session_count"] == 2
    assert alignment["matched_session_count"] == 2
    assert alignment["alignment_rate"] == 1.0


def test_guardrail_requires_manual_approval_token() -> None:
    cfg = GuardrailConfig(
        min_evaluable_sessions=1,
        min_alignment_rate=0.5,
        max_unavailable_ratio=1.0,
        max_patch_delta_ratio=0.5,
        require_manual_approval=False,
    )
    summary = {
        "status": "OK",
        "alignment": {
            "evaluable_session_count": 2,
            "alignment_rate": 1.0,
            "unavailable_ratio": 0.0,
        },
    }
    decision = evaluate_guardrails(
        cfg=cfg,
        batch_summary=summary,
        patches=[
            {
                "id": "p1",
                "target": "TM_T2_THROTTLE_MS",
                "current": 1000,
                "proposed": 1200,
                "manual_review_required": True,
            }
        ],
        approval_token=None,
    )
    assert decision["approved"] is True
    assert decision["decision"] == "APPLY_READY"


def test_queue_gate_denies_with_pass_is_labeled_human() -> None:
    records = [
        {
            "event_type": "EVALUATE",
            "session_id": "sess-qgate-human",
            "allow": False,
            "action": "GATE",
            "risk_score": 0.4,
            "rule_hits": ["S3_QUEUE_EXIT_VQA_REQUIRED"],
            "method": "POST",
            "path": "/seat/matches/687/seat-holds",
        },
        {
            "event_type": "CHALLENGE_VERIFIED",
            "session_id": "sess-qgate-human",
            "payload": {"result": "PASSED"},
        },
    ]
    aggs = aggregate_sessions(records)
    assert expected_label_from_aggregate(aggs["sess-qgate-human"]) == "HUMAN"


def test_replay_builder_can_force_label_mix() -> None:
    records = _sample_records()
    # Add one uncertain-like session.
    records.extend(
        [
            {
                "event_type": "EVALUATE",
                "session_id": "sess-uncertain-1",
                "allow": False,
                "action": "THROTTLE",
                "risk_score": 0.45,
                "rule_hits": [],
                "method": "GET",
                "path": "/seat/matches/687/recommendations/blocks",
            }
        ]
    )
    built = build_replay_dataset(
        records,
        min_decisions_per_session=1,
        max_sessions=10,
        min_suspicious_sessions=1,
        min_human_sessions=1,
        min_uncertain_sessions=1,
    )
    dist = built["selected_label_distribution"]
    assert dist["SUSPICIOUS"] >= 1
    assert dist["HUMAN"] >= 1
    assert dist["UNCERTAIN"] >= 1
