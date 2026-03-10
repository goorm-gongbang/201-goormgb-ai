#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _playwright_installed() -> bool:
    return importlib.util.find_spec("playwright") is not None


def _default_cases() -> list[dict[str, str]]:
    return [
        {"mode": "MAP", "challenge_mode": "pass", "challenge_strategy": "ui_solver"},
        {"mode": "MAP", "challenge_mode": "pass", "challenge_strategy": "ui_solver_stealth"},
        {"mode": "MAP", "challenge_mode": "pass", "challenge_strategy": "api_fast"},
        {"mode": "MAP", "challenge_mode": "pass", "challenge_strategy": "humanish_pass"},
        {"mode": "MAP", "challenge_mode": "pass", "challenge_strategy": "edge_pass"},
        {"mode": "MAP", "challenge_mode": "fail", "challenge_strategy": "botlike_fail"},
        {"mode": "MAP", "challenge_mode": "fail", "challenge_strategy": "timing_fail"},
        {"mode": "MAP", "challenge_mode": "fail", "challenge_strategy": "token_tamper"},
        {"mode": "RECOMMEND", "challenge_mode": "pass", "challenge_strategy": "ui_solver"},
        {"mode": "RECOMMEND", "challenge_mode": "pass", "challenge_strategy": "ui_solver_stealth"},
        {"mode": "RECOMMEND", "challenge_mode": "pass", "challenge_strategy": "api_fast"},
        {"mode": "RECOMMEND", "challenge_mode": "pass", "challenge_strategy": "humanish_pass"},
        {"mode": "RECOMMEND", "challenge_mode": "fail", "challenge_strategy": "token_tamper"},
    ]


def _parse_log_path(output: str) -> str | None:
    m = re.search(r"log=(logs/attack_mvp/[^ ]+\.jsonl)", output)
    return m.group(1) if m else None


def _extract_terminal_reason(log_path: Path) -> str | None:
    if not log_path.exists():
        return None
    lines = [line.strip() for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for raw in reversed(lines):
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if item.get("event") == "RUN_END":
            reason = item.get("terminal_reason")
            return str(reason) if reason is not None else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step7 non-LLM attack-agent mode matrix runner."
    )
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually run Playwright flows. Default runs --dry-run matrix.",
    )
    parser.add_argument("--summary-out", default="logs/step7_attack_matrix_summary.json")
    args = parser.parse_args()

    can_execute = args.execute and _playwright_installed()
    if args.execute and not can_execute:
        print("[step7] playwright not installed, fallback to dry-run matrix")

    results: list[dict[str, Any]] = []
    for case in _default_cases():
        cmd = [
            sys.executable,
            "-m",
            "traffic_master_ai.attack.a1_mvp.main",
            "--mode",
            case["mode"],
            "--frontend-url",
            args.frontend_url,
            "--challenge-mode",
            case["challenge_mode"],
            "--challenge-strategy",
            case["challenge_strategy"],
        ]
        if can_execute:
            cmd.extend(["--headless"])
        else:
            cmd.extend(["--dry-run"])

        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = (proc.stdout or "") + (proc.stderr or "")
        log_rel = _parse_log_path(output)
        terminal_reason = None
        if can_execute and log_rel:
            terminal_reason = _extract_terminal_reason(Path(log_rel))
        results.append(
            {
                "case": case,
                "command": " ".join(cmd),
                "exit_code": proc.returncode,
                "dry_run": not can_execute,
                "log_path": log_rel,
                "terminal_reason": terminal_reason,
            }
        )

    success_count = sum(1 for row in results if row["exit_code"] == 0)
    summary = {
        "mode": "execute" if can_execute else "dry_run",
        "frontend_url": args.frontend_url,
        "total_cases": len(results),
        "success_count": success_count,
        "failed_count": len(results) - success_count,
        "results": results,
    }
    out = Path(args.summary_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if success_count == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
