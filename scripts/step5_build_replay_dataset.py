#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from traffic_master_ai.defense.offline.pipeline import load_decision_audit, write_json, write_jsonl
from traffic_master_ai.defense.offline.replay import build_replay_dataset


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step5-3 replay dataset builder from defense decision audit log."
    )
    parser.add_argument("--decision-log", default="logs/defense_decision_audit.jsonl")
    parser.add_argument("--replay-out", default="logs/step5_replay_dataset.jsonl")
    parser.add_argument("--manifest-out", default="logs/step5_replay_manifest.json")
    parser.add_argument("--min-decisions-per-session", type=int, default=3)
    parser.add_argument("--max-sessions", type=int, default=200)
    parser.add_argument("--min-suspicious-sessions", type=int, default=1)
    parser.add_argument("--min-human-sessions", type=int, default=1)
    parser.add_argument("--min-uncertain-sessions", type=int, default=0)
    args = parser.parse_args()

    records = load_decision_audit(args.decision_log)
    built = build_replay_dataset(
        records,
        min_decisions_per_session=args.min_decisions_per_session,
        max_sessions=args.max_sessions,
        min_suspicious_sessions=max(0, args.min_suspicious_sessions),
        min_human_sessions=max(0, args.min_human_sessions),
        min_uncertain_sessions=max(0, args.min_uncertain_sessions),
    )
    write_jsonl(args.replay_out, built["replay_records"])
    write_json(
        args.manifest_out,
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
    print(
        json.dumps(
            {
                "decision_log_path": args.decision_log,
                "record_count": built["record_count"],
                "selected_session_count": built["selected_session_count"],
                "replay_record_count": built["replay_record_count"],
                "selected_label_distribution": built.get("selected_label_distribution", {}),
                "replay_out": args.replay_out,
                "manifest_out": args.manifest_out,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
