"""Configuration for Attack Agent MVP (A1).

All values must be injectable (env/CLI). Do not hardcode secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import cast

from .state import SeatMode

MouseProfile = str  # "human" | "bot" (MVP; expand later)
ChallengeMode = str  # "auto" | "pass" | "fail"
ChallengeStrategy = str  # "api_fast" | "humanish_pass" | "edge_pass" | "ui_solver" | "ui_solver_stealth" | "botlike_fail" | "timing_fail" | "token_tamper"

def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True, slots=True)
class RunConfig:
    frontend_url: str = "http://localhost:3000"
    game_id: str = "game-001"
    headless: bool = False
    mode: SeatMode = "MAP"
    slow_mo_ms: int = 0
    log_dir: str = "logs/attack_mvp"
    mouse_profile: MouseProfile = "human"
    challenge_mode: ChallengeMode = "auto"
    challenge_strategy: ChallengeStrategy = "api_fast"

    @staticmethod
    def from_env() -> "RunConfig":
        mode_raw = os.getenv("TM_ATTACK_MODE", "MAP").strip().upper()
        if mode_raw not in ("MAP", "RECOMMEND"):
            raise ValueError(f"invalid TM_ATTACK_MODE: {mode_raw!r} (expected MAP|RECOMMEND)")

        mouse_profile_raw = os.getenv("TM_MOUSE_PROFILE", "human").strip().lower()
        if mouse_profile_raw not in ("human", "bot"):
            raise ValueError(f"invalid TM_MOUSE_PROFILE: {mouse_profile_raw!r} (expected human|bot)")

        challenge_mode_raw = os.getenv("TM_ATTACK_CHALLENGE_MODE", "auto").strip().lower()
        if challenge_mode_raw not in ("auto", "pass", "fail"):
            raise ValueError(
                "invalid TM_ATTACK_CHALLENGE_MODE: "
                f"{challenge_mode_raw!r} (expected auto|pass|fail)"
            )
        challenge_strategy_raw = os.getenv("TM_ATTACK_CHALLENGE_STRATEGY", "api_fast").strip().lower()
        if challenge_strategy_raw not in (
            "api_fast",
            "humanish_pass",
            "edge_pass",
            "ui_solver",
            "ui_solver_stealth",
            "botlike_fail",
            "timing_fail",
            "token_tamper",
        ):
            raise ValueError(
                "invalid TM_ATTACK_CHALLENGE_STRATEGY: "
                f"{challenge_strategy_raw!r} "
                "(expected api_fast|humanish_pass|edge_pass|ui_solver|ui_solver_stealth|botlike_fail|timing_fail|token_tamper)"
            )

        slow_mo_raw = os.getenv("TM_SLOW_MO_MS", "0").strip()
        slow_mo_ms = int(slow_mo_raw) if slow_mo_raw else 0

        return RunConfig(
            frontend_url=os.getenv("TM_FRONTEND_URL", "http://localhost:3000").strip(),
            game_id=os.getenv("TM_GAME_ID", "game-001").strip(),
            headless=_env_bool("TM_HEADLESS", False),
            mode=cast(SeatMode, mode_raw),
            slow_mo_ms=slow_mo_ms,
            log_dir=os.getenv("TM_ATTACK_LOG_DIR", "logs/attack_mvp").strip(),
            mouse_profile=mouse_profile_raw,
            challenge_mode=challenge_mode_raw,
            challenge_strategy=challenge_strategy_raw,
        )
