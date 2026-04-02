"""S3 Challenge actuator.

Ref: annex/challenge_spec.yaml
"""

from __future__ import annotations

import hashlib
import json
import random
import secrets
import time
import uuid
from dataclasses import dataclass
import os
from typing import Any, Mapping, Optional

from ..core.constants import CHALLENGE_VERIFY_UNAVAILABLE_HTTP_STATUS
from ..core.models import SessionState
from ..events.catalog import S3_FAIL, S3_PASS, S3_UNKNOWN
from ..policy.snapshot import PolicySnapshot
from ..state.keyspace import CHALLENGE_ATTEMPT_KEY_PREFIX, CHALLENGE_KEY_PREFIX
from ..state.redis_client import RedisLike
from ..state.session_state import SessionStateManager


@dataclass(slots=True, frozen=True)
class ChallengeIssueResult:
    """Challenge issue API result."""

    challenge_id: str
    game_id: str
    issued_at_ms: int
    expires_at_ms: int
    seed_commitment: str
    public_params: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ChallengeVerifyResult:
    """Challenge verify API result."""

    challenge_id: str
    game_id: str
    result: str
    reason_code: str
    server_verdict: dict[str, Any]
    http_status: int = 200
    cooldown_ms: int = 0
    attempts_in_window: int = 0
    verify_latency_ms: int = 0


class ChallengeActuator:
    """Fixed S3 challenge issue/verify handler."""

    _CHAL_PREFIX = CHALLENGE_KEY_PREFIX
    _ATTEMPT_PREFIX = CHALLENGE_ATTEMPT_KEY_PREFIX

    def __init__(
        self,
        *,
        redis: RedisLike,
        session_state: SessionStateManager,
    ) -> None:
        self._redis = redis
        self._session_state = session_state

    def issue(
        self,
        *,
        session_id: str,
        trace_id: str,
        policy: PolicySnapshot,
        now_ms: Optional[int] = None,
        client_viewport: Optional[Mapping[str, Any]] = None,
    ) -> ChallengeIssueResult:
        """Issue one S3 challenge and persist it with short TTL."""
        del trace_id
        now = now_ms or _now_ms()
        challenge_id = uuid.uuid4().hex
        seed = secrets.token_hex(16)
        target = _derive_target(seed)

        expires_at_ms = now + (policy.challenge_ttl_seconds * 1000)
        store_payload = {
            "game_id": policy.challenge_game_id,
            "seed": seed,
            "issued_at_ms": now,
            "expires_at_ms": expires_at_ms,
            "session_id": session_id,
            "used": False,
            "target_x": target["x"],
            "target_y": target["y"],
            "target_ts_ms": now + target["t_offset_ms"],
            "client_viewport": dict(client_viewport or {}),
        }
        self._redis.set(
            self._challenge_key(challenge_id),
            json.dumps(store_payload),
            ex=policy.challenge_ttl_seconds,
        )

        self._session_state.set_s3_grace(
            session_id,
            grace_until_ms=now + (policy.s3_grace_ttl_seconds * 1000),
            challenge_id=challenge_id,
        )

        return ChallengeIssueResult(
            challenge_id=challenge_id,
            game_id=policy.challenge_game_id,
            issued_at_ms=now,
            expires_at_ms=expires_at_ms,
            seed_commitment=hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            public_params={
                "ready_go_total_seconds": 2.0,
                "play_duration_seconds": 3.0,
                "catch_radius_px": policy.challenge_catch_radius_px,
                "timing_window_ms": policy.challenge_timing_window_ms,
            },
        )

    def current_retry_gate(
        self,
        *,
        session_id: str,
        policy: PolicySnapshot,
        now_ms: Optional[int] = None,
    ) -> dict[str, Optional[int]]:
        """Return the active retry gate for S3 challenge reissue/retry."""
        now = now_ms or _now_ms()
        data = self._read_attempt_state(
            session_id=session_id,
            policy=policy,
            now_ms=now,
        )
        if not data:
            return {
                "attempts_in_window": 0,
                "cooldown_until_ms": None,
            }
        cooldown_until_ms = int(data.get("cooldownUntilMs", 0) or 0)
        return {
            "attempts_in_window": int(data.get("count", 0) or 0),
            "cooldown_until_ms": cooldown_until_ms if cooldown_until_ms > now else None,
        }

    def verify(
        self,
        *,
        session_id: str,
        trace_id: str,
        challenge_id: str,
        client_answer: Mapping[str, Any],
        policy: PolicySnapshot,
        now_ms: Optional[int] = None,
    ) -> ChallengeVerifyResult:
        """Verify one challenge answer with anti-replay and fail handling."""
        del trace_id
        now = now_ms or _now_ms()
        started_at_ms = _now_ms()
        self._session_state.set_s3_grace(
            session_id,
            grace_until_ms=now + (policy.s3_grace_ttl_seconds * 1000),
            challenge_id=challenge_id,
        )
        state = self._session_state.get_or_create(session_id)
        if state.challenge_halt_until_ms is not None and now < state.challenge_halt_until_ms:
            return ChallengeVerifyResult(
                challenge_id=challenge_id,
                game_id=policy.challenge_game_id,
                result=S3_FAIL,
                reason_code="CHALLENGE_TEMPORARILY_LOCKED",
                server_verdict={"haltUntilMs": state.challenge_halt_until_ms},
                http_status=429,
                verify_latency_ms=max(0, _now_ms() - started_at_ms),
            )
        try:
            retry_gate = self.current_retry_gate(
                session_id=session_id,
                policy=policy,
                now_ms=now,
            )
        except Exception as exc:
            mode = str(os.environ.get("TM_S3_VERIFY_UNAVAILABLE_MODE", "fail_close")).strip().lower()
            fail_open = mode == "fail_open"
            return ChallengeVerifyResult(
                challenge_id=challenge_id,
                game_id=policy.challenge_game_id,
                result=S3_UNKNOWN,
                reason_code="CHALLENGE_VERIFY_UNAVAILABLE",
                server_verdict={"error": str(exc.__class__.__name__)},
                http_status=200 if fail_open else CHALLENGE_VERIFY_UNAVAILABLE_HTTP_STATUS,
                verify_latency_ms=max(0, _now_ms() - started_at_ms),
            )
        cooldown_until_ms = retry_gate["cooldown_until_ms"]
        if cooldown_until_ms is not None:
            remaining_cooldown_ms = max(0, cooldown_until_ms - now)
            return ChallengeVerifyResult(
                challenge_id=challenge_id,
                game_id=policy.challenge_game_id,
                result=S3_FAIL,
                reason_code="CHALLENGE_FAILED",
                server_verdict={"cooldownUntilMs": cooldown_until_ms},
                cooldown_ms=remaining_cooldown_ms,
                attempts_in_window=retry_gate["attempts_in_window"] or 0,
                verify_latency_ms=max(0, _now_ms() - started_at_ms),
            )

        try:
            raw = self._redis.get(self._challenge_key(challenge_id))
            if raw is None:
                return ChallengeVerifyResult(
                    challenge_id=challenge_id,
                    game_id=policy.challenge_game_id,
                    result=S3_FAIL,
                    reason_code="CHALLENGE_EXPIRED",
                    server_verdict={"challenge_id": challenge_id},
                    verify_latency_ms=max(0, _now_ms() - started_at_ms),
                )

            data = _json_dict(raw)
            if not data:
                return ChallengeVerifyResult(
                    challenge_id=challenge_id,
                    game_id=policy.challenge_game_id,
                    result=S3_FAIL,
                    reason_code="CHALLENGE_INVALID",
                    server_verdict={"challenge_id": challenge_id},
                    verify_latency_ms=max(0, _now_ms() - started_at_ms),
                )

            if str(data.get("session_id")) != session_id:
                return ChallengeVerifyResult(
                    challenge_id=challenge_id,
                    game_id=str(data.get("game_id", policy.challenge_game_id)),
                    result=S3_FAIL,
                    reason_code="CHALLENGE_INVALID",
                    server_verdict={"challenge_id": challenge_id, "reason": "session_mismatch"},
                    verify_latency_ms=max(0, _now_ms() - started_at_ms),
                )

            if bool(data.get("used", False)):
                return ChallengeVerifyResult(
                    challenge_id=challenge_id,
                    game_id=str(data.get("game_id", policy.challenge_game_id)),
                    result=S3_FAIL,
                    reason_code="CHALLENGE_INVALID",
                    server_verdict={"challenge_id": challenge_id, "reason": "already_used"},
                    verify_latency_ms=max(0, _now_ms() - started_at_ms),
                )

            expires_at_ms = int(data.get("expires_at_ms", 0))
            if now > expires_at_ms:
                data["used"] = True
                self._redis.set(
                    self._challenge_key(challenge_id),
                    json.dumps(data),
                    ex=max(1, policy.challenge_ttl_seconds),
                )
                return ChallengeVerifyResult(
                    challenge_id=challenge_id,
                    game_id=str(data.get("game_id", policy.challenge_game_id)),
                    result=S3_FAIL,
                    reason_code="CHALLENGE_EXPIRED",
                    server_verdict={"challenge_id": challenge_id},
                    verify_latency_ms=max(0, _now_ms() - started_at_ms),
                )

            verdict = self._compute_verdict(
                challenge_data=data,
                client_answer=client_answer,
                catch_radius_px=policy.challenge_catch_radius_px,
                timing_window_ms=policy.challenge_timing_window_ms,
            )

            data["used"] = True
            self._redis.set(
                self._challenge_key(challenge_id),
                json.dumps(data),
                ex=max(1, policy.challenge_ttl_seconds),
            )

            game_id = str(data.get("game_id", policy.challenge_game_id))
            if verdict["spatial_ok"] and verdict["temporal_ok"]:
                self._clear_fail_attempts(session_id)
                probation_until_ms = now + (policy.probation_seconds_after_s3_pass * 1000)
                self._session_state.update_by_role(
                    "analyzer",
                    session_id,
                    {
                        "challengeFailCount": 0,
                        "probationUntilMs": probation_until_ms,
                    },
                    is_allow=True,
                )
                self._session_state.update_by_role(
                    "orchestrator",
                    session_id,
                    {
                        "s3Passed": 1,
                        "s3PassedAtMs": now,
                        "lastDecisionAction": "NONE",
                    },
                    is_allow=True,
                )
                self._session_state.set_s3_grace(
                    session_id,
                    grace_until_ms=now + (policy.s3_grace_ttl_seconds * 1000),
                    challenge_id=challenge_id,
                )
                return ChallengeVerifyResult(
                    challenge_id=challenge_id,
                    game_id=game_id,
                    result=S3_PASS,
                    reason_code="CHALLENGE_PASSED",
                    server_verdict={"score_components": verdict},
                    verify_latency_ms=max(0, _now_ms() - started_at_ms),
                )

            attempts, cooldown_until_ms = self._register_fail_attempt(
                session_id=session_id,
                now_ms=now,
                policy=policy,
            )
            next_fail_count = state.challenge_fail_count + 1
            changes: dict[str, Any] = {
                "challengeFailCount": next_fail_count,
            }
            cooldown_ms = (
                policy.challenge_cooldown_ms_1
                if attempts <= 1
                else policy.challenge_cooldown_ms_2
            )

            if attempts > policy.challenge_max_attempts:
                halt_until_ms = now + (policy.challenge_halt_seconds * 1000)
                changes["challengeHaltUntilMs"] = halt_until_ms
                self._session_state.update_by_role(
                    "analyzer",
                    session_id,
                    changes,
                    is_allow=False,
                )
                self._session_state.set_s3_grace(
                    session_id,
                    grace_until_ms=now + (policy.s3_grace_ttl_seconds * 1000),
                    challenge_id=challenge_id,
                    attempts=attempts,
                    halt_until_ms=halt_until_ms,
                )
                return ChallengeVerifyResult(
                    challenge_id=challenge_id,
                    game_id=game_id,
                    result=S3_FAIL,
                    reason_code="CHALLENGE_TEMPORARILY_LOCKED",
                    server_verdict={"score_components": verdict},
                    http_status=429,
                    cooldown_ms=0,
                    attempts_in_window=attempts,
                    verify_latency_ms=max(0, _now_ms() - started_at_ms),
                )

            self._session_state.update_by_role(
                "analyzer",
                session_id,
                changes,
                is_allow=False,
            )
            self._session_state.set_s3_grace(
                session_id,
                grace_until_ms=now + (policy.s3_grace_ttl_seconds * 1000),
                challenge_id=challenge_id,
                attempts=attempts,
            )
            return ChallengeVerifyResult(
                challenge_id=challenge_id,
                game_id=game_id,
                result=S3_FAIL,
                reason_code="CHALLENGE_FAILED",
                server_verdict={"score_components": verdict},
                cooldown_ms=max(0, (cooldown_until_ms or now) - now),
                attempts_in_window=attempts,
                verify_latency_ms=max(0, _now_ms() - started_at_ms),
            )

        except Exception as exc:
            mode = str(os.environ.get("TM_S3_VERIFY_UNAVAILABLE_MODE", "fail_close")).strip().lower()
            fail_open = mode == "fail_open"
            return ChallengeVerifyResult(
                challenge_id=challenge_id,
                game_id=policy.challenge_game_id,
                result=S3_UNKNOWN,
                reason_code="CHALLENGE_VERIFY_UNAVAILABLE",
                server_verdict={"error": str(exc.__class__.__name__)},
                http_status=200 if fail_open else CHALLENGE_VERIFY_UNAVAILABLE_HTTP_STATUS,
                verify_latency_ms=max(0, _now_ms() - started_at_ms),
            )

    def _compute_verdict(
        self,
        *,
        challenge_data: Mapping[str, Any],
        client_answer: Mapping[str, Any],
        catch_radius_px: int,
        timing_window_ms: int,
    ) -> dict[str, Any]:
        catch_ts_ms = int(client_answer.get("catch_ts_ms", 0))
        glove_pos = client_answer.get("glove_pos_norm") or {}
        if not isinstance(glove_pos, Mapping):
            glove_pos = {}

        gx = float(glove_pos.get("x", -1.0))
        gy = float(glove_pos.get("y", -1.0))
        tx = float(challenge_data.get("target_x", 2.0))
        ty = float(challenge_data.get("target_y", 2.0))
        dx = gx - tx
        dy = gy - ty
        dist = (dx * dx + dy * dy) ** 0.5

        viewport = client_answer.get("client_viewport")
        if not isinstance(viewport, Mapping):
            viewport = challenge_data.get("client_viewport")
        if not isinstance(viewport, Mapping):
            viewport = {}

        vw = int(viewport.get("w", 1000))
        vh = int(viewport.get("h", 1000))
        norm_base = max(1, max(vw, vh))
        radius_norm = float(catch_radius_px) / float(norm_base)

        temporal_delta_ms = abs(catch_ts_ms - int(challenge_data.get("target_ts_ms", 0)))
        catch_triggered = bool(client_answer.get("catch_triggered", False))

        spatial_ok = bool(catch_triggered and dist <= radius_norm)
        temporal_ok = bool(catch_triggered and temporal_delta_ms <= timing_window_ms)

        return {
            "spatial_ok": spatial_ok,
            "temporal_ok": temporal_ok,
            "spatial_dist": dist,
            "temporal_delta_ms": temporal_delta_ms,
        }

    def _register_fail_attempt(
        self,
        *,
        session_id: str,
        now_ms: int,
        policy: PolicySnapshot,
    ) -> tuple[int, Optional[int]]:
        key = self._attempt_key(session_id)
        data = self._read_attempt_state(
            session_id=session_id,
            policy=policy,
            now_ms=now_ms,
        )
        count = 0 if data is None else int(data.get("count", 0))
        window_start = now_ms if data is None else int(data.get("window_start_ms", now_ms))

        count += 1
        cooldown_ms = (
            policy.challenge_cooldown_ms_1
            if count <= 1
            else policy.challenge_cooldown_ms_2
        )
        cooldown_until_ms = None
        if count <= policy.challenge_max_attempts and cooldown_ms > 0:
            cooldown_until_ms = now_ms + cooldown_ms
        payload = {
            "window_start_ms": window_start,
            "count": count,
        }
        if cooldown_until_ms is not None:
            payload["cooldownUntilMs"] = cooldown_until_ms
        self._redis.set(key, json.dumps(payload), ex=policy.challenge_attempt_window_s)
        return count, cooldown_until_ms

    def _read_attempt_state(
        self,
        *,
        session_id: str,
        policy: PolicySnapshot,
        now_ms: int,
    ) -> Optional[dict[str, Any]]:
        raw = self._redis.get(self._attempt_key(session_id))
        if raw is None:
            return None
        data = _json_dict(raw)
        if not data:
            return None
        old_start = int(data.get("window_start_ms", 0))
        if now_ms - old_start > policy.challenge_attempt_window_s * 1000:
            return None
        return data

    def _clear_fail_attempts(self, session_id: str) -> None:
        self._redis.delete(self._attempt_key(session_id))

    def _challenge_key(self, challenge_id: str) -> str:
        return f"{self._CHAL_PREFIX}{challenge_id}"

    def _attempt_key(self, session_id: str) -> str:
        return f"{self._ATTEMPT_PREFIX}{session_id}"



def _derive_target(seed: str) -> dict[str, float]:
    rnd = random.Random(seed)
    return {
        "x": rnd.uniform(0.15, 0.85),
        "y": rnd.uniform(0.15, 0.85),
        "t_offset_ms": rnd.randint(700, 2600),
    }



def _json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return {}
        except json.JSONDecodeError:
            return {}
    if isinstance(raw, dict):
        return dict(raw)
    return {}



def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["ChallengeActuator", "ChallengeIssueResult", "ChallengeVerifyResult"]
