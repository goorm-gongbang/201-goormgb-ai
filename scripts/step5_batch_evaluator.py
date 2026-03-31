#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from traffic_master_ai.defense.offline.pipeline import (
    OfflineJudgeConfig,
    run_offline_batch,
    write_json,
    write_jsonl,
)
from traffic_master_ai.defense.offline.replay import evaluate_alignment


def _read_manifest(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return []
    entries = raw.get("manifest")
    if not isinstance(entries, list):
        return []
    return [row for row in entries if isinstance(row, dict)]


def _manifest_label_distribution(entries: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {"SUSPICIOUS": 0, "HUMAN": 0, "UNCERTAIN": 0}
    for row in entries:
        label = str(row.get("expected_label") or "").upper().strip()
        if label in out:
            out[label] += 1
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step5-3 offline batch evaluator against replay dataset."
    )
    parser.add_argument("--replay-log", default="logs/step5_replay_dataset.jsonl")
    parser.add_argument("--manifest", default="logs/step5_replay_manifest.json")
    parser.add_argument("--results-out", default="logs/step5_offline_judge_results.jsonl")
    parser.add_argument("--patches-out", default="logs/step5_offline_patch_candidates.json")
    parser.add_argument("--summary-out", default="logs/step5_batch_eval_summary.json")
    parser.add_argument(
        "--mode",
        choices=["mock", "openai_compatible"],
        default="mock",
        help="Offline judge mode.",
    )
    parser.add_argument("--candidate-limit", type=int, default=500)
    parser.add_argument("--strict", action="store_true", default=False)
    args = parser.parse_args()

    cfg = OfflineJudgeConfig.from_env()
    cfg.mode = args.mode
    batch = run_offline_batch(
        decision_audit_path=args.replay_log,
        min_log_count=0,
        min_decisions_per_session=1,
        candidate_limit=max(1, args.candidate_limit),
        cfg=cfg,
    )
    if batch["status"] == "OK":
        write_jsonl(args.results_out, batch["results"])
        write_json(args.patches_out, batch["patches"])

    manifest_entries = _read_manifest(args.manifest)
    alignment = evaluate_alignment(
        manifest_entries=manifest_entries,
        offline_results=batch["results"],
    )
    summary = {
        "status": batch["status"],
        "reason": batch["reason"],
        "mode": args.mode,
        "replay_log": args.replay_log,
        "manifest": args.manifest,
        "batch": {
            "record_count": batch.get("record_count", 0),
            "session_count": batch.get("session_count", 0),
            "candidate_count": batch.get("candidate_count", 0),
            "llm_candidate_count": batch.get("llm_candidate_count", 0),
            "triage": batch.get("triage", {}),
        },
        "manifest_label_distribution": _manifest_label_distribution(manifest_entries),
        "alignment": alignment,
        "outputs": {
            "results_out": args.results_out,
            "patches_out": args.patches_out,
        },
    }
    write_json(args.summary_out, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.strict and summary["status"] != "OK":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
