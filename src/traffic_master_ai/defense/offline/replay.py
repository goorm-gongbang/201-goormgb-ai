"""Replay dataset builder + batch alignment helpers for offline defense analysis."""

from __future__ import annotations

from typing import Any, Literal

from .pipeline import SessionAggregate, aggregate_sessions

ExpectedLabel = Literal["SUSPICIOUS", "HUMAN", "UNCERTAIN"]
PredictedLabel = Literal["SUSPICIOUS", "HUMAN", "UNCERTAIN", "UNAVAILABLE"]


def expected_label_from_aggregate(agg: SessionAggregate) -> ExpectedLabel:
    repetitive_t2 = agg.rule_hits.get("R1_REPETITIVE_PATTERN_T2", 0)
    suspicious_hit = (
        agg.block_count > 0
        or agg.challenge_verified_block_count > 0
        or agg.challenge_verified_fail_count >= 2
        or repetitive_t2 > 0
        or agg.avg_risk_score >= 0.65
    )
    if suspicious_hit:
        return "SUSPICIOUS"

    likely_human_hit = (
        agg.deny_count == 0
        and agg.challenge_verified_pass_count > 0
        and agg.avg_risk_score <= 0.25
    )
    if likely_human_hit:
        return "HUMAN"

    # Mandatory queue-gate VQA introduces deny counts before pass.
    # Treat this pattern as human-like when pass exists and no hard suspicious signal exists.
    queue_gate_human_hit = (
        agg.challenge_verified_pass_count > 0
        and agg.challenge_verified_fail_count == 0
        and agg.challenge_verified_block_count == 0
        and agg.block_count == 0
        and _has_only_queue_gate_rule_hits(agg)
        and agg.avg_risk_score <= 0.55
    )
    if queue_gate_human_hit:
        return "HUMAN"
    return "UNCERTAIN"


def build_replay_dataset(
    records: list[dict[str, Any]],
    *,
    min_decisions_per_session: int,
    max_sessions: int,
    min_suspicious_sessions: int = 0,
    min_human_sessions: int = 0,
    min_uncertain_sessions: int = 0,
) -> dict[str, Any]:
    aggregates = aggregate_sessions(records)
    candidates = [
        agg
        for agg in aggregates.values()
        if agg.decision_count >= max(1, min_decisions_per_session)
    ]
    by_label: dict[ExpectedLabel, list[SessionAggregate]] = {
        "SUSPICIOUS": [],
        "HUMAN": [],
        "UNCERTAIN": [],
    }
    for item in candidates:
        by_label[expected_label_from_aggregate(item)].append(item)

    for items in by_label.values():
        items.sort(
            key=lambda agg: (
                agg.decision_count,
                agg.deny_count,
                agg.avg_risk_score,
                agg.challenge_verified_pass_count,
                agg.challenge_verified_fail_count,
            ),
            reverse=True,
        )

    selected: list[SessionAggregate] = []
    selected_ids: set[str] = set()

    def _take(label: ExpectedLabel, count: int) -> None:
        if count <= 0:
            return
        for agg in by_label[label]:
            if len(selected) >= max(1, max_sessions):
                return
            if agg.session_id in selected_ids:
                continue
            selected.append(agg)
            selected_ids.add(agg.session_id)
            if count == 1:
                return
            count -= 1

    _take("SUSPICIOUS", min_suspicious_sessions)
    _take("HUMAN", min_human_sessions)
    _take("UNCERTAIN", min_uncertain_sessions)

    all_sorted = sorted(
        candidates,
        key=lambda item: (
            item.decision_count,
            item.deny_count,
            item.avg_risk_score,
            item.challenge_verified_pass_count,
            item.challenge_verified_fail_count,
        ),
        reverse=True,
    )
    for agg in all_sorted:
        if len(selected) >= max(1, max_sessions):
            break
        if agg.session_id in selected_ids:
            continue
        selected.append(agg)
        selected_ids.add(agg.session_id)

    selected_sessions = {item.session_id for item in selected}

    replay_records = [rec for rec in records if str(rec.get("session_id") or "") in selected_sessions]
    manifest_entries: list[dict[str, Any]] = []
    selected_label_distribution: dict[str, int] = {"SUSPICIOUS": 0, "HUMAN": 0, "UNCERTAIN": 0}
    for item in selected:
        expected_label = expected_label_from_aggregate(item)
        selected_label_distribution[expected_label] = (
            selected_label_distribution.get(expected_label, 0) + 1
        )
        manifest_entries.append(
            {
                "session_id": item.session_id,
                "expected_label": expected_label,
                "decision_count": item.decision_count,
                "deny_count": item.deny_count,
                "allow_count": item.allow_count,
                "challenge_verified_fail_count": item.challenge_verified_fail_count,
                "challenge_verified_pass_count": item.challenge_verified_pass_count,
                "challenge_verified_block_count": item.challenge_verified_block_count,
                "avg_risk_score": round(item.avg_risk_score, 4),
                "rule_hits": item.rule_hits,
            }
        )

    return {
        "record_count": len(records),
        "session_count": len(aggregates),
        "selected_session_count": len(selected),
        "replay_record_count": len(replay_records),
        "selected_label_distribution": selected_label_distribution,
        "manifest": manifest_entries,
        "replay_records": replay_records,
    }


def _has_only_queue_gate_rule_hits(agg: SessionAggregate) -> bool:
    if not agg.rule_hits:
        return False
    allowed = {"S3_QUEUE_EXIT_VQA_REQUIRED"}
    return all(key in allowed for key in agg.rule_hits.keys())


def map_verdict_to_predicted_label(verdict: str) -> PredictedLabel:
    key = verdict.upper().strip()
    if key == "TRUE_BOT":
        return "SUSPICIOUS"
    if key == "HUMAN":
        return "HUMAN"
    if key == "UNAVAILABLE":
        return "UNAVAILABLE"
    return "UNCERTAIN"


def evaluate_alignment(
    *,
    manifest_entries: list[dict[str, Any]],
    offline_results: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_by_session: dict[str, ExpectedLabel] = {}
    for item in manifest_entries:
        session_id = str(item.get("session_id") or "")
        expected = str(item.get("expected_label") or "UNCERTAIN").upper()
        if not session_id:
            continue
        if expected not in {"SUSPICIOUS", "HUMAN", "UNCERTAIN"}:
            expected = "UNCERTAIN"
        expected_by_session[session_id] = expected  # type: ignore[assignment]

    predicted_by_session: dict[str, PredictedLabel] = {}
    for row in offline_results:
        session_id = str(row.get("session_id") or "")
        if not session_id:
            continue
        predicted_by_session[session_id] = map_verdict_to_predicted_label(
            str(row.get("verdict") or "")
        )

    total_manifest = len(expected_by_session)
    total_predicted = len(predicted_by_session)
    matched_sessions = 0
    evaluable_sessions = 0
    unavailable_count = 0
    missing_prediction_count = 0

    for session_id, expected in expected_by_session.items():
        predicted = predicted_by_session.get(session_id)
        if predicted is None:
            missing_prediction_count += 1
            continue
        if predicted == "UNAVAILABLE":
            unavailable_count += 1
            continue
        if expected in {"SUSPICIOUS", "HUMAN"}:
            evaluable_sessions += 1
            if predicted == expected:
                matched_sessions += 1

    coverage = total_predicted / total_manifest if total_manifest else 0.0
    alignment_rate = matched_sessions / evaluable_sessions if evaluable_sessions else 0.0
    unavailable_ratio = unavailable_count / total_predicted if total_predicted else 0.0
    return {
        "manifest_session_count": total_manifest,
        "predicted_session_count": total_predicted,
        "evaluable_session_count": evaluable_sessions,
        "matched_session_count": matched_sessions,
        "missing_prediction_count": missing_prediction_count,
        "unavailable_count": unavailable_count,
        "coverage": round(coverage, 4),
        "alignment_rate": round(alignment_rate, 4),
        "unavailable_ratio": round(unavailable_ratio, 4),
    }
