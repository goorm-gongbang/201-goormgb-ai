from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import uuid4

from ...backoffice_copilot.storage import PolicyProjectionApplyResult
from ...storage_env import (
    load_postgres_storage_config_from_env,
    load_runtime_redis_config_from_env,
)
from ..state.redis_client import RedisLike

logger = logging.getLogger(__name__)

POLICY_PROJECTION_RECONCILER_LOCK_KEY = "tm:policy-projection-reconciler:lock"
DEFAULT_POLICY_PROJECTION_RECONCILER_INTERVAL_SECONDS = 60
DEFAULT_POLICY_PROJECTION_RECONCILER_LOCK_TTL_SECONDS = 55
_RELEASE_LOCK_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) else return 0 end"
)

PolicyProjectionReconcilerStatus = Literal["refreshed", "lock_missed"]


class PolicyProjectionAuthority(Protocol):
    def refresh_current_runtime_projection(self) -> PolicyProjectionApplyResult:
        ...


@dataclass(slots=True, frozen=True)
class PolicyProjectionReconcilerConfig:
    enabled: bool
    interval_seconds: int = DEFAULT_POLICY_PROJECTION_RECONCILER_INTERVAL_SECONDS
    lock_ttl_seconds: int = DEFAULT_POLICY_PROJECTION_RECONCILER_LOCK_TTL_SECONDS
    lock_key: str = POLICY_PROJECTION_RECONCILER_LOCK_KEY


@dataclass(slots=True, frozen=True)
class PolicyProjectionReconcilerResult:
    status: PolicyProjectionReconcilerStatus
    detail: dict[str, Any]
    projection_result: PolicyProjectionApplyResult | None = None


@dataclass(slots=True)
class PolicyProjectionReconciler:
    redis: RedisLike
    authority_service: PolicyProjectionAuthority
    config: PolicyProjectionReconcilerConfig

    def reconcile_once(self) -> PolicyProjectionReconcilerResult:
        token = uuid4().hex
        if not self.redis.set(
            self.config.lock_key,
            token,
            ex=self.config.lock_ttl_seconds,
            nx=True,
        ):
            return PolicyProjectionReconcilerResult(
                status="lock_missed",
                detail={"lockKey": self.config.lock_key},
            )
        try:
            result = self.authority_service.refresh_current_runtime_projection()
            return PolicyProjectionReconcilerResult(
                status="refreshed",
                detail={"lockKey": self.config.lock_key},
                projection_result=result,
            )
        finally:
            _release_redis_lock(self.redis, self.config.lock_key, token)


def load_policy_projection_reconciler_config_from_env(
    *,
    strict_authority: bool,
    redis_backend: str,
) -> PolicyProjectionReconcilerConfig:
    interval_seconds = _clean_positive_int(
        os.getenv("TM_POLICY_PROJECTION_RECONCILER_INTERVAL_SECONDS"),
        default=DEFAULT_POLICY_PROJECTION_RECONCILER_INTERVAL_SECONDS,
        env_name="TM_POLICY_PROJECTION_RECONCILER_INTERVAL_SECONDS",
    )
    lock_ttl_seconds = _clean_positive_int(
        os.getenv("TM_POLICY_PROJECTION_RECONCILER_LOCK_TTL_SECONDS"),
        default=min(DEFAULT_POLICY_PROJECTION_RECONCILER_LOCK_TTL_SECONDS, interval_seconds),
        env_name="TM_POLICY_PROJECTION_RECONCILER_LOCK_TTL_SECONDS",
    )
    disabled = _clean_bool(
        os.getenv("TM_POLICY_PROJECTION_RECONCILER_DISABLED"),
        default=False,
        env_name="TM_POLICY_PROJECTION_RECONCILER_DISABLED",
    )
    postgres_config = load_postgres_storage_config_from_env(required=False)
    redis_config = load_runtime_redis_config_from_env()
    enabled = (
        not disabled
        and strict_authority
        and postgres_config.enabled
        and bool(redis_config.redis_url)
        and redis_backend == "redis"
    )
    return PolicyProjectionReconcilerConfig(
        enabled=enabled,
        interval_seconds=interval_seconds,
        lock_ttl_seconds=lock_ttl_seconds,
    )


def _release_redis_lock(redis: RedisLike, lock_key: str, token: str) -> None:
    try:
        eval_fn = getattr(redis, "eval", None)
        if callable(eval_fn):
            eval_fn(_RELEASE_LOCK_SCRIPT, 1, lock_key, token)
            return
        current = redis.get(lock_key)
        if isinstance(current, (bytes, bytearray)):
            current = current.decode("utf-8", errors="ignore")
        if current is not None and str(current) == token:
            redis.delete(lock_key)
    except Exception:
        logger.exception("Failed to release policy projection reconciler lock.")


def _clean_positive_int(raw: str | None, *, default: int, env_name: str) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{env_name} must be a positive integer.") from exc
    if value <= 0:
        raise ValueError(f"{env_name} must be a positive integer.")
    return value


def _clean_bool(raw: str | None, *, default: bool, env_name: str) -> bool:
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{env_name} must be a boolean.")
