"""PostgreSQL -> Redis runtime policy projection helpers and write repository."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
import time
from typing import Any, Protocol, Sequence

from ...d0_mvp.state.redis_client import RedisLike, build_runtime_redis_from_env
from .connection import build_postgres_engine_from_env
from ...storage_env import (
    load_projection_sync_config_from_env,
    validate_control_plane_projection_env_for_prod,
)
from .policy_control_plane_models import (
    PolicyOptimizationRunRecord,
    PolicyRolloutEventRecord,
    PolicyRolloutStateRecord,
    PolicyVersionRecord,
)
from .policy_control_plane_repository import (
    PolicyOptimizationRunRepository,
    PolicyRolloutEventRepository,
    PolicyRolloutStateRepository,
    PolicyVersionRepository,
    PostgresPolicyOptimizationRunRepository,
    PostgresPolicyRolloutEventRepository,
    PostgresPolicyRolloutStateRepository,
    PostgresPolicyVersionRepository,
)
from .policy_projection_models import (
    PolicyProjectionApplyResult,
    PolicyRuntimeProjectionInput,
    RedisProjectedPolicyDocument,
    RedisProjectedRolloutState,
    build_redis_projected_policy_document,
    build_redis_projected_rollout_state,
    derive_projected_version_index,
    serialize_redis_projected_policy_document,
    serialize_redis_projected_rollout_state,
    serialize_redis_projected_version_index,
    validate_policy_runtime_projection_input,
)

logger = logging.getLogger(__name__)

# Canonical source: src/traffic_master_ai/defense/d0_mvp/state/keyspace.py
POLICY_VERSION_KEY_PREFIX = "tm:decision-policy:version:"
POLICY_ROLLOUT_STATE_KEY = "tm:decision-policy:rollout-state"
POLICY_VERSION_INDEX_KEY = "tm:decision-policy:version-index"


class PolicyProjectionNotFoundError(LookupError):
    """Raised when PostgreSQL authoritative rows required for projection are missing."""


class RedisProjectionApplyError(RuntimeError):
    """Raised when PostgreSQL -> Redis projection cannot be fully applied."""

    def __init__(
        self,
        *,
        scope: str,
        max_attempts: int,
    ) -> None:
        self.scope = scope
        self.max_attempts = max_attempts
        self.resync_hint = (
            "Repair runtime Redis keys by retrying the same projection call or running "
            "reconcile_policy_runtime_projection(...) from PostgreSQL authoritative rows."
        )
        super().__init__(
            "Redis runtime projection apply failed "
            f"(scope={scope}, max_attempts={max_attempts}). {self.resync_hint}"
        )


@dataclass(slots=True, frozen=True)
class ProjectionRetryPolicy:
    """Minimal retry surface for PostgreSQL -> Redis projection apply."""

    max_attempts: int = 1
    backoff_ms: int = 0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1.")
        if self.backoff_ms < 0:
            raise ValueError("backoff_ms must be >= 0.")


class RedisPolicyProjectionClient(Protocol):
    """Minimal Redis JSON write surface used by the projection layer."""

    def set(self, name: str, value: object, ex: int | None = None, nx: bool = False) -> bool:
        """Store one JSON-serializable value."""

    def get(self, name: str) -> object | None:
        """Read one raw Redis value."""

    def delete(self, *names: str) -> int:
        """Delete one or more keys."""


class RedisPolicyProjectionRepository(Protocol):
    """Redis write boundary for runtime policy projection only."""

    def project_policy_version(
        self,
        *,
        policy_version: str,
        payload: RedisProjectedPolicyDocument,
    ) -> None:
        """Project one runtime-readable policy document to Redis."""

    def project_rollout_state(self, payload: RedisProjectedRolloutState) -> None:
        """Project one runtime-readable rollout-state payload to Redis."""

    def clear_rollout_state(self) -> None:
        """Delete the runtime rollout-state projection."""

    def project_version_index(self, versions: Sequence[str]) -> tuple[str, ...]:
        """Project the version inventory helper key and return the stored list."""

    def read_version_index(self) -> tuple[str, ...]:
        """Read the currently projected version inventory helper key."""


@dataclass(slots=True)
class PostgresStrictPolicyAuthorityService:
    """Thin authoritative write + Redis projection sync surface.

    Explicit non-goals:
    - no rollout assignment algorithm
    - no PostgreSQL direct read in runtime request path
    - no scheduler/orchestrator ownership
    """

    version_repository: PolicyVersionRepository
    rollout_state_repository: PolicyRolloutStateRepository
    rollout_event_repository: PolicyRolloutEventRepository
    optimization_run_repository: PolicyOptimizationRunRepository
    projection_repository: RedisPolicyProjectionRepository
    projection_retry_policy: ProjectionRetryPolicy = field(
        default_factory=ProjectionRetryPolicy
    )

    @classmethod
    def from_env(
        cls,
        *,
        redis_client: RedisLike | None = None,
        projection_retry_policy: ProjectionRetryPolicy | None = None,
    ) -> "PostgresStrictPolicyAuthorityService":
        validate_control_plane_projection_env_for_prod()
        engine = build_postgres_engine_from_env()
        runtime_redis = redis_client
        if runtime_redis is None:
            runtime_redis, _ = build_runtime_redis_from_env()
        retry_config = load_projection_sync_config_from_env()
        return cls(
            version_repository=PostgresPolicyVersionRepository(engine),
            rollout_state_repository=PostgresPolicyRolloutStateRepository(engine),
            rollout_event_repository=PostgresPolicyRolloutEventRepository(engine),
            optimization_run_repository=PostgresPolicyOptimizationRunRepository(engine),
            projection_repository=RedisRuntimePolicyProjectionRepository(runtime_redis),
            projection_retry_policy=projection_retry_policy
            or ProjectionRetryPolicy(
                max_attempts=retry_config.retry_max_attempts,
                backoff_ms=retry_config.retry_backoff_ms,
            ),
        )

    def save_policy_version(
        self,
        record: PolicyVersionRecord,
        *,
        project_to_runtime: bool = False,
    ) -> PolicyProjectionApplyResult | None:
        self.version_repository.save_version(record)
        if not project_to_runtime:
            return None
        return project_policy_version_activation(
            policy_version=record.policy_version,
            version_repository=self.version_repository,
            projection_repository=self.projection_repository,
            retry_policy=self.projection_retry_policy,
        )

    def save_rollout_state(
        self,
        record: PolicyRolloutStateRecord,
        *,
        additional_policy_versions: Sequence[str] = (),
    ) -> PolicyProjectionApplyResult:
        self.rollout_state_repository.save_state(record)
        return project_rollout_state_change(
            rollout_id=record.rollout_id,
            version_repository=self.version_repository,
            rollout_state_repository=self.rollout_state_repository,
            projection_repository=self.projection_repository,
            additional_policy_versions=additional_policy_versions,
            retry_policy=self.projection_retry_policy,
        )

    def append_rollout_event(self, record: PolicyRolloutEventRecord) -> None:
        self.rollout_event_repository.append_event(record)

    def save_optimization_run(self, record: PolicyOptimizationRunRecord) -> None:
        self.optimization_run_repository.save_run(record)

    def sync_runtime_projection(
        self,
        *,
        rollout_id: str,
        additional_policy_versions: Sequence[str] = (),
    ) -> PolicyProjectionApplyResult:
        return project_rollout_state_change(
            rollout_id=rollout_id,
            version_repository=self.version_repository,
            rollout_state_repository=self.rollout_state_repository,
            projection_repository=self.projection_repository,
            additional_policy_versions=additional_policy_versions,
            retry_policy=self.projection_retry_policy,
        )

    def resync_runtime_projection(
        self,
        *,
        rollout_id: str,
        additional_policy_versions: Sequence[str] = (),
    ) -> PolicyProjectionApplyResult:
        return reconcile_policy_runtime_projection(
            rollout_id=rollout_id,
            version_repository=self.version_repository,
            rollout_state_repository=self.rollout_state_repository,
            projection_repository=self.projection_repository,
            additional_policy_versions=additional_policy_versions,
            retry_policy=self.projection_retry_policy,
        )


def run_runtime_projection_sync_from_env(
    *,
    rollout_id: str,
    additional_policy_versions: Sequence[str] = (),
) -> PolicyProjectionApplyResult:
    """Operational sync entry point using shared TM_* env settings."""

    service = PostgresStrictPolicyAuthorityService.from_env()
    return service.sync_runtime_projection(
        rollout_id=rollout_id,
        additional_policy_versions=additional_policy_versions,
    )


def run_runtime_projection_resync_from_env(
    *,
    rollout_id: str,
    additional_policy_versions: Sequence[str] = (),
) -> PolicyProjectionApplyResult:
    """Operational resync entry point using shared TM_* env settings."""

    service = PostgresStrictPolicyAuthorityService.from_env()
    return service.resync_runtime_projection(
        rollout_id=rollout_id,
        additional_policy_versions=additional_policy_versions,
    )


@dataclass(slots=True)
class RedisRuntimePolicyProjectionRepository:
    """Redis repository for runtime policy projection keys only.

    Explicit non-goals:
    - no authoritative history storage
    - no rollout assignment or fallback policy decision
    - no PostgreSQL reads
    """

    client: RedisPolicyProjectionClient

    def _set_required(self, key: str, payload_json: str) -> None:
        result = self.client.set(key, payload_json)
        if result is False:
            raise RuntimeError(f"Redis projection write returned False for key={key}.")

    def project_policy_version(
        self,
        *,
        policy_version: str,
        payload: RedisProjectedPolicyDocument,
    ) -> None:
        self._set_required(
            self._policy_version_key(policy_version),
            json.dumps(
                serialize_redis_projected_policy_document(payload),
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    def project_rollout_state(self, payload: RedisProjectedRolloutState) -> None:
        self._set_required(
            POLICY_ROLLOUT_STATE_KEY,
            json.dumps(
                serialize_redis_projected_rollout_state(payload),
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    def clear_rollout_state(self) -> None:
        self.client.delete(POLICY_ROLLOUT_STATE_KEY)

    def project_version_index(self, versions: Sequence[str]) -> tuple[str, ...]:
        serialized = tuple(serialize_redis_projected_version_index(versions))
        self._set_required(
            POLICY_VERSION_INDEX_KEY,
            json.dumps(list(serialized), ensure_ascii=False),
        )
        return serialized

    def read_version_index(self) -> tuple[str, ...]:
        raw = self.client.get(POLICY_VERSION_INDEX_KEY)
        parsed = _json_array(raw)
        if parsed is None:
            return ()
        return tuple(version for version in parsed if isinstance(version, str) and version)

    def _policy_version_key(self, policy_version: str) -> str:
        if not policy_version:
            raise ValueError("policy_version must be a non-empty string.")
        return f"{POLICY_VERSION_KEY_PREFIX}{policy_version}"


def load_policy_runtime_projection_input(
    *,
    rollout_id: str,
    version_repository: PolicyVersionRepository,
    rollout_state_repository: PolicyRolloutStateRepository,
    additional_policy_versions: Sequence[str] = (),
) -> PolicyRuntimeProjectionInput:
    """Load the minimum authoritative PG rows required for one rollout projection apply."""

    rollout_state = rollout_state_repository.get_state(rollout_id)
    if rollout_state is None:
        raise PolicyProjectionNotFoundError(
            f"policy_rollout_state row not found for rollout_id={rollout_id!r}."
        )

    version_ids = list(additional_policy_versions)
    version_ids.append(rollout_state.base_policy_version)
    if rollout_state.candidate_policy_version is not None:
        version_ids.append(rollout_state.candidate_policy_version)

    policy_versions = []
    for policy_version in serialize_redis_projected_version_index(version_ids):
        record = version_repository.get_version(policy_version)
        if record is None:
            raise PolicyProjectionNotFoundError(
                f"policy_versions row not found for policy_version={policy_version!r}."
            )
        policy_versions.append(record)

    return validate_policy_runtime_projection_input(
        PolicyRuntimeProjectionInput(
            policy_versions=tuple(policy_versions),
            rollout_state=rollout_state,
        )
    )


def apply_policy_runtime_projection(
    projection_input: PolicyRuntimeProjectionInput,
    *,
    projection_repository: RedisPolicyProjectionRepository,
) -> PolicyProjectionApplyResult:
    """Apply one projection bundle in document -> rollout -> index order."""

    validated = validate_policy_runtime_projection_input(projection_input)
    existing_index = projection_repository.read_version_index()

    for record in validated.policy_versions:
        projection_repository.project_policy_version(
            policy_version=record.policy_version,
            payload=build_redis_projected_policy_document(record),
        )

    wrote_rollout_state = False
    if validated.rollout_state is not None:
        projection_repository.project_rollout_state(
            build_redis_projected_rollout_state(validated.rollout_state)
        )
        wrote_rollout_state = True

    version_index = projection_repository.project_version_index(
        derive_projected_version_index(
            existing_versions=existing_index,
            projection_input=validated,
        )
    )

    return PolicyProjectionApplyResult(
        projected_policy_versions=tuple(
            record.policy_version for record in validated.policy_versions
        ),
        version_index=version_index,
        wrote_rollout_state=wrote_rollout_state,
    )


def apply_policy_runtime_projection_with_retry(
    projection_input: PolicyRuntimeProjectionInput,
    *,
    projection_repository: RedisPolicyProjectionRepository,
    retry_policy: ProjectionRetryPolicy,
    scope: str,
) -> PolicyProjectionApplyResult:
    """Apply one projection bundle with minimal retry and explicit resync surfacing."""

    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            return apply_policy_runtime_projection(
                projection_input,
                projection_repository=projection_repository,
            )
        except Exception as exc:
            logger.exception(
                "Redis runtime projection apply failed for scope=%s attempt=%s/%s",
                scope,
                attempt,
                retry_policy.max_attempts,
            )
            if attempt < retry_policy.max_attempts and retry_policy.backoff_ms > 0:
                time.sleep(retry_policy.backoff_ms / 1000.0)
            last_exc = exc
    raise RedisProjectionApplyError(
        scope=scope,
        max_attempts=retry_policy.max_attempts,
    ) from last_exc


def project_policy_version_activation(
    *,
    policy_version: str,
    version_repository: PolicyVersionRepository,
    projection_repository: RedisPolicyProjectionRepository,
    retry_policy: ProjectionRetryPolicy | None = None,
) -> PolicyProjectionApplyResult:
    """Projection trigger for a runtime-readable policy version activation/write."""

    record = version_repository.get_version(policy_version)
    if record is None:
        raise PolicyProjectionNotFoundError(
            f"policy_versions row not found for policy_version={policy_version!r}."
        )

    projection_input = PolicyRuntimeProjectionInput(policy_versions=(record,))
    try:
        return apply_policy_runtime_projection_with_retry(
            projection_input,
            projection_repository=projection_repository,
            retry_policy=retry_policy or ProjectionRetryPolicy(),
            scope=f"policy_version:{policy_version}",
        )
    except Exception:
        logger.exception(
            "Policy version projection failed for policy_version=%s",
            policy_version,
        )
        raise


def project_rollout_state_change(
    *,
    rollout_id: str,
    version_repository: PolicyVersionRepository,
    rollout_state_repository: PolicyRolloutStateRepository,
    projection_repository: RedisPolicyProjectionRepository,
    additional_policy_versions: Sequence[str] = (),
    retry_policy: ProjectionRetryPolicy | None = None,
) -> PolicyProjectionApplyResult:
    """Projection trigger for current rollout-state changes.

    This keeps runtime on Redis only: load PG rows here, then write Redis keys in order.
    """

    projection_input = load_policy_runtime_projection_input(
        rollout_id=rollout_id,
        version_repository=version_repository,
        rollout_state_repository=rollout_state_repository,
        additional_policy_versions=additional_policy_versions,
    )
    try:
        return apply_policy_runtime_projection_with_retry(
            projection_input,
            projection_repository=projection_repository,
            retry_policy=retry_policy or ProjectionRetryPolicy(),
            scope=f"rollout_id:{rollout_id}",
        )
    except Exception:
        logger.exception(
            "Rollout-state projection failed for rollout_id=%s",
            rollout_id,
        )
        raise


def reconcile_policy_runtime_projection(
    *,
    rollout_id: str,
    version_repository: PolicyVersionRepository,
    rollout_state_repository: PolicyRolloutStateRepository,
    projection_repository: RedisPolicyProjectionRepository,
    additional_policy_versions: Sequence[str] = (),
    retry_policy: ProjectionRetryPolicy | None = None,
) -> PolicyProjectionApplyResult:
    """Minimal helper for stale/evicted Redis projection re-sync."""

    return project_rollout_state_change(
        rollout_id=rollout_id,
        version_repository=version_repository,
        rollout_state_repository=rollout_state_repository,
        projection_repository=projection_repository,
        additional_policy_versions=additional_policy_versions,
        retry_policy=retry_policy,
    )


def _json_array(raw: Any) -> list[object] | None:
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
            return parsed
        return None
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, tuple):
        return list(raw)
    return None
