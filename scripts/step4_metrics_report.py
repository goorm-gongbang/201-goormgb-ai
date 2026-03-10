#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield {"_parse_error": True, "_lineno": lineno, "_path": str(path)}


def _collect_attack_metrics(log_dir: Path, latest_n: int) -> dict[str, float | int]:
    attempts = 0
    failed_attempts = 0
    blocked_failed_attempts = 0
    latency_samples: list[float] = []
    parse_errors = 0

    challenge_sessions: set[str] = set()
    challenge_passed: set[str] = set()
    challenge_failed: set[str] = set()
    challenge_strategy: dict[str, str] = {}

    files = sorted(log_dir.glob("*.jsonl"))
    if latest_n > 0:
        files = files[-latest_n:]

    for p in files:
        for rec in _iter_jsonl(p):
            if rec.get("_parse_error"):
                parse_errors += 1
                continue
            if rec.get("event") == "CHALLENGE_ATTEMPT":
                attempts += 1
                latency = rec.get("challenge_solver_latency_ms")
                if isinstance(latency, (int, float)):
                    latency_samples.append(float(latency))
                challenge_id = rec.get("challenge_id")
                if isinstance(challenge_id, str) and challenge_id:
                    challenge_sessions.add(challenge_id)

                result = str(rec.get("challenge_result", "")).upper()
                if result == "PASS" and isinstance(challenge_id, str) and challenge_id:
                    challenge_passed.add(challenge_id)
                if result in {"FAILED", "BLOCKED", "FAIL"}:
                    failed_attempts += 1
                    if isinstance(challenge_id, str) and challenge_id:
                        challenge_failed.add(challenge_id)
                if rec.get("blocked") is True:
                    blocked_failed_attempts += 1
            elif rec.get("event") == "CHALLENGE_MODE_SELECTED":
                challenge_id = rec.get("challenge_id")
                if isinstance(challenge_id, str) and challenge_id:
                    challenge_sessions.add(challenge_id)
                    strategy = str(rec.get("challenge_solver_strategy") or "")
                    if strategy:
                        challenge_strategy[challenge_id] = strategy
            elif rec.get("event") == "CHALLENGE_PASSED":
                challenge_id = rec.get("challenge_id")
                if isinstance(challenge_id, str) and challenge_id:
                    challenge_sessions.add(challenge_id)
                    challenge_passed.add(challenge_id)
            elif rec.get("event") == "CHALLENGE_FAILED":
                challenge_id = rec.get("challenge_id")
                if isinstance(challenge_id, str) and challenge_id:
                    challenge_sessions.add(challenge_id)
                    challenge_failed.add(challenge_id)

    # Session-level outcomes are keyed by challenge_id (single source of truth).
    total_sessions = len(challenge_sessions)
    passed_sessions = len(challenge_passed)
    failed_sessions = len({cid for cid in challenge_failed if cid not in challenge_passed})
    success_rate = (passed_sessions / total_sessions) if total_sessions else 0.0
    fail_rate = (failed_sessions / total_sessions) if total_sessions else 0.0
    attempt_fail_rate = (failed_attempts / attempts) if attempts else 0.0
    blocked_rate_after_fail = (blocked_failed_attempts / failed_attempts) if failed_attempts else 0.0
    median_latency = median(latency_samples) if latency_samples else 0.0

    false_pass_suspicions = 0
    for cid in challenge_passed:
        strategy = challenge_strategy.get(cid, "").lower()
        if strategy.startswith("bot"):
            false_pass_suspicions += 1

    return {
        "attack_log_files_scanned": len(files),
        "attack_log_parse_errors": parse_errors,
        "challenge_sessions_total": total_sessions,
        "challenge_sessions_passed": passed_sessions,
        "challenge_sessions_failed": failed_sessions,
        "challenge_attempts": attempts,
        "challenge_attempt_fail_count": failed_attempts,
        "solver_success_rate": round(success_rate, 4),
        "solver_fail_rate": round(fail_rate, 4),
        "solver_attempt_fail_rate": round(attempt_fail_rate, 4),
        "blocked_rate_after_fail": round(blocked_rate_after_fail, 4),
        "median_solver_latency_ms": round(float(median_latency), 2),
        "false_pass_suspicion_count": false_pass_suspicions,
    }


def _collect_decision_metrics(decision_log: Path) -> dict[str, int]:
    challenge_decisions = 0
    block_decisions = 0
    gate_decisions = 0
    parse_errors = 0
    verified_pass = 0
    verified_fail = 0
    verified_block = 0
    for rec in _iter_jsonl(decision_log):
        if rec.get("_parse_error"):
            parse_errors += 1
            continue
        action = str(rec.get("action") or "").upper()
        actions = [str(x).upper() for x in rec.get("actions", []) if isinstance(x, str)]
        bucket = {action, *actions}
        if "CHALLENGE" in bucket:
            challenge_decisions += 1
        if "BLOCK" in bucket:
            block_decisions += 1
        if "GATE" in bucket:
            gate_decisions += 1

        if rec.get("event_type") == "CHALLENGE_VERIFIED" and isinstance(rec.get("payload"), dict):
            result = str(rec["payload"].get("result", "")).upper()
            if result == "PASSED":
                verified_pass += 1
            elif result == "FAILED":
                verified_fail += 1
            elif result == "BLOCKED":
                verified_block += 1
    return {
        "decision_log_parse_errors": parse_errors,
        "decision_challenge_count": challenge_decisions,
        "decision_block_count": block_decisions,
        "decision_gate_count": gate_decisions,
        "challenge_verified_pass_count": verified_pass,
        "challenge_verified_fail_count": verified_fail,
        "challenge_verified_block_count": verified_block,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Step4 metrics quality report")
    parser.add_argument("--attack-log-dir", default="logs/attack_mvp")
    parser.add_argument("--decision-log", default="logs/defense_decision_audit.jsonl")
    parser.add_argument("--latest-n", type=int, default=0, help="Use only latest N attack log files (0=all)")
    parser.add_argument("--output", default="", help="Optional output JSON file path")
    parser.add_argument("--min-success-rate", type=float, default=0.8)
    parser.add_argument("--max-median-latency-ms", type=float, default=1200.0)
    parser.add_argument("--max-false-pass-suspicion", type=int, default=0)
    parser.add_argument("--strict", action="store_true", default=False)
    args = parser.parse_args()

    attack_metrics = _collect_attack_metrics(Path(args.attack_log_dir), latest_n=max(0, args.latest_n))
    decision_metrics = _collect_decision_metrics(Path(args.decision_log))
    summary = {**attack_metrics, **decision_metrics}

    gate = {
        "has_samples": summary["challenge_sessions_total"] > 0,
        "success_rate_ok": summary["solver_success_rate"] >= args.min_success_rate,
        "latency_ok": summary["median_solver_latency_ms"] <= args.max_median_latency_ms,
        "false_pass_ok": summary["false_pass_suspicion_count"] <= args.max_false_pass_suspicion,
    }
    gate["all_ok"] = all(gate.values())

    result: dict[str, Any] = {"summary": summary, "gate": gate}
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["output"] = str(out)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.strict and not gate["all_ok"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
