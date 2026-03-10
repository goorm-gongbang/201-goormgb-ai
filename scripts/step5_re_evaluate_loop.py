#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from traffic_master_ai.defense.offline.guardrails import GuardrailConfig, evaluate_guardrails
from traffic_master_ai.defense.offline.pipeline import (
    OfflineJudgeConfig,
    load_decision_audit,
    run_offline_batch,
    write_json,
    write_jsonl,
)
from traffic_master_ai.defense.offline.replay import build_replay_dataset, evaluate_alignment


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Step5 re-evaluation loop: replay build -> offline batch evaluate -> guardrails."
        )
    )
    parser.add_argument("--decision-log", default="logs/defense_decision_audit.jsonl")
    parser.add_argument("--mode", choices=["mock", "openai_compatible"], default="openai_compatible")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--candidate-limit", type=int, default=500)
    parser.add_argument("--min-decisions-per-session", type=int, default=1)
    parser.add_argument("--max-sessions", type=int, default=200)
    parser.add_argument("--min-suspicious-sessions", type=int, default=1)
    parser.add_argument("--min-human-sessions", type=int, default=1)
    parser.add_argument("--min-uncertain-sessions", type=int, default=0)
    parser.add_argument("--output-dir", default="logs/step5_reval")
    parser.add_argument("--approval-token", default=None)
    parser.add_argument("--strict", action="store_true", default=False)
    args = parser.parse_args()

    records = load_decision_audit(args.decision_log)
    out_dir = Path(args.output_dir)
    _mkdir(out_dir)

    rounds = max(1, int(args.rounds))
    loop_rows: list[dict[str, Any]] = []
    last_guardrail: dict[str, Any] | None = None

    for idx in range(1, rounds + 1):
        round_name = f"round_{idx:02d}"
        round_dir = out_dir / round_name
        _mkdir(round_dir)

        built = build_replay_dataset(
            records,
            min_decisions_per_session=max(1, int(args.min_decisions_per_session)),
            max_sessions=max(1, int(args.max_sessions)),
            min_suspicious_sessions=max(0, int(args.min_suspicious_sessions)),
            min_human_sessions=max(0, int(args.min_human_sessions)),
            min_uncertain_sessions=max(0, int(args.min_uncertain_sessions)),
        )

        replay_log_path = round_dir / "replay_dataset.jsonl"
        manifest_path = round_dir / "replay_manifest.json"
        write_jsonl(str(replay_log_path), built["replay_records"])
        write_json(
            str(manifest_path),
            {
                "decision_log_path": args.decision_log,
                "record_count": built["record_count"],
                "session_count": built["session_count"],
                "selected_session_count": built["selected_session_count"],
                "replay_record_count": built["replay_record_count"],
                "selected_label_distribution": built.get("selected_label_distribution", {}),
                "manifest": built["manifest"],
            },
        )

        judge_cfg = OfflineJudgeConfig.from_env()
        judge_cfg.mode = args.mode
        batch = run_offline_batch(
            decision_audit_path=str(replay_log_path),
            min_log_count=0,
            min_decisions_per_session=1,
            candidate_limit=max(1, int(args.candidate_limit)),
            cfg=judge_cfg,
        )

        results_path = round_dir / "offline_judge_results.jsonl"
        patches_path = round_dir / "offline_patch_candidates.json"
        batch_summary_path = round_dir / "batch_eval_summary.json"
        if batch["status"] == "OK":
            write_jsonl(str(results_path), batch["results"])
            write_json(str(patches_path), batch["patches"])

        alignment = evaluate_alignment(
            manifest_entries=built["manifest"],
            offline_results=batch["results"],
        )
        batch_summary = {
            "status": batch["status"],
            "reason": batch["reason"],
            "mode": args.mode,
            "replay_log": str(replay_log_path),
            "manifest": str(manifest_path),
            "batch": {
                "record_count": batch.get("record_count", 0),
                "session_count": batch.get("session_count", 0),
                "candidate_count": batch.get("candidate_count", 0),
                "llm_candidate_count": batch.get("llm_candidate_count", 0),
                "triage": batch.get("triage", {}),
            },
            "alignment": alignment,
            "outputs": {
                "results_out": str(results_path),
                "patches_out": str(patches_path),
            },
        }
        write_json(str(batch_summary_path), batch_summary)

        guard_cfg = GuardrailConfig.from_env()
        guardrail = evaluate_guardrails(
            cfg=guard_cfg,
            batch_summary=batch_summary,
            patches=batch.get("patches", []),
            approval_token=args.approval_token,
        )
        guardrail_path = round_dir / "policy_apply_decision.json"
        write_json(str(guardrail_path), guardrail)
        last_guardrail = guardrail

        row = {
            "round": idx,
            "dir": str(round_dir),
            "selected_session_count": built["selected_session_count"],
            "selected_label_distribution": built.get("selected_label_distribution", {}),
            "alignment": alignment,
            "guardrail": {
                "decision": guardrail.get("decision"),
                "approved": guardrail.get("approved"),
                "reasons": guardrail.get("reasons", []),
            },
        }
        loop_rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

        if guardrail.get("approved") is True:
            break
        if idx < rounds and args.sleep_seconds > 0:
            time.sleep(max(0.0, float(args.sleep_seconds)))

    loop_summary = {
        "status": "OK",
        "mode": args.mode,
        "decision_log": args.decision_log,
        "rounds_requested": rounds,
        "rounds_executed": len(loop_rows),
        "latest_guardrail": last_guardrail or {},
        "rounds": loop_rows,
    }
    write_json(str(out_dir / "loop_summary.json"), loop_summary)
    print(json.dumps(loop_summary, ensure_ascii=False, indent=2))

    if args.strict:
        approved = bool((last_guardrail or {}).get("approved"))
        if not approved:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

