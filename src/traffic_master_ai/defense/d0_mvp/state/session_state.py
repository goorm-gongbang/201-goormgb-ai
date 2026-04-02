"""Session state manager — tm:decision-state:session:{sessionId} CRUD + TTL refresh.

Ref: L1/runtime/state.yaml#redis.keyspace.session_key
     L1/runtime/state.yaml#ttl.refresh_policy (Strict + S3 Grace)
     L1/runtime/state.yaml#writer_responsibility
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
import threading
import time
import uuid
from typing import Any, Optional

from ..core.constants import (
    S3_GRACE_TTL_SECONDS,
    SESSION_DIST_LOCK_ENABLED,
    SESSION_DIST_LOCK_TTL_MS,
    SESSION_DIST_LOCK_WAIT_MS,
    SESSION_STATE_TTL_SECONDS,
)
from ..core.models import SessionState
from .keyspace import SESSION_KEY_PREFIX, SESSION_LOCK_KEY_PREFIX, S3_GRACE_KEY_PREFIX
from .redis_client import RedisLike

logger = logging.getLogger(__name__)

_WRITER_ALLOWED_FIELDS: dict[str, frozenset[str]] = {
    # Ref: L1/runtime/state.yaml#writer_responsibility.writers.guard
    "guard": frozenset({"riskScore", "defenseTier", "lastStepRisk", "lastGuardTsMs"}),
    # Ref: L1/runtime/state.yaml#writer_responsibility.writers.analyzer
    "analyzer": frozenset(
        {
            "challengeFailCount",
            "seatTakenStreak",
            "holdFailStreak",
            "probationUntilMs",
            "challengeHaltUntilMs",
        }
    ),
    # Ref: L1/runtime/state.yaml#writer_responsibility.writers.orchestrator
    "orchestrator": frozenset(
        {"flowState", "s3Passed", "s3PassedAtMs", "lastDecisionAction"}
    ),
}


class SessionStateManager:
    """Manages tm:decision-state:session:{sessionId} Redis hash.

    TTL refresh policy (state.yaml#ttl.refresh_policy):
    - STRICT: DENY responses do NOT refresh TTL.
    - ALLOW: TTL is refreshed only on ALLOW-path.
    - S3 Grace: At S3-related flows, a separate short-TTL tm:grace:s3:* key is managed.
    """

    def __init__(
        self,
        redis: RedisLike,
        session_ttl_s: int = SESSION_STATE_TTL_SECONDS,
        s3_grace_ttl_s: int = S3_GRACE_TTL_SECONDS,
        dist_lock_enabled: bool = SESSION_DIST_LOCK_ENABLED,
        dist_lock_wait_ms: int = SESSION_DIST_LOCK_WAIT_MS,
        dist_lock_ttl_ms: int = SESSION_DIST_LOCK_TTL_MS,
    ) -> None:
        self._redis = redis
        self._session_ttl_s = session_ttl_s
        self._s3_grace_ttl_s = s3_grace_ttl_s
        self._dist_lock_enabled = bool(dist_lock_enabled)
        self._dist_lock_wait_ms = max(0, int(dist_lock_wait_ms))
        self._dist_lock_ttl_ms = max(200, int(dist_lock_ttl_ms))
        self._lock_index: dict[str, threading.RLock] = {}
        self._lock_index_guard = threading.Lock()

    # --- Key helpers ---
    @staticmethod
    def session_key(session_id: str) -> str:
        return f"{SESSION_KEY_PREFIX}{session_id}"

    @staticmethod
    def s3_grace_key(session_id: str) -> str:
        return f"{S3_GRACE_KEY_PREFIX}{session_id}"

    # --- Read ---
    def get(self, session_id: str) -> Optional[SessionState]:
        """Read session state from Redis.

        Returns None if key does not exist.
        """
        key = self.session_key(session_id)
        raw = self._redis.hgetall(key)
        if not raw:
            return None
        # Coerce all values to str for consistent parsing
        coerced = {k: str(v) if not isinstance(v, str) else v for k, v in raw.items()}
        sanitized = _sanitize_session_state_dict(coerced)
        sanitized_compare = {
            k: str(v) if not isinstance(v, str) else v for k, v in sanitized.items()
        }
        if sanitized_compare != coerced:
            logger.warning("Recovered invalid session state for %s via read-side clamp", session_id)
        return SessionState.from_redis_dict(sanitized)

    def get_or_create(self, session_id: str, policy_version: str = "") -> SessionState:
        """Read existing state or create a new default state.

        Initialises with the given policy_version.
        """
        state = self.get(session_id)
        if state is not None:
            if policy_version and state.policy_version != policy_version:
                self.sync_policy_version(session_id, policy_version)
                state.policy_version = policy_version
            return state
        state = SessionState(policy_version=policy_version)
        self._save(session_id, state)
        return state

    # --- Write ---
    def update(
        self,
        session_id: str,
        changes: dict[str, Any],
        *,
        is_allow: bool = True,
        writer: Optional[str] = None,
    ) -> None:
        """Apply partial updates to session state.

        Args:
            session_id: Session identifier.
            changes: Fields to update (camelCase keys matching Redis field names).
            is_allow: True → refresh TTL. False (DENY) → no TTL refresh (Strict).
            writer: Optional writer role ("guard" | "analyzer" | "orchestrator").
        """
        if writer is not None:
            self._validate_writer_fields(writer, changes)

        key = self.session_key(session_id)
        self._write_hash(
            key,
            changes,
            expire_seconds=self._session_ttl_s if is_allow else None,
        )

    def update_by_role(
        self,
        writer: str,
        session_id: str,
        changes: dict[str, Any],
        *,
        is_allow: bool = True,
    ) -> None:
        """Role-aware write helper using writer responsibility contract."""
        self.update(session_id, changes, is_allow=is_allow, writer=writer)

    def increment_by_role(
        self,
        writer: str,
        session_id: str,
        field: str,
        *,
        amount: int = 1,
        is_allow: bool = False,
    ) -> int:
        """Atomically increment one allowed numeric field and optionally refresh TTL."""
        self._validate_writer_fields(writer, {field: amount})
        key = self.session_key(session_id)
        new_value = int(self._redis.hincrby(key, field, amount))
        if is_allow:
            self._redis.expire(key, self._session_ttl_s)
        return new_value

    @contextmanager
    def session_lock(self, session_id: str):
        """Same-session lock for runtime mutations.

        Uses process-local RLock and Redis distributed lock (best-effort).
        """
        lock = self._get_session_lock(session_id)
        lock.acquire()
        lock_token: Optional[str] = None
        try:
            lock_token = self._acquire_dist_lock(session_id)
            yield
        finally:
            if lock_token is not None:
                self._release_dist_lock(session_id, lock_token)
            lock.release()

    def sync_policy_version(
        self,
        session_id: str,
        policy_version: str,
        *,
        refresh_ttl: bool = False,
    ) -> None:
        """Keep the stored policyVersion aligned with the active runtime policy."""
        if not policy_version:
            return
        self.update(
            session_id,
            {"policyVersion": policy_version},
            is_allow=refresh_ttl,
        )

    def _validate_writer_fields(self, writer: str, changes: dict[str, Any]) -> None:
        allowed = _WRITER_ALLOWED_FIELDS.get(writer)
        if allowed is None:
            raise ValueError(f"Unknown session state writer role: {writer}")
        illegal = sorted(k for k in changes if k not in allowed)
        if illegal:
            raise PermissionError(
                f"Writer '{writer}' cannot write fields: {', '.join(illegal)}"
            )

    def _save(self, session_id: str, state: SessionState) -> None:
        """Full write of session state."""
        key = self.session_key(session_id)
        self._write_hash(key, state.to_redis_dict(), expire_seconds=self._session_ttl_s)

    # --- S3 Grace Period ---
    def set_s3_grace(
        self,
        session_id: str,
        grace_until_ms: int,
        challenge_id: Optional[str] = None,
        attempts: Optional[int] = None,
        halt_until_ms: Optional[int] = None,
    ) -> None:
        """Set/refresh S3 grace period key.

        Ref: state.yaml#ttl.refresh_policy.grace_period
        Applies when: S3 challenge issued, S3 verify attempted, DENY=428/429.
        """
        key = self.s3_grace_key(session_id)
        data: dict[str, Any] = {"graceUntilMs": grace_until_ms}
        if challenge_id is not None:
            data["lastChallengeId"] = challenge_id
        if attempts is not None:
            data["attemptsSnapshot"] = attempts
        if halt_until_ms is not None:
            data["haltUntilMs"] = halt_until_ms
        self._write_hash(key, data, expire_seconds=self._s3_grace_ttl_s)

    def get_s3_grace(self, session_id: str) -> Optional[dict[str, Any]]:
        """Read S3 grace period state."""
        key = self.s3_grace_key(session_id)
        raw = self._redis.hgetall(key)
        return raw if raw else None

    # --- Delete ---
    def delete(self, session_id: str) -> None:
        """Remove session state entirely."""
        self._redis.delete(self.session_key(session_id))

    def _get_session_lock(self, session_id: str) -> threading.RLock:
        with self._lock_index_guard:
            lock = self._lock_index.get(session_id)
            if lock is None:
                lock = threading.RLock()
                self._lock_index[session_id] = lock
            return lock

    def _session_dist_lock_key(self, session_id: str) -> str:
        return f"{SESSION_LOCK_KEY_PREFIX}{session_id}"

    def _acquire_dist_lock(self, session_id: str) -> Optional[str]:
        if not self._dist_lock_enabled:
            return None
        token = uuid.uuid4().hex
        lock_key = self._session_dist_lock_key(session_id)
        deadline = time.monotonic() + (self._dist_lock_wait_ms / 1000.0)
        sleep_s = 0.01
        ttl_seconds = max(1, int((self._dist_lock_ttl_ms + 999) / 1000))

        while True:
            acquired = self._redis.set(lock_key, token, ex=ttl_seconds, nx=True)
            if acquired:
                return token
            if time.monotonic() >= deadline:
                logger.warning(
                    "Distributed session lock timeout; fallback to local lock only (session=%s)",
                    session_id,
                )
                return None
            time.sleep(sleep_s)

    def _release_dist_lock(self, session_id: str, token: str) -> None:
        lock_key = self._session_dist_lock_key(session_id)
        try:
            current = self._redis.get(lock_key)
            if isinstance(current, (bytes, bytearray)):
                current = current.decode("utf-8", errors="ignore")
            if current is not None and str(current) == token:
                self._redis.delete(lock_key)
        except Exception:  # noqa: BLE001 - lock release must not break runtime
            logger.exception("Failed to release distributed session lock: %s", session_id)

    def _write_hash(
        self,
        key: str,
        mapping: dict[str, Any],
        *,
        expire_seconds: Optional[int] = None,
    ) -> None:
        if not mapping and expire_seconds is None:
            return

        pipeline_factory = getattr(self._redis, "pipeline", None)
        if callable(pipeline_factory):
            pipe = pipeline_factory(transaction=True)
            if mapping:
                pipe.hset(key, mapping=mapping)
            if expire_seconds is not None:
                pipe.expire(key, expire_seconds)
            pipe.execute()
            return

        if mapping:
            self._redis.hset(key, mapping)
        if expire_seconds is not None:
            self._redis.expire(key, expire_seconds)


def _sanitize_session_state_dict(raw: dict[str, str]) -> dict[str, Any]:
    sanitized: dict[str, Any] = dict(raw)
    sanitized["flowState"] = _safe_flow_state(raw.get("flowState"))
    sanitized["defenseTier"] = _safe_defense_tier(raw.get("defenseTier"))
    sanitized["riskScore"] = _clamp_float(raw.get("riskScore"), 0.0, 1.0, default=0.0)
    sanitized["challengeFailCount"] = _clamp_int(raw.get("challengeFailCount"), minimum=0, default=0)
    sanitized["seatTakenStreak"] = _clamp_int(raw.get("seatTakenStreak"), minimum=0, default=0)
    sanitized["holdFailStreak"] = _clamp_int(raw.get("holdFailStreak"), minimum=0, default=0)
    sanitized["s3Passed"] = _safe_bool_int(raw.get("s3Passed"))

    probation_until_ms = _opt_non_negative_int(raw.get("probationUntilMs"))
    if probation_until_ms is None:
        sanitized.pop("probationUntilMs", None)
    else:
        sanitized["probationUntilMs"] = probation_until_ms

    s3_passed_at_ms = _opt_non_negative_int(raw.get("s3PassedAtMs"))
    if s3_passed_at_ms is None:
        sanitized.pop("s3PassedAtMs", None)
    else:
        sanitized["s3PassedAtMs"] = s3_passed_at_ms

    challenge_halt_until_ms = _opt_non_negative_int(raw.get("challengeHaltUntilMs"))
    if challenge_halt_until_ms is None:
        sanitized.pop("challengeHaltUntilMs", None)
    else:
        sanitized["challengeHaltUntilMs"] = challenge_halt_until_ms

    last_step_risk = _opt_clamped_float(raw.get("lastStepRisk"), 0.0, 1.0)
    if last_step_risk is None:
        sanitized.pop("lastStepRisk", None)
    else:
        sanitized["lastStepRisk"] = last_step_risk

    last_guard_ts_ms = _opt_non_negative_int(raw.get("lastGuardTsMs"))
    if last_guard_ts_ms is None:
        sanitized.pop("lastGuardTsMs", None)
    else:
        sanitized["lastGuardTsMs"] = last_guard_ts_ms

    return sanitized


def _safe_flow_state(value: Any) -> str:
    value_str = str(value or "S0")
    return value_str if value_str in {"S0", "S1", "S2", "S3", "S4", "S5", "S6", "SX"} else "S0"


def _safe_defense_tier(value: Any) -> str:
    value_str = str(value or "T0")
    return value_str if value_str in {"T0", "T1", "T2", "T3"} else "T0"


def _safe_bool_int(value: Any) -> int:
    try:
        return 1 if int(value or 0) > 0 else 0
    except (TypeError, ValueError):
        return 0


def _clamp_int(value: Any, *, minimum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _opt_non_negative_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _clamp_float(value: Any, minimum: float, maximum: float, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _opt_clamped_float(value: Any, minimum: float, maximum: float) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return max(minimum, min(maximum, parsed))
