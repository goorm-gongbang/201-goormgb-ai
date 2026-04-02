"""Policy loader and local policy store for D0-MVP.

Ref: L2/obs_opt/policy_v1.yaml#rollout.storage_contract
     L2/obs_opt/policy_v1.yaml#rollout.assignment
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional, Protocol

from ..core.constants import POLICY_CACHE_SECONDS, POLICY_STORE_FILENAME
from ..state.keyspace import (
    POLICY_ROLLOUT_STATE_KEY,
    POLICY_VERSION_INDEX_KEY,
    POLICY_VERSION_KEY_PREFIX,
)
from ..state.redis_client import InMemoryRedis, RedisLike
from .snapshot import PolicySnapshot

logger = logging.getLogger(__name__)

class PolicyStore(Protocol):
    """Storage backend for policy documents and rollout state."""

    def fetch_policy_by_version(self, version: str) -> Optional[dict[str, Any]]:
        ...

    def get_rollout_state(self) -> Optional[dict[str, Any]]:
        ...

    def save_policy_version(self, version: str, document: dict[str, Any]) -> None:
        ...

    def set_rollout_state(self, state: Optional[dict[str, Any]]) -> None:
        ...

    def list_policy_versions(self) -> list[str]:
        ...


class InMemoryPolicyStore:
    """Simple in-memory policy + rollout store for tests and local use."""

    def __init__(self) -> None:
        self._policies: dict[str, dict[str, Any]] = {}
        self._rollout_state: Optional[dict[str, Any]] = None

    def fetch_policy_by_version(self, version: str) -> Optional[dict[str, Any]]:
        raw = self._policies.get(version)
        if raw is None:
            return None
        return json.loads(json.dumps(raw))

    def get_rollout_state(self) -> Optional[dict[str, Any]]:
        if self._rollout_state is None:
            return None
        return dict(self._rollout_state)

    def save_policy_version(self, version: str, document: dict[str, Any]) -> None:
        self._policies[version] = json.loads(json.dumps(document))

    def set_rollout_state(self, state: Optional[dict[str, Any]]) -> None:
        self._rollout_state = None if state is None else dict(state)

    def list_policy_versions(self) -> list[str]:
        return sorted(self._policies)


class RedisPolicyStore:
    """Redis-first policy store with optional file fallback."""

    def __init__(
        self,
        redis: RedisLike,
        *,
        fallback: Optional[PolicyStore] = None,
    ) -> None:
        self._redis = redis
        self._fallback = fallback

    def fetch_policy_by_version(self, version: str) -> Optional[dict[str, Any]]:
        raw = self._redis.get(self._policy_key(version))
        parsed = _json_object(raw)
        if parsed is not None:
            return parsed
        if self._fallback is None:
            return None
        return self._fallback.fetch_policy_by_version(version)

    def get_rollout_state(self) -> Optional[dict[str, Any]]:
        raw = self._redis.get(POLICY_ROLLOUT_STATE_KEY)
        parsed = _json_object(raw)
        if parsed is not None:
            return parsed
        if self._fallback is None:
            return None
        return self._fallback.get_rollout_state()

    def save_policy_version(self, version: str, document: dict[str, Any]) -> None:
        self._redis.set(
            self._policy_key(version),
            json.dumps(document, ensure_ascii=False, sort_keys=True),
        )
        self._write_version_index(version)
        if self._fallback is not None:
            self._fallback.save_policy_version(version, document)

    def set_rollout_state(self, state: Optional[dict[str, Any]]) -> None:
        if state is None:
            self._redis.delete(POLICY_ROLLOUT_STATE_KEY)
        else:
            self._redis.set(
                POLICY_ROLLOUT_STATE_KEY,
                json.dumps(state, ensure_ascii=False, sort_keys=True),
            )
        if self._fallback is not None:
            self._fallback.set_rollout_state(state)

    def list_policy_versions(self) -> list[str]:
        versions = set(self._read_version_index())
        if self._fallback is not None:
            versions.update(self._fallback.list_policy_versions())
        return sorted(versions)

    def _policy_key(self, version: str) -> str:
        return f"{POLICY_VERSION_KEY_PREFIX}{version}"

    def _read_version_index(self) -> list[str]:
        raw = self._redis.get(POLICY_VERSION_INDEX_KEY)
        parsed = _json_array(raw)
        if parsed is None:
            return []
        return [str(item) for item in parsed if isinstance(item, str)]

    def _write_version_index(self, version: str) -> None:
        versions = self._read_version_index()
        if version not in versions:
            versions.append(version)
        self._redis.set(
            POLICY_VERSION_INDEX_KEY,
            json.dumps(sorted(versions), ensure_ascii=False),
        )


class FilePolicyStore:
    """JSON file-backed policy store.

    MVP implementation of the policy storage contract described in L2 rollout docs.
    """

    def __init__(self, file_path: str = POLICY_STORE_FILENAME) -> None:
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def file_path(self) -> Path:
        return self._path

    def fetch_policy_by_version(self, version: str) -> Optional[dict[str, Any]]:
        payload = self._read_store()
        policies = payload.get("policies")
        if not isinstance(policies, dict):
            return None
        raw = policies.get(version)
        if not isinstance(raw, dict):
            return None
        return raw

    def get_rollout_state(self) -> Optional[dict[str, Any]]:
        payload = self._read_store()
        rollout_state = payload.get("rollout_state")
        if not isinstance(rollout_state, dict):
            return None
        return rollout_state

    def save_policy_version(self, version: str, document: dict[str, Any]) -> None:
        payload = self._read_store()
        policies = payload.setdefault("policies", {})
        if not isinstance(policies, dict):
            policies = {}
            payload["policies"] = policies
        policies[version] = json.loads(json.dumps(document))
        self._write_store(payload)

    def set_rollout_state(self, state: Optional[dict[str, Any]]) -> None:
        payload = self._read_store()
        payload["rollout_state"] = None if state is None else dict(state)
        self._write_store(payload)

    def list_policy_versions(self) -> list[str]:
        payload = self._read_store()
        policies = payload.get("policies")
        if not isinstance(policies, dict):
            return []
        return sorted(str(key) for key in policies.keys())

    def _read_store(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"policies": {}, "rollout_state": None}
        try:
            with self._path.open("r", encoding="utf-8") as f:
                parsed = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read policy store %s", self._path)
            return {"policies": {}, "rollout_state": None}
        if not isinstance(parsed, dict):
            return {"policies": {}, "rollout_state": None}
        parsed.setdefault("policies", {})
        parsed.setdefault("rollout_state", None)
        return parsed

    def _write_store(self, payload: dict[str, Any]) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        tmp_path.replace(self._path)


def resolve_policy_version(
    session_id: str,
    rollout_state: Optional[dict[str, Any]],
    salt: str = "",
) -> str:
    """Deterministically assign a policy version to a session."""
    default_version = PolicySnapshot().policy_version
    if rollout_state is None:
        return default_version

    stage = str(rollout_state.get("stage", "FULL"))
    base = str(rollout_state.get("base_policy_version", default_version))
    candidate_raw = rollout_state.get("candidate_policy_version")
    candidate = str(candidate_raw) if candidate_raw else None

    if stage in {"NONE", "ROLLED_BACK"}:
        return base
    if stage == "FULL":
        return base

    ratio = float(rollout_state.get("ratio", 0.0))
    if not candidate or ratio <= 0.0:
        return base

    h = int(hashlib.sha256(f"{session_id}{salt}".encode("utf-8")).hexdigest(), 16) % 10000
    if h < int(ratio * 10000):
        return candidate
    return base


class PolicyLoader:
    """Resolves the active PolicySnapshot for a session."""

    def __init__(
        self,
        store: Optional[PolicyStore] = None,
        rollout_salt: str = "",
        cache_seconds: int = POLICY_CACHE_SECONDS,
    ) -> None:
        self._store = store or RedisPolicyStore(
            InMemoryRedis(),
            fallback=FilePolicyStore(),
        )
        self._salt = rollout_salt
        self._default = PolicySnapshot()
        self._cache_seconds = max(0, cache_seconds)
        self._rollout_cache_expires_at = 0.0
        self._rollout_cache: Optional[dict[str, Any]] = None
        self._policy_cache: dict[str, tuple[float, PolicySnapshot]] = {}

    @property
    def store(self) -> PolicyStore:
        return self._store

    def load(self, session_id: str) -> PolicySnapshot:
        """Load and validate the active policy for a session."""
        rollout_state = self._get_rollout_state()
        version = resolve_policy_version(session_id, rollout_state, self._salt)

        cached = self._get_cached_policy(version)
        if cached is not None:
            return cached

        raw = self._store.fetch_policy_by_version(version)
        if raw is None:
            return self._default

        try:
            policy = _build_snapshot_from_dict(raw, version)
        except Exception:
            logger.exception("Failed to parse policy %s, using default", version)
            return self._default

        errors = policy.validate()
        if errors:
            logger.warning(
                "Policy %s failed validation: %s — using default", version, errors
            )
            return self._default

        self._remember_policy(version, policy)
        return policy

    def _get_rollout_state(self) -> Optional[dict[str, Any]]:
        if self._cache_seconds <= 0:
            return self._store.get_rollout_state()
        now = time.time()
        if now < self._rollout_cache_expires_at:
            return None if self._rollout_cache is None else dict(self._rollout_cache)
        rollout_state = self._store.get_rollout_state()
        self._rollout_cache = None if rollout_state is None else dict(rollout_state)
        self._rollout_cache_expires_at = now + self._cache_seconds
        return None if self._rollout_cache is None else dict(self._rollout_cache)

    def _get_cached_policy(self, version: str) -> Optional[PolicySnapshot]:
        if self._cache_seconds <= 0:
            return None
        cached = self._policy_cache.get(version)
        if cached is None:
            return None
        expires_at, snapshot = cached
        if time.time() >= expires_at:
            self._policy_cache.pop(version, None)
            return None
        return snapshot

    def _remember_policy(self, version: str, snapshot: PolicySnapshot) -> None:
        if self._cache_seconds <= 0:
            return
        self._policy_cache[version] = (time.time() + self._cache_seconds, snapshot)


def snapshot_to_document(snapshot: PolicySnapshot) -> dict[str, Any]:
    """Serialize one PolicySnapshot into policy_v1-like document structure."""
    return {
        "schemaVersion": "policy.v1",
        "parameters": {
            "risk": {
                "ewma": {"alpha": snapshot.ewma_alpha},
                "decay": {
                    "passive_decay_after_inactive_seconds": snapshot.passive_decay_after_inactive_s,
                    "passive_decay_multiplier_per_tick": snapshot.passive_decay_multiplier,
                    "tick_seconds": snapshot.passive_decay_tick_s,
                },
                "probation": {
                    "probation_seconds_after_s3_pass": snapshot.probation_seconds_after_s3_pass,
                },
            },
            "tiering": {
                "thresholds": {
                    "T0_max": snapshot.t0_max,
                    "T1_max": snapshot.t1_max,
                    "T2_max": snapshot.t2_max,
                },
                "hysteresis": {"margin": snapshot.hysteresis_margin},
            },
            "turnstile": {
                "enabled": snapshot.turnstile_enabled,
                "primary_trigger": "S1_ENTRY_CLICKED",
                "secondary_trigger_enabled": snapshot.turnstile_secondary_trigger_enabled,
                "verify": {
                    "timeout_ms": snapshot.turnstile_verify_timeout_ms,
                    "max_retries": snapshot.turnstile_verify_max_retries,
                    "cache_ttl_seconds": snapshot.turnstile_cache_ttl_s,
                },
                "failure_mode": {
                    "external_score_on_failure": snapshot.turnstile_external_score_on_failure,
                },
                "rate_limits": {
                    "max_runs_per_session": snapshot.turnstile_max_runs_per_session,
                    "cooldown_seconds": snapshot.turnstile_cooldown_seconds,
                },
            },
            "planner": {
                "action_matrix": {
                    "T0": snapshot.action_t0,
                    "T1": snapshot.action_t1,
                    "T2": snapshot.action_t2,
                    "T3": snapshot.action_t3,
                },
                "s3_gate": {
                    "require_s3_for_states": list(snapshot.require_s3_for_states),
                },
            },
            "throttle": {
                "enabled": True,
                "enforcement": "ADAPTER_DELAY_INJECTION",
                "delay_ms": {
                    "T0": snapshot.throttle_delay_ms_t0,
                    "T1": snapshot.throttle_delay_ms_t1,
                    "T2": snapshot.throttle_delay_ms_t2,
                    "T3": snapshot.throttle_delay_ms_t3,
                },
                "max_delay_ms": snapshot.throttle_max_delay_ms,
                "scope": {
                    "mode": "READ_ONLY_PREFERRED",
                    "include_path_prefixes": list(snapshot.throttle_include_path_prefixes),
                    "exclude_path_prefixes": list(snapshot.throttle_exclude_path_prefixes),
                },
                "audit": {
                    "eventType": "DEF_THROTTLE_APPLIED",
                },
            },
            "challenge": {
                "game_id": snapshot.challenge_game_id,
                "ttl_seconds": snapshot.challenge_ttl_seconds,
                "verify_timeout_ms": snapshot.challenge_verify_timeout_ms,
                "success": {
                    "catch_radius_px": snapshot.challenge_catch_radius_px,
                    "timing_window_ms": snapshot.challenge_timing_window_ms,
                },
                "failure_policy": {
                    "max_attempts_per_window": snapshot.challenge_max_attempts,
                    "window_seconds": snapshot.challenge_attempt_window_s,
                    "cooldown_ms": {
                        "first_fail": snapshot.challenge_cooldown_ms_1,
                        "second_fail": snapshot.challenge_cooldown_ms_2,
                    },
                    "on_exceed_max_attempts": {
                        "temporary_lock": {
                            "halt_seconds": snapshot.challenge_halt_seconds,
                        },
                    },
                },
                "grace_period": {"ttl_seconds": snapshot.s3_grace_ttl_seconds},
            },
            "block": {
                "http_status": snapshot.block_http_status,
                "reason_code": snapshot.block_reason_code,
                "ttl_seconds": snapshot.block_ttl_seconds,
            },
        },
        "flags": {
            "runtime_llm_enabled": snapshot.runtime_llm_enabled,
            "dynamic_challenge_enabled": snapshot.dynamic_challenge_enabled,
            "honey_enabled": snapshot.honey_enabled,
            "gate_enabled": snapshot.gate_enabled,
            "sandbox_enabled": snapshot.sandbox_enabled,
            "s3_challenge_fixed": snapshot.s3_challenge_fixed,
        },
    }


def _build_snapshot_from_dict(d: dict[str, Any], version: str) -> PolicySnapshot:
    """Build PolicySnapshot from a raw policy dict."""
    params = d.get("parameters", d)
    risk = params.get("risk", {})
    tiering = params.get("tiering", {})
    turnstile = params.get("turnstile", {})
    planner = params.get("planner", {})
    throttle = params.get("throttle", {})
    challenge = params.get("challenge", {})
    block = params.get("block", {})
    flags = d.get("flags", {})

    thresholds = tiering.get("thresholds", {})
    ewma = risk.get("ewma", {})
    decay = risk.get("decay", {})
    probation = risk.get("probation", {})
    hysteresis = tiering.get("hysteresis", {})
    verify = turnstile.get("verify", {})
    failure_mode = turnstile.get("failure_mode", {})
    turnstile_limits = turnstile.get("rate_limits", {})
    action_matrix = planner.get("action_matrix", {})
    s3_gate = planner.get("s3_gate", {})
    delay_ms = throttle.get("delay_ms", {})
    throttle_scope = throttle.get("scope", {})
    fp = challenge.get("failure_policy", {})
    cooldown = fp.get("cooldown_ms", {})
    success = challenge.get("success", {})
    grace = challenge.get("grace_period", {})

    return PolicySnapshot(
        policy_version=version,
        ewma_alpha=ewma.get("alpha", PolicySnapshot.ewma_alpha),
        passive_decay_after_inactive_s=decay.get(
            "passive_decay_after_inactive_seconds",
            PolicySnapshot.passive_decay_after_inactive_s,
        ),
        passive_decay_multiplier=decay.get(
            "passive_decay_multiplier_per_tick",
            PolicySnapshot.passive_decay_multiplier,
        ),
        passive_decay_tick_s=decay.get("tick_seconds", PolicySnapshot.passive_decay_tick_s),
        probation_seconds_after_s3_pass=probation.get(
            "probation_seconds_after_s3_pass",
            PolicySnapshot.probation_seconds_after_s3_pass,
        ),
        t0_max=thresholds.get("T0_max", PolicySnapshot.t0_max),
        t1_max=thresholds.get("T1_max", PolicySnapshot.t1_max),
        t2_max=thresholds.get("T2_max", PolicySnapshot.t2_max),
        hysteresis_margin=hysteresis.get("margin", PolicySnapshot.hysteresis_margin),
        turnstile_enabled=turnstile.get("enabled", PolicySnapshot.turnstile_enabled),
        turnstile_secondary_trigger_enabled=turnstile.get(
            "secondary_trigger_enabled",
            PolicySnapshot.turnstile_secondary_trigger_enabled,
        ),
        turnstile_verify_timeout_ms=verify.get(
            "timeout_ms", PolicySnapshot.turnstile_verify_timeout_ms
        ),
        turnstile_verify_max_retries=verify.get(
            "max_retries", PolicySnapshot.turnstile_verify_max_retries
        ),
        turnstile_cache_ttl_s=verify.get(
            "cache_ttl_seconds", PolicySnapshot.turnstile_cache_ttl_s
        ),
        turnstile_external_score_on_failure=failure_mode.get(
            "external_score_on_failure",
            PolicySnapshot.turnstile_external_score_on_failure,
        ),
        turnstile_max_runs_per_session=turnstile_limits.get(
            "max_runs_per_session",
            PolicySnapshot.turnstile_max_runs_per_session,
        ),
        turnstile_cooldown_seconds=turnstile_limits.get(
            "cooldown_seconds",
            PolicySnapshot.turnstile_cooldown_seconds,
        ),
        action_t0=action_matrix.get("T0", PolicySnapshot.action_t0),
        action_t1=action_matrix.get("T1", PolicySnapshot.action_t1),
        action_t2=action_matrix.get("T2", PolicySnapshot.action_t2),
        action_t3=action_matrix.get("T3", PolicySnapshot.action_t3),
        require_s3_for_states=tuple(
            s3_gate.get("require_s3_for_states", PolicySnapshot.require_s3_for_states)
        ),
        throttle_delay_ms_t0=delay_ms.get("T0", PolicySnapshot.throttle_delay_ms_t0),
        throttle_delay_ms_t1=delay_ms.get("T1", PolicySnapshot.throttle_delay_ms_t1),
        throttle_delay_ms_t2=delay_ms.get("T2", PolicySnapshot.throttle_delay_ms_t2),
        throttle_delay_ms_t3=delay_ms.get("T3", PolicySnapshot.throttle_delay_ms_t3),
        throttle_max_delay_ms=throttle.get(
            "max_delay_ms", PolicySnapshot.throttle_max_delay_ms
        ),
        throttle_include_path_prefixes=tuple(
            throttle_scope.get(
                "include_path_prefixes",
                PolicySnapshot.throttle_include_path_prefixes,
            )
        ),
        throttle_exclude_path_prefixes=tuple(
            throttle_scope.get(
                "exclude_path_prefixes",
                PolicySnapshot.throttle_exclude_path_prefixes,
            )
        ),
        challenge_game_id=challenge.get("game_id", PolicySnapshot.challenge_game_id),
        challenge_ttl_seconds=challenge.get(
            "ttl_seconds", PolicySnapshot.challenge_ttl_seconds
        ),
        challenge_verify_timeout_ms=challenge.get(
            "verify_timeout_ms", PolicySnapshot.challenge_verify_timeout_ms
        ),
        challenge_catch_radius_px=success.get(
            "catch_radius_px", PolicySnapshot.challenge_catch_radius_px
        ),
        challenge_timing_window_ms=success.get(
            "timing_window_ms", PolicySnapshot.challenge_timing_window_ms
        ),
        challenge_max_attempts=fp.get(
            "max_attempts_per_window", PolicySnapshot.challenge_max_attempts
        ),
        challenge_attempt_window_s=fp.get(
            "window_seconds", PolicySnapshot.challenge_attempt_window_s
        ),
        challenge_cooldown_ms_1=cooldown.get(
            "first_fail", PolicySnapshot.challenge_cooldown_ms_1
        ),
        challenge_cooldown_ms_2=cooldown.get(
            "second_fail", PolicySnapshot.challenge_cooldown_ms_2
        ),
        challenge_halt_seconds=fp.get("on_exceed_max_attempts", {})
        .get("temporary_lock", {})
        .get("halt_seconds", PolicySnapshot.challenge_halt_seconds),
        s3_grace_ttl_seconds=grace.get(
            "ttl_seconds", PolicySnapshot.s3_grace_ttl_seconds
        ),
        block_http_status=block.get("http_status", PolicySnapshot.block_http_status),
        block_reason_code=block.get("reason_code", PolicySnapshot.block_reason_code),
        block_ttl_seconds=block.get("ttl_seconds", PolicySnapshot.block_ttl_seconds),
        runtime_llm_enabled=flags.get("runtime_llm_enabled", False),
        dynamic_challenge_enabled=flags.get("dynamic_challenge_enabled", False),
        honey_enabled=flags.get("honey_enabled", False),
        gate_enabled=flags.get("gate_enabled", False),
        sandbox_enabled=flags.get("sandbox_enabled", False),
        s3_challenge_fixed=flags.get("s3_challenge_fixed", True),
    )


def _json_object(raw: Any) -> Optional[dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None
    if isinstance(raw, dict):
        return dict(raw)
    return None


def _json_array(raw: Any) -> Optional[list[Any]]:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list):
            return list(parsed)
        return None
    if isinstance(raw, list):
        return list(raw)
    return None


__all__ = [
    "PolicyLoader",
    "PolicyStore",
    "InMemoryPolicyStore",
    "RedisPolicyStore",
    "FilePolicyStore",
    "resolve_policy_version",
    "snapshot_to_document",
]
