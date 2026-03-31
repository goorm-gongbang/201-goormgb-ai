"""CLI entrypoint for Attack Agent MVP (A1).

This module intentionally does not import heavy optional dependencies at import
time (Playwright/LangGraph) so that basic tooling/tests can run without them.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import cast

from .config import RunConfig
from .logging.audit import DecisionAuditLogger, now_ms
from .state import AgentState, SeatMode
from .runner import run as run_agent


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="traffic-master-attack-agent")
    p.add_argument("--mode", choices=["MAP", "RECOMMEND"], default=None)
    p.add_argument("--frontend-url", default=None)
    p.add_argument("--game-id", default=None)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--slow-mo-ms", type=int, default=None)
    p.add_argument("--log-dir", default=None)
    p.add_argument("--mouse-profile", choices=["human", "bot"], default=None)
    p.add_argument("--challenge-mode", choices=["auto", "pass", "fail"], default=None)
    p.add_argument(
        "--challenge-strategy",
        choices=[
            "api_fast",
            "humanish_pass",
            "edge_pass",
            "ui_solver",
            "ui_solver_stealth",
            "botlike_fail",
            "timing_fail",
            "token_tamper",
        ],
        default=None,
    )
    p.add_argument(
        "--no-synthesis",
        action="store_true",
        help="Disable human-ish mouse movement and use straight-line bot movements.",
    )
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    cfg = RunConfig.from_env()
    if args.mode is not None:
        cfg = replace(cfg, mode=cast(SeatMode, args.mode))
    if args.frontend_url is not None:
        cfg = replace(cfg, frontend_url=args.frontend_url)
    if args.game_id is not None:
        cfg = replace(cfg, game_id=args.game_id)
    if args.headless:
        cfg = replace(cfg, headless=True)
    if args.slow_mo_ms is not None:
        cfg = replace(cfg, slow_mo_ms=args.slow_mo_ms)
    if args.log_dir is not None:
        cfg = replace(cfg, log_dir=args.log_dir)
    if args.mouse_profile is not None:
        cfg = replace(cfg, mouse_profile=args.mouse_profile)
    if args.challenge_mode is not None:
        cfg = replace(cfg, challenge_mode=args.challenge_mode)
    if args.challenge_strategy is not None:
        cfg = replace(cfg, challenge_strategy=args.challenge_strategy)
    if args.no_synthesis:
        cfg = replace(cfg, mouse_profile="bot")

    state = AgentState(mode=cfg.mode)

    log_path = Path(cfg.log_dir) / f"attack_mvp_{now_ms()}.jsonl"
    with DecisionAuditLogger(log_path) as audit:
        audit.log(
            {
                "ts_ms": now_ms(),
                "event": "BOOT",
                "flow_state": state.flow_state.value,
                "mode": state.mode,
                "frontend_url": cfg.frontend_url,
                "game_id": cfg.game_id,
                "mouse_profile": cfg.mouse_profile,
                "challenge_mode": cfg.challenge_mode,
                "challenge_strategy": cfg.challenge_strategy,
            }
        )
        if args.dry_run:
            print(f"[A1 MVP] dry-run ok. mode={cfg.mode} log={log_path}")
            return 0

        final_state = run_agent(cfg, audit)

    print(f"[A1 MVP] done. mode={cfg.mode} log={log_path}")
    print(final_state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
