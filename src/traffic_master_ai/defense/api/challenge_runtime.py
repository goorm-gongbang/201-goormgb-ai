"""Runtime challenge issuance, event ingestion, and server-side verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from .models import (
    ChallengeEventIngestRequest,
    ChallengeEventIngestResponse,
    ChallengeResultStr,
    ChallengeStartRequest,
    ChallengeStartResponse,
    ChallengeTypeStr,
    ChallengeVerifyRequest,
    ChallengeVerifyResponse,
    RuntimeStateSnapshot,
)

_TIER_RANK = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + pad)


@dataclass(slots=True)
class ChallengeConfig:
    """Challenge gate runtime tunables."""

    secret: str = "tm-local-dev-secret"
    ttl_ms: int = 120_000
    retry_limit: int = 2
    max_events: int = 6000
    min_events: int = 25
    min_duration_ms: int = 400
    max_duration_ms: int = 7_000
    max_speed_px_per_ms: float = 3.8
    max_jump_px: float = 220.0
    catch_radius_px: float = 38.0
    timing_window_ms: int = 260

    @staticmethod
    def from_env() -> ChallengeConfig:
        return ChallengeConfig(
            secret=os.getenv("TM_CHALLENGE_SECRET", "tm-local-dev-secret"),
            ttl_ms=int(os.getenv("TM_CHALLENGE_TTL_MS", "120000")),
            retry_limit=int(os.getenv("TM_CHALLENGE_RETRY_LIMIT", "2")),
            max_events=int(os.getenv("TM_CHALLENGE_MAX_EVENTS", "6000")),
            min_events=int(os.getenv("TM_CHALLENGE_MIN_EVENTS", "25")),
            min_duration_ms=int(os.getenv("TM_CHALLENGE_MIN_DURATION_MS", "400")),
            max_duration_ms=int(os.getenv("TM_CHALLENGE_MAX_DURATION_MS", "7000")),
            max_speed_px_per_ms=float(os.getenv("TM_CHALLENGE_MAX_SPEED_PX_PER_MS", "3.8")),
            max_jump_px=float(os.getenv("TM_CHALLENGE_MAX_JUMP_PX", "220")),
            catch_radius_px=float(os.getenv("TM_CHALLENGE_CATCH_RADIUS_PX", "38")),
            timing_window_ms=int(os.getenv("TM_CHALLENGE_TIMING_WINDOW_MS", "260")),
        )


@dataclass(slots=True)
class ChallengeArtifact:
    """Server-side challenge artifact."""

    challenge_id: str
    session_id: str
    challenge_type: ChallengeTypeStr
    nonce: str
    issued_at_ms: int
    expires_at_ms: int
    attempts_used: int
    attempt_limit: int
    hidden_params: dict[str, float | int | str]
    public_params: dict[str, float | int | str | bool]
    events: list[dict[str, float | int | str]] = field(default_factory=list)
    final_result: ChallengeResultStr | None = None
    final_reason: str | None = None


class ChallengeRuntime:
    """In-memory challenge runtime for local and dev integration."""

    def __init__(self, cfg: ChallengeConfig) -> None:
        self._cfg = cfg
        self._lock = Lock()
        self._artifacts: dict[str, ChallengeArtifact] = {}

    def start(
        self,
        req: ChallengeStartRequest,
        runtime_state: RuntimeStateSnapshot,
    ) -> tuple[ChallengeStartResponse, RuntimeStateSnapshot]:
        now_ms = int(time.time() * 1000)
        challenge_id = f"CH_{uuid.uuid4().hex[:12]}"
        nonce = uuid.uuid4().hex
        expires_at_ms = now_ms + self._cfg.ttl_ms

        hidden_params, public_params = self._derive_params(
            session_id=req.session_id,
            challenge_id=challenge_id,
            challenge_type=req.challenge_type,
            issued_at_ms=now_ms,
        )
        attempt_limit = runtime_state.vqa_retry_limit

        artifact = ChallengeArtifact(
            challenge_id=challenge_id,
            session_id=req.session_id,
            challenge_type=req.challenge_type,
            nonce=nonce,
            issued_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
            attempts_used=runtime_state.vqa_attempt_count,
            attempt_limit=attempt_limit,
            hidden_params=hidden_params,
            public_params=public_params,
        )
        with self._lock:
            self._artifacts[challenge_id] = artifact

        token = self._mint_token(
            challenge_id=challenge_id,
            session_id=req.session_id,
            nonce=nonce,
            issued_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
        )
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
                challenge_token=token,
                issued_at_ms=now_ms,
                expires_at_ms=expires_at_ms,
                attempt_limit=attempt_limit,
                public_params=public_params,
            ),
            next_state,
        )

    def ingest_events(
        self,
        req: ChallengeEventIngestRequest,
    ) -> ChallengeEventIngestResponse:
        now_ms = int(time.time() * 1000)
        artifact = self._resolve_active_artifact(
            challenge_id=req.challenge_id,
            session_id=req.session_id,
            token=req.challenge_token,
            now_ms=now_ms,
        )
        if artifact.final_result is not None:
            raise ValueError("challenge already finalized")

        with self._lock:
            max_append = max(0, self._cfg.max_events - len(artifact.events))
            for event in req.events[:max_append]:
                artifact.events.append(event.model_dump())
            total = len(artifact.events)

        return ChallengeEventIngestResponse(
            session_id=req.session_id,
            challenge_id=req.challenge_id,
            accepted_events=min(len(req.events), max_append),
            total_events=total,
        )

    def verify(
        self,
        req: ChallengeVerifyRequest,
        runtime_state: RuntimeStateSnapshot,
    ) -> tuple[ChallengeVerifyResponse, RuntimeStateSnapshot]:
        now_ms = int(time.time() * 1000)
        artifact = self._resolve_active_artifact(
            challenge_id=req.challenge_id,
            session_id=req.session_id,
            token=req.challenge_token,
            now_ms=now_ms,
        )
        if artifact.final_result is not None:
            attempts_left = max(artifact.attempt_limit - artifact.attempts_used, 0)
            return (
                ChallengeVerifyResponse(
                    session_id=req.session_id,
                    challenge_id=req.challenge_id,
                    result=artifact.final_result,
                    passed=artifact.final_result == "PASSED",
                    attempts_used=artifact.attempts_used,
                    attempts_left=attempts_left,
                    defense_tier=runtime_state.defense_tier,
                    action="NONE" if artifact.final_result == "PASSED" else "BLOCK",
                    reason=artifact.final_reason,
                    headers_to_add=self._result_headers(
                        artifact.final_result,
                        runtime_state.defense_tier,
                    ),
                ),
                runtime_state,
            )

        checks = self._validate_physical_consistency(artifact.events)
        checks.extend(self._validate_catch_ball(artifact, req))

        passed = len(checks) == 0

        if passed:
            artifact.final_result = "PASSED"
            artifact.final_reason = None
            attempts_left = max(artifact.attempt_limit - artifact.attempts_used, 0)
            next_state = runtime_state.model_copy(
                update={
                    "flow_state": runtime_state.flow_state,
                    "vqa_required": False,
                    "vqa_passed": True,
                    "vqa_last_result": "PASSED",
                    "vqa_attempt_count": artifact.attempts_used,
                    "active_challenge_id": None,
                    "active_challenge_expires_at_ms": None,
                    "updated_ts_ms": now_ms,
                }
            )
            return (
                ChallengeVerifyResponse(
                    session_id=req.session_id,
                    challenge_id=req.challenge_id,
                    result="PASSED",
                    passed=True,
                    attempts_used=artifact.attempts_used,
                    attempts_left=attempts_left,
                    defense_tier=runtime_state.defense_tier,
                    action="NONE",
                    reason=None,
                    headers_to_add=self._result_headers("PASSED", runtime_state.defense_tier),
                ),
                next_state,
            )

        artifact.attempts_used += 1
        attempts_left = max(artifact.attempt_limit - artifact.attempts_used, 0)
        blocked = artifact.attempts_used >= artifact.attempt_limit
        reason = checks[0]

        next_tier = "T3" if blocked else self._max_tier(runtime_state.defense_tier, "T2")
        next_state = runtime_state.model_copy(
            update={
                "defense_tier": next_tier,
                "vqa_passed": False,
                "vqa_last_result": "BLOCKED" if blocked else "FAILED",
                "vqa_attempt_count": artifact.attempts_used,
                "challenge_fail_count": runtime_state.challenge_fail_count + 1,
                "updated_ts_ms": now_ms,
            }
        )
        if blocked:
            artifact.final_result = "BLOCKED"
            artifact.final_reason = reason
            next_state = next_state.model_copy(
                update={
                    "flow_state": "FX",
                    "active_challenge_id": None,
                    "active_challenge_expires_at_ms": None,
                }
            )

        result: ChallengeResultStr = "BLOCKED" if blocked else "FAILED"
        action = "BLOCK" if blocked else "CHALLENGE"
        headers = self._result_headers(result, next_state.defense_tier)
        return (
            ChallengeVerifyResponse(
                session_id=req.session_id,
                challenge_id=req.challenge_id,
                result=result,
                passed=False,
                attempts_used=artifact.attempts_used,
                attempts_left=attempts_left,
                defense_tier=next_state.defense_tier,
                action=action,
                reason=reason,
                headers_to_add=headers,
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
            "requires_raw_events": True,
        }
        return hidden, public

    def _mint_token(
        self,
        *,
        challenge_id: str,
        session_id: str,
        nonce: str,
        issued_at_ms: int,
        expires_at_ms: int,
    ) -> str:
        payload = {
            "cid": challenge_id,
            "sid": session_id,
            "nonce": nonce,
            "iat": issued_at_ms,
            "exp": expires_at_ms,
        }
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_raw = _b64url_encode(payload_json)
        sig = _b64url_encode(
            hmac.new(
                self._cfg.secret.encode("utf-8"),
                payload_raw.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )
        return f"{payload_raw}.{sig}"

    def _parse_and_verify_token(self, token: str) -> dict[str, Any]:
        try:
            payload_raw, sig = token.split(".", 1)
        except ValueError as exc:
            raise ValueError("invalid challenge token format") from exc
        expected_sig = _b64url_encode(
            hmac.new(
                self._cfg.secret.encode("utf-8"),
                payload_raw.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("invalid challenge token signature")
        payload = json.loads(_b64url_decode(payload_raw))
        return payload

    def _resolve_active_artifact(
        self,
        *,
        challenge_id: str,
        session_id: str,
        token: str,
        now_ms: int,
    ) -> ChallengeArtifact:
        payload = self._parse_and_verify_token(token)
        if payload.get("cid") != challenge_id or payload.get("sid") != session_id:
            raise ValueError("challenge token binding mismatch")
        if int(payload.get("exp", 0)) <= now_ms:
            raise ValueError("challenge token expired")

        with self._lock:
            artifact = self._artifacts.get(challenge_id)
        if artifact is None:
            raise ValueError("challenge not found")
        if artifact.session_id != session_id:
            raise ValueError("challenge session mismatch")
        if artifact.nonce != payload.get("nonce"):
            raise ValueError("challenge nonce mismatch")
        if artifact.expires_at_ms <= now_ms:
            artifact.final_result = "EXPIRED"
            artifact.final_reason = "CHALLENGE_EXPIRED"
            raise ValueError("challenge expired")
        return artifact

    def _validate_physical_consistency(
        self,
        events: list[dict[str, float | int | str]],
    ) -> list[str]:
        reasons: list[str] = []
        if len(events) < self._cfg.min_events:
            reasons.append("INSUFFICIENT_EVENTS")
            return reasons

        timestamps = [int(e["t_ms"]) for e in events]
        if timestamps != sorted(timestamps):
            reasons.append("TIME_REVERSAL")
            return reasons

        duration = timestamps[-1] - timestamps[0]
        if duration < self._cfg.min_duration_ms:
            reasons.append("TOO_FAST")
        if duration > self._cfg.max_duration_ms:
            reasons.append("TOO_SLOW")

        total_distance = 0.0
        has_down = False
        has_click = False
        for idx in range(1, len(events)):
            prev = events[idx - 1]
            cur = events[idx]
            if prev["event"] == "down":
                has_down = True
            if cur["event"] == "click":
                has_click = True
            dt = max(1, int(cur["t_ms"]) - int(prev["t_ms"]))
            dx = float(cur["x"]) - float(prev["x"])
            dy = float(cur["y"]) - float(prev["y"])
            step = (dx * dx + dy * dy) ** 0.5
            speed = step / dt
            total_distance += step
            if step > self._cfg.max_jump_px:
                reasons.append("TELEPORT_JUMP")
                break
            if speed > self._cfg.max_speed_px_per_ms:
                reasons.append("IMPOSSIBLE_SPEED")
                break

        if total_distance < 50.0:
            reasons.append("LOW_INTERACTION")
        if not has_down or not has_click:
            reasons.append("MISSING_POINTER_SEQUENCE")
        return reasons

    def _validate_catch_ball(
        self,
        artifact: ChallengeArtifact,
        req: ChallengeVerifyRequest,
    ) -> list[str]:
        events = artifact.events
        if not events:
            return ["NO_EVENTS"]

        click_event = None
        for event in reversed(events):
            if event["event"] in ("click", "up"):
                click_event = event
                break
        if click_event is None:
            return ["NO_CLICK_EVENT"]

        click_ts = (
            req.final_click_ts_ms
            if req.final_click_ts_ms is not None
            else int(click_event["t_ms"])
        )
        timing_target_ms = int(artifact.hidden_params["timing_target_ms"])
        timing_window_ms = int(artifact.hidden_params["timing_window_ms"])
        if abs(click_ts - timing_target_ms) > timing_window_ms // 2:
            return ["TIMING_MISS"]

        target_x = float(artifact.hidden_params["target_x"])
        target_y = float(artifact.hidden_params["target_y"])
        catch_radius = float(artifact.hidden_params["catch_radius_px"])
        dx = float(click_event["x"]) - target_x
        dy = float(click_event["y"]) - target_y
        if (dx * dx + dy * dy) ** 0.5 > catch_radius:
            return ["POSITION_MISS"]

        return []

    def _result_headers(self, result: ChallengeResultStr, tier: str) -> dict[str, str]:
        headers = {"x-defense-tier": tier}
        if result == "PASSED":
            headers["x-defense-action"] = "none"
        elif result == "FAILED":
            headers["x-defense-action"] = "challenge"
            headers["x-challenge-required"] = "true"
        elif result == "BLOCKED":
            headers["x-defense-action"] = "block"
        else:
            headers["x-defense-action"] = "challenge"
            headers["x-challenge-required"] = "true"
        return headers

    def _max_tier(self, a: str, b: str) -> str:
        return a if _TIER_RANK[a] >= _TIER_RANK[b] else b
