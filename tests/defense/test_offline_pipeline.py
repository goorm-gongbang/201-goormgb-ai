from __future__ import annotations

import json
from pathlib import Path

from traffic_master_ai.defense.offline.pipeline import (
    OfflineJudgeConfig,
    aggregate_sessions,
    run_offline_batch,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _bot_session_rows(session_id: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for _ in range(4):
        rows.append(
            {
                "event_type": "EVALUATE",
                "session_id": session_id,
                "allow": False,
                "action": "GATE",
                "risk_score": 0.78,
                "rule_hits": ["R1_REPETITIVE_PATTERN_T2"],
                "method": "POST",
                "path": "/seat/matches/687/seat-holds",
            }
        )
    rows.append(
        {
            "event_type": "CHALLENGE_VERIFIED",
            "session_id": session_id,
            "payload": {"result": "FAILED"},
        }
    )
    rows.append(
        {
            "event_type": "CHALLENGE_VERIFIED",
            "session_id": session_id,
            "payload": {"result": "FAILED"},
        }
    )
    return rows


def test_offline_batch_skips_when_log_count_below_threshold(tmp_path: Path) -> None:
    decision_log = tmp_path / "decision.jsonl"
    _write_jsonl(
        decision_log,
        [
            {
                "event_type": "EVALUATE",
                "session_id": "sess-1",
                "allow": True,
                "action": "NONE",
                "risk_score": 0.05,
                "rule_hits": [],
                "method": "GET",
                "path": "/seat/matches/687/seat-groups",
            }
        ],
    )
    result = run_offline_batch(
        decision_audit_path=str(decision_log),
        min_log_count=10,
        min_decisions_per_session=1,
        candidate_limit=10,
        cfg=OfflineJudgeConfig(mode="mock"),
    )
    assert result["status"] == "SKIPPED"
    assert result["reason"] == "NOT_ENOUGH_LOGS"
    assert result["candidate_count"] == 0


def test_offline_batch_mock_outputs_true_bot_and_patch_candidates(tmp_path: Path) -> None:
    decision_log = tmp_path / "decision.jsonl"
    rows = _bot_session_rows("sess-bot-1")
    rows.extend(_bot_session_rows("sess-bot-2"))
    rows.extend(_bot_session_rows("sess-bot-3"))
    _write_jsonl(decision_log, rows)

    result = run_offline_batch(
        decision_audit_path=str(decision_log),
        min_log_count=1,
        min_decisions_per_session=3,
        candidate_limit=10,
        cfg=OfflineJudgeConfig(mode="mock"),
    )
    assert result["status"] == "OK"
    assert result["candidate_count"] == 3
    assert len(result["results"]) == 3
    assert all(row["verdict"] == "TRUE_BOT" for row in result["results"])
    assert any(
        patch.get("id") == "suggest-tighten-t2-throttle"
        for patch in result["patches"]
    )


def test_session_aggregate_compact_vector_shape(tmp_path: Path) -> None:
    decision_log = tmp_path / "decision.jsonl"
    rows = _bot_session_rows("sess-bot-compact")
    _write_jsonl(decision_log, rows)
    records = [json.loads(line) for line in decision_log.read_text(encoding="utf-8").splitlines()]
    aggs = aggregate_sessions(records)
    vector = aggs["sess-bot-compact"].to_session_aggregate_vector(top_k=2)
    assert set(vector.keys()) == {
        "sid",
        "dc",
        "deny",
        "allow",
        "cf",
        "cfb",
        "cp",
        "gate",
        "thr",
        "blk",
        "r_avg",
        "hits",
        "paths",
        "mth",
    }
    assert vector["sid"] == "sess-bot-compact"
    assert isinstance(vector["hits"], list)
    assert len(vector["hits"]) <= 2


def test_offline_batch_triage_auto_bot_and_human_without_llm_key(tmp_path: Path) -> None:
    decision_log = tmp_path / "decision.jsonl"
    rows = _bot_session_rows("sess-bot-1")
    rows.extend(
        [
            {
                "event_type": "EVALUATE",
                "session_id": "sess-human-1",
                "allow": True,
                "action": "NONE",
                "risk_score": 0.05,
                "rule_hits": [],
                "method": "GET",
                "path": "/seat/matches/687/seat-groups",
            },
            {
                "event_type": "EVALUATE",
                "session_id": "sess-human-1",
                "allow": True,
                "action": "NONE",
                "risk_score": 0.1,
                "rule_hits": [],
                "method": "GET",
                "path": "/seat/matches/687/sections/A1/blocks",
            },
            {
                "event_type": "CHALLENGE_VERIFIED",
                "session_id": "sess-human-1",
                "payload": {"result": "PASSED"},
            },
        ]
    )
    _write_jsonl(decision_log, rows)

    result = run_offline_batch(
        decision_audit_path=str(decision_log),
        min_log_count=0,
        min_decisions_per_session=1,
        candidate_limit=10,
        cfg=OfflineJudgeConfig(
            mode="openai_compatible",
            api_key="",
            triage_enabled=True,
        ),
    )
    assert result["status"] == "OK"
    assert result["llm_candidate_count"] == 0
    assert result["triage"]["auto_bot_count"] >= 1
    assert result["triage"]["auto_human_count"] >= 1
    by_sid = {row["session_id"]: row for row in result["results"]}
    assert by_sid["sess-bot-1"]["verdict"] == "TRUE_BOT"
    assert by_sid["sess-human-1"]["verdict"] == "HUMAN"


def test_offline_batch_triage_routes_ambiguous_to_llm(tmp_path: Path) -> None:
    decision_log = tmp_path / "decision.jsonl"
    _write_jsonl(
        decision_log,
        [
            {
                "event_type": "EVALUATE",
                "session_id": "sess-ambiguous-1",
                "allow": False,
                "action": "GATE",
                "risk_score": 0.41,
                "rule_hits": [],
                "method": "POST",
                "path": "/seat/matches/687/seat-holds",
            },
            {
                "event_type": "EVALUATE",
                "session_id": "sess-ambiguous-1",
                "allow": True,
                "action": "THROTTLE",
                "risk_score": 0.46,
                "rule_hits": [],
                "method": "GET",
                "path": "/seat/matches/687/recommendations/blocks",
            },
            {
                "event_type": "CHALLENGE_VERIFIED",
                "session_id": "sess-ambiguous-1",
                "payload": {"result": "PASSED"},
            },
        ],
    )
    result = run_offline_batch(
        decision_audit_path=str(decision_log),
        min_log_count=0,
        min_decisions_per_session=1,
        candidate_limit=10,
        cfg=OfflineJudgeConfig(
            mode="openai_compatible",
            api_key="",
            triage_enabled=True,
        ),
    )
    assert result["status"] == "OK"
    assert result["llm_candidate_count"] == 1
    assert result["triage"]["llm_count"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["verdict"] == "UNAVAILABLE"
