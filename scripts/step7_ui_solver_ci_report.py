#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _playwright_installed() -> bool:
    return importlib.util.find_spec("playwright") is not None


def _default_python_bin() -> str:
    venv_bin = Path(".venv/bin/python")
    if venv_bin.exists() and os.access(venv_bin, os.X_OK):
        return str(venv_bin)
    return sys.executable


def _parse_log_path(output: str) -> str | None:
    m = re.search(r"log=(logs/attack_mvp/[^ ]+\.jsonl)", output)
    return m.group(1) if m else None


def _extract_terminal_reason(log_path: Path) -> str:
    if not log_path.exists():
        return "NO_LOG"
    lines = [line.strip() for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for raw in reversed(lines):
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if item.get("event") in ("RUN_END", "TERMINAL"):
            reason = item.get("terminal_reason")
            if reason:
                return str(reason)
            reason = item.get("reasonCode")
            if reason:
                return str(reason)
    return "UNKNOWN"


def _extract_log_details(log_path: Path) -> dict[str, Any]:
    details: dict[str, Any] = {
        "terminal_reason": "NO_LOG",
        "session_id": None,
        "primary_reason": None,
        "reason_counts": {},
    }
    if not log_path.exists():
        return details

    terminal_reason = "UNKNOWN"
    session_id: str | None = None
    reason_counter: Counter[str] = Counter()

    for raw in log_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        event = item.get("event")
        if event in ("RUN_END", "TERMINAL"):
            reason = item.get("terminal_reason") or item.get("reasonCode")
            if reason:
                terminal_reason = str(reason)
        elif event == "BOOTSTRAP_COMPLETE":
            sid = item.get("session_id")
            if sid:
                session_id = str(sid)
        elif event == "CHALLENGE_ATTEMPT":
            rc = item.get("reason_code")
            if rc:
                reason_counter[str(rc)] += 1
        elif event == "CHALLENGE_FAILED":
            err = str(item.get("error") or "")
            if err:
                m = re.search(r"\(([A-Z0-9_]+)\)", err)
                if m:
                    reason_counter[m.group(1)] += 1
        elif event == "CHALLENGE_UI_SOLVER_RETRY_REQUIRED":
            snap = item.get("snapshot") or {}
            txt = snap.get("errorText") or snap.get("statusText")
            if txt:
                reason_counter[str(txt)] += 1

    primary_reason = None
    if reason_counter:
        primary_reason = reason_counter.most_common(1)[0][0]

    details["terminal_reason"] = terminal_reason
    details["session_id"] = session_id
    details["primary_reason"] = primary_reason
    details["reason_counts"] = dict(reason_counter)
    return details


def _run_case(
    *,
    python_bin: str,
    mode: str,
    challenge_mode: str,
    challenge_strategy: str,
    frontend_url: str,
    execute: bool,
    headless: bool,
) -> dict[str, Any]:
    cmd = [
        python_bin,
        "-m",
        "traffic_master_ai.attack.a1_mvp.main",
        "--mode",
        mode,
        "--frontend-url",
        frontend_url,
        "--challenge-mode",
        challenge_mode,
        "--challenge-strategy",
        challenge_strategy,
    ]
    if not execute:
        cmd.append("--dry-run")
    elif headless:
        cmd.append("--headless")

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = (proc.stdout or "") + (proc.stderr or "")
    log_rel = _parse_log_path(output)
    terminal_reason = "DRY_RUN"
    reason_counts: dict[str, int] = {}
    primary_reason: str | None = None
    session_id: str | None = None
    if execute:
        if log_rel:
            details = _extract_log_details(Path(log_rel))
            terminal_reason = str(details.get("terminal_reason", "UNKNOWN"))
            reason_counts = dict(details.get("reason_counts", {}))
            primary_reason = details.get("primary_reason")
            session_id = details.get("session_id")
        elif proc.returncode != 0:
            terminal_reason = "PROCESS_ERROR"
        else:
            terminal_reason = "NO_LOG"

    lines = [line for line in output.splitlines() if line.strip()]
    output_tail = lines[-8:] if lines else []

    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "log_path": log_rel,
        "terminal_reason": terminal_reason,
        "session_id": session_id,
        "primary_reason": primary_reason,
        "reason_counts": reason_counts,
        "output_tail": output_tail,
    }


def _collect_case_stats(
    *,
    python_bin: str,
    frontend_url: str,
    execute: bool,
    headless: bool,
    runs: int,
    mode: str,
    challenge_mode: str,
    challenge_strategy: str,
    expected_reason: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for _ in range(runs):
        rows.append(
            _run_case(
                python_bin=python_bin,
                mode=mode,
                challenge_mode=challenge_mode,
                challenge_strategy=challenge_strategy,
                frontend_url=frontend_url,
                execute=execute,
                headless=headless,
            )
        )

    reason_counter = Counter(row["terminal_reason"] for row in rows)
    primary_reason_counter = Counter(row.get("primary_reason") for row in rows if row.get("primary_reason"))
    matched = sum(1 for row in rows if row["terminal_reason"] == expected_reason)
    nonzero_exit = sum(1 for row in rows if row["exit_code"] != 0)
    return {
        "case": {
            "mode": mode,
            "challenge_mode": challenge_mode,
            "challenge_strategy": challenge_strategy,
            "expected_reason": expected_reason,
        },
        "runs": runs,
        "expected_match_count": matched,
        "expected_match_rate": (matched / runs) if runs > 0 else 0.0,
        "nonzero_exit_count": nonzero_exit,
        "terminal_reason_counts": dict(reason_counter),
        "primary_reason_counts": dict(primary_reason_counter),
        "sessions": [row.get("session_id") for row in rows if row.get("session_id")],
        "runs_detail": rows,
        "samples": rows[:2],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step7 CI report: repeated ui_solver pass-rate and api_forge blocked-rate"
    )
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--python-bin", default=_default_python_bin())
    parser.add_argument("--runs-per-case", type=int, default=5)
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--summary-out", default="logs/step7_ui_solver_ci_report.json")
    parser.add_argument("--headless", dest="headless", action="store_true")
    parser.add_argument("--headful", dest="headless", action="store_false")
    parser.set_defaults(headless=True)
    parser.add_argument(
        "--include-ui-stealth",
        action="store_true",
        default=False,
        help="Include ui_solver_stealth attack cases (MAP/RECOMMEND).",
    )
    parser.add_argument(
        "--ui-expected-reason",
        default="BLOCKED",
        choices=["DONE", "BLOCKED"],
        help="Expected terminal reason for ui_solver cases (policy dependent).",
    )

    # Gate thresholds
    parser.add_argument("--min-ui-done-rate", type=float, default=0.0)
    parser.add_argument("--min-ui-blocked-rate", type=float, default=0.0)
    parser.add_argument("--min-api-fast-blocked-rate", type=float, default=1.0)
    parser.add_argument(
        "--min-ui-stealth-blocked-rate",
        type=float,
        default=0.0,
        help="Minimum blocked-rate for ui_solver_stealth cases (effective when --include-ui-stealth).",
    )
    args = parser.parse_args()

    can_execute = args.execute and _playwright_installed()
    if args.execute and not can_execute:
        print("[step7-ci] playwright not installed, falling back to dry-run")

    execute = can_execute
    headless = bool(args.headless)
    runs = max(1, args.runs_per_case)

    case_results = [
        _collect_case_stats(
            python_bin=args.python_bin,
            frontend_url=args.frontend_url,
            execute=execute,
            headless=headless,
            runs=runs,
            mode="MAP",
            challenge_mode="pass",
            challenge_strategy="ui_solver",
            expected_reason=args.ui_expected_reason,
        ),
        _collect_case_stats(
            python_bin=args.python_bin,
            frontend_url=args.frontend_url,
            execute=execute,
            headless=headless,
            runs=runs,
            mode="RECOMMEND",
            challenge_mode="pass",
            challenge_strategy="ui_solver",
            expected_reason=args.ui_expected_reason,
        ),
        _collect_case_stats(
            python_bin=args.python_bin,
            frontend_url=args.frontend_url,
            execute=execute,
            headless=headless,
            runs=runs,
            mode="MAP",
            challenge_mode="pass",
            challenge_strategy="api_fast",
            expected_reason="BLOCKED",
        ),
        _collect_case_stats(
            python_bin=args.python_bin,
            frontend_url=args.frontend_url,
            execute=execute,
            headless=headless,
            runs=runs,
            mode="RECOMMEND",
            challenge_mode="pass",
            challenge_strategy="api_fast",
            expected_reason="BLOCKED",
        ),
    ]
    if args.include_ui_stealth:
        case_results.extend(
            [
                _collect_case_stats(
                    python_bin=args.python_bin,
                    frontend_url=args.frontend_url,
                    execute=execute,
                    headless=headless,
                    runs=runs,
                    mode="MAP",
                    challenge_mode="pass",
                    challenge_strategy="ui_solver_stealth",
                    expected_reason="BLOCKED",
                ),
                _collect_case_stats(
                    python_bin=args.python_bin,
                    frontend_url=args.frontend_url,
                    execute=execute,
                    headless=headless,
                    runs=runs,
                    mode="RECOMMEND",
                    challenge_mode="pass",
                    challenge_strategy="ui_solver_stealth",
                    expected_reason="BLOCKED",
                ),
            ]
        )

    by_key = {
        (r["case"]["mode"], r["case"]["challenge_strategy"]): r
        for r in case_results
    }

    def _reason_rate(case_stat: dict[str, Any], reason: str) -> float:
        runs_count = max(1, int(case_stat.get("runs", 0)))
        counts = case_stat.get("terminal_reason_counts", {})
        return float(counts.get(reason, 0)) / float(runs_count)

    ui_map_done = _reason_rate(by_key[("MAP", "ui_solver")], "DONE")
    ui_reco_done = _reason_rate(by_key[("RECOMMEND", "ui_solver")], "DONE")
    ui_map_block = _reason_rate(by_key[("MAP", "ui_solver")], "BLOCKED")
    ui_reco_block = _reason_rate(by_key[("RECOMMEND", "ui_solver")], "BLOCKED")

    api_map_block = _reason_rate(by_key[("MAP", "api_fast")], "BLOCKED")
    api_reco_block = _reason_rate(by_key[("RECOMMEND", "api_fast")], "BLOCKED")

    ui_done_rate = (ui_map_done + ui_reco_done) / 2.0
    ui_blocked_rate = (ui_map_block + ui_reco_block) / 2.0
    api_fast_blocked_rate = (api_map_block + api_reco_block) / 2.0

    stealth_blocked_rate = None
    if args.include_ui_stealth:
        stealth_map_block = _reason_rate(by_key[("MAP", "ui_solver_stealth")], "BLOCKED")
        stealth_reco_block = _reason_rate(by_key[("RECOMMEND", "ui_solver_stealth")], "BLOCKED")
        stealth_blocked_rate = (stealth_map_block + stealth_reco_block) / 2.0

    gate_reasons: list[str] = []
    if execute:
        if ui_done_rate < args.min_ui_done_rate:
            gate_reasons.append("UI_DONE_RATE_BELOW_THRESHOLD")
        if ui_blocked_rate < args.min_ui_blocked_rate:
            gate_reasons.append("UI_BLOCKED_RATE_BELOW_THRESHOLD")
        if api_fast_blocked_rate < args.min_api_fast_blocked_rate:
            gate_reasons.append("API_FAST_BLOCKED_RATE_BELOW_THRESHOLD")
        if args.include_ui_stealth and stealth_blocked_rate is not None:
            if stealth_blocked_rate < args.min_ui_stealth_blocked_rate:
                gate_reasons.append("UI_STEALTH_BLOCKED_RATE_BELOW_THRESHOLD")
    else:
        gate_reasons.append("DRY_RUN_ONLY")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "execute" if execute else "dry_run",
        "frontend_url": args.frontend_url,
        "runs_per_case": runs,
        "metrics": {
            "ui_solver_done_rate": ui_done_rate,
            "ui_solver_blocked_rate": ui_blocked_rate,
            "api_fast_blocked_rate": api_fast_blocked_rate,
            "ui_solver_stealth_blocked_rate": stealth_blocked_rate,
        },
        "thresholds": {
            "min_ui_done_rate": args.min_ui_done_rate,
            "min_ui_blocked_rate": args.min_ui_blocked_rate,
            "min_api_fast_blocked_rate": args.min_api_fast_blocked_rate,
            "min_ui_stealth_blocked_rate": args.min_ui_stealth_blocked_rate,
        },
        "gate": {
            "passed": len(gate_reasons) == 0,
            "reasons": gate_reasons,
        },
        "cases": case_results,
    }

    out = Path(args.summary_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
