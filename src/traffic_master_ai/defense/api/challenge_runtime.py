"""Runtime challenge issuance helpers for /ai challenge routes."""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import time
import uuid
from dataclasses import dataclass

from .models import (
    ChallengeStartRequest,
    ChallengeStartResponse,
    ChallengeTypeStr,
    RuntimeStateSnapshot,
)
from .settings import read_float, read_int, read_str


@dataclass(slots=True)
class ChallengeConfig:
    """Challenge gate runtime tunables."""

    secret: str = "tm-local-dev-secret"
    ttl_ms: int = 120_000
    catch_radius_px: float = 38.0
    timing_window_ms: int = 260

    @staticmethod
    def from_settings() -> ChallengeConfig:
        return ChallengeConfig(
            secret=read_str("TM_CHALLENGE_SECRET", "tm-local-dev-secret"),
            ttl_ms=read_int("TM_CHALLENGE_TTL_MS", 120000),
            catch_radius_px=read_float("TM_CHALLENGE_CATCH_RADIUS_PX", 38.0),
            timing_window_ms=read_int("TM_CHALLENGE_TIMING_WINDOW_MS", 260),
        )


class ChallengeRuntime:
    """In-memory challenge runtime for local and dev integration."""

    def __init__(self, cfg: ChallengeConfig) -> None:
        self._cfg = cfg

    def start(
        self,
        req: ChallengeStartRequest,
        runtime_state: RuntimeStateSnapshot,
    ) -> tuple[ChallengeStartResponse, RuntimeStateSnapshot]:
        now_ms = int(time.time() * 1000)
        challenge_id = f"CH_{uuid.uuid4().hex[:12]}"
        expires_at_ms = now_ms + self._cfg.ttl_ms

        hidden_params, public_params = self._derive_params(
            session_id=req.session_id,
            challenge_id=challenge_id,
            challenge_type=req.challenge_type,
            issued_at_ms=now_ms,
        )
        attempt_limit = runtime_state.vqa_retry_limit

        next_state = runtime_state.model_copy(
            update={
                "flow_state": req.flow_state or runtime_state.flow_state,
                "vqa_required": True,
                "active_challenge_id": challenge_id,
                "active_challenge_expires_at_ms": expires_at_ms,
                "updated_ts_ms": now_ms,
            }
        )

        return (
            ChallengeStartResponse(
                session_id=req.session_id,
                challenge_id=challenge_id,
                challenge_type=req.challenge_type,
                issued_at_ms=now_ms,
                expires_at_ms=expires_at_ms,
                attempt_limit=attempt_limit,
                public_params=public_params,
            ),
            next_state,
        )

    def _derive_params(
        self,
        *,
        session_id: str,
        challenge_id: str,
        challenge_type: ChallengeTypeStr,
        issued_at_ms: int,
    ) -> tuple[dict[str, float | int | str], dict[str, float | int | str | bool]]:
        seed_src = f"{session_id}:{challenge_id}:{challenge_type}:{issued_at_ms}"
        digest = hmac.new(
            self._cfg.secret.encode("utf-8"),
            seed_src.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        rng = random.Random(int.from_bytes(digest[:8], byteorder="big", signed=False))
        target_x = round(rng.uniform(220.0, 580.0), 2)
        target_y = round(rng.uniform(120.0, 330.0), 2)
        timing_target_ms = rng.randint(920, 1360)

        hidden = {
            "target_x": target_x,
            "target_y": target_y,
            "timing_target_ms": timing_target_ms,
            "catch_radius_px": self._cfg.catch_radius_px,
            "timing_window_ms": self._cfg.timing_window_ms,
        }
        commit = hashlib.sha256(json.dumps(hidden, sort_keys=True).encode("utf-8")).hexdigest()
        public = {
            "variant_id": f"VAR_{digest.hex()[:10]}",
            "challenge_type": challenge_type,
            "timing_track_ms": 1600,
            "time_limit_ms": self._cfg.ttl_ms,
            "server_commit": commit,
            "requires_raw_events": False,
        }
        return hidden, public
