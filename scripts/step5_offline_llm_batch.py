#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from traffic_master_ai.defense.offline.pipeline import (
    OfflineJudgeConfig,
    run_offline_batch,
    write_json,
    write_jsonl,
)


def _default_min_logs() -> int:
    raw = os.getenv("TM_OFFLINE_TRIGGER_MIN_LOGS", "100")
    try:
        return max(0, int(raw))
    except ValueError:
        return 100


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Step5-2 offline LLM batch runner. "
            "Consumes decision audit logs and emits session judgments + patch candidates."
        )
    )
    parser.add_argument("--decision-log", default="logs/defense_decision_audit.jsonl")
    parser.add_argument("--results-out", default="logs/offline_judge_results.jsonl")
    parser.add_argument("--patches-out", default="logs/offline_policy_patch_candidates.json")
    parser.add_argument("--summary-out", default="logs/offline_batch_summary.json")
    parser.add_argument("--min-log-count", type=int, default=_default_min_logs())
    parser.add_argument("--min-decisions-per-session", type=int, default=3)
    parser.add_argument("--candidate-limit", type=int, default=200)
    parser.add_argument(
        "--mode",
        choices=["mock", "openai_compatible"],
        default="mock",
        help="Offline judge mode.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "Return non-zero when run completes but has no candidates "
            "or has unavailable offline judgments."
        ),
    )
    args = parser.parse_args()

    cfg = OfflineJudgeConfig.from_env()
    cfg.mode = args.mode
    result = run_offline_batch(
        decision_audit_path=args.decision_log,
        min_log_count=args.min_log_count,
        min_decisions_per_session=args.min_decisions_per_session,
        candidate_limit=args.candidate_limit,
        cfg=cfg,
    )

    if result["status"] == "OK":
        write_jsonl(args.results_out, result["results"])
        write_json(args.patches_out, result["patches"])
    write_json(args.summary_out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.strict and result["status"] == "OK":
        candidate_count = int(result.get("candidate_count", 0))
        unavailable_count = sum(
            1 for row in result["results"] if row.get("verdict") == "UNAVAILABLE"
        )
        if candidate_count == 0 or unavailable_count > 0:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
