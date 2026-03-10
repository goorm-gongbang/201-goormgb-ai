#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from traffic_master_ai.defense.offline.guardrails import GuardrailConfig, evaluate_guardrails
from traffic_master_ai.defense.offline.pipeline import write_json


def _load_json_object(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def _load_json_array(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step5-4 policy apply guardrail checker (manual-approval-first)."
    )
    parser.add_argument("--batch-summary", default="logs/step5_batch_eval_summary.json")
    parser.add_argument("--patches", default="logs/step5_offline_patch_candidates.json")
    parser.add_argument("--decision-out", default="logs/step5_policy_apply_decision.json")
    parser.add_argument("--approval-token", default="", help="Manual approval token")
    parser.add_argument("--strict", action="store_true", default=False)
    args = parser.parse_args()

    summary = _load_json_object(args.batch_summary)
    patches = _load_json_array(args.patches)
    cfg = GuardrailConfig.from_env()
    decision = evaluate_guardrails(
        cfg=cfg,
        batch_summary=summary,
        patches=patches,
        approval_token=args.approval_token or None,
    )
    write_json(args.decision_out, decision)
    print(json.dumps(decision, ensure_ascii=False, indent=2))

    if args.strict and not bool(decision.get("approved", False)):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
