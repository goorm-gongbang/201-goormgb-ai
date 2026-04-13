from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Mapping, Protocol, Sequence
from uuid import uuid4

from ...backoffice_copilot.storage import (
    POLICY_ROLLOUT_STATE_KEY,
    POLICY_VERSION_INDEX_KEY,
    POLICY_VERSION_KEY_PREFIX,
    OfflineMetricsQuery,
    PolicyRolloutStateRecord,
    PolicyVersionRecord,
    build_redis_projected_policy_document,
    build_redis_projected_rollout_state,
    serialize_redis_projected_policy_document,
    serialize_redis_projected_rollout_state,
)
from ...storage_env import (
    StorageOperationalConfigError,
    load_clickhouse_storage_config_from_env,
    load_postgres_storage_config_from_env,
    load_runtime_policy_config_from_env,
    validate_control_plane_projection_env_for_prod,
    validate_runtime_policy_env_for_prod,
)
from ..policy.loader import FilePolicyStore, PolicyLoader, RedisPolicyStore, snapshot_to_document
from ..policy.snapshot import PolicySnapshot
from ..state.redis_client import RedisLike, build_runtime_redis_from_env
from .audit_summarizer import AuditSummarizer
from .pipeline import OfflineOptimizer

logger = logging.getLogger(__name__)

POLICY_OPTIMIZER_LOCK_KEY = "tm:policy-optimizer:lock"
POLICY_OPTIMIZER_ROLLOUT_ID = "offline-optimizer-default"
DEFAULT_POLICY_OPTIMIZER_LOCK_TTL_SECONDS = 300
_RELEASE_LOCK_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) else return 0 end"
)

PolicyOptimizerWorkerStatus = Literal[
    "disabled",
    "insufficient_data",
    "lock_missed",
    "no_change",
    "proposal_applied",
    "rolled_back",
    "rollout_expanded",
    "rollout_waiting",
    "rollback_cooling_down",
    "rollout_cooling_down",
]


class PolicyOptimizerConfigurationError(StorageOperationalConfigError):
    pass


class PolicyOptimizerLike(Protocol):
    def current_rollout_state(self) -> dict[str, Any] | None:
        ...

    def run_once(self, *, window_seconds: int = 600) -> dict[str, Any]:
        ...

    def start_canary(
        self,
        *,
        proposal: dict[str, Any],
        ratio: float = 0.05,
    ) -> dict[str, Any]:
        ...

    def expand_rollout(self, *, step_index: int) -> dict[str, Any]:
        ...

    def rollback(self, *, reason: str = "manual") -> dict[str, Any]:
        ...

    def collect_metrics(self, *, window_seconds: int = 600) -> dict[str, Any]:
        ...

    def evaluate_guardrails(self, deltas: Mapping[str, float]) -> dict[str, Any]:
        ...


class RolloutGuardrailRepository(Protocol):
    def read_rollout_guardrail_deltas(
        self,
        query: OfflineMetricsQuery,
        *,
        base_policy_version: str,
        candidate_policy_version: str,
    ) -> dict[str, float] | None:
        ...


class PolicyBootstrapAuthority(Protocol):
    version_repository: Any
    rollout_state_repository: Any

    def save_policy_version(
        self,
        record: PolicyVersionRecord,
        *,
        project_to_runtime: bool = False,
    ) -> Any:
        ...

    def save_rollout_state(
        self,
        record: PolicyRolloutStateRecord,
        *,
        additional_policy_versions: Sequence[str] = (),
    ) -> Any:
        ...

    def resync_runtime_projection(
        self,
        *,
        rollout_id: str,
        additional_policy_versions: Sequence[str] = (),
    ) -> Any:
        ...


@dataclass(slots=True, frozen=True)
class PolicyOptimizerWorkerResult:
    status: PolicyOptimizerWorkerStatus
    detail: dict[str, Any]


@dataclass(slots=True, frozen=True)
class PolicyOptimizerStateMachineConfig:
    window_seconds: int
    canary_ratio: float
    min_apply_cooldown_seconds: int
    rollout_id: str


@dataclass(slots=True)
class PolicyOptimizerWorker:
    redis: RedisLike
    optimizer: PolicyOptimizerLike
    lock_ttl_seconds: int
    guardrail_repository: RolloutGuardrailRepository | None = None
    lock_key: str = POLICY_OPTIMIZER_LOCK_KEY
    window_seconds: int = 600
    canary_ratio: float = 0.05
    min_apply_cooldown_seconds: int = 300
    bootstrap_baseline: bool = False
    bootstrap_authority: PolicyBootstrapAuthority | None = None
    rollout_id: str = POLICY_OPTIMIZER_ROLLOUT_ID

    @classmethod
    def from_env(cls) -> PolicyOptimizerWorker:
        _validate_optimizer_storage_env()
        try:
            redis_client, _ = build_runtime_redis_from_env()
        except ValueError as exc:
            raise PolicyOptimizerConfigurationError(str(exc)) from exc
        policy_loader = PolicyLoader.from_env(
            store=_build_policy_store(redis_client),
        )
        config = _load_worker_state_machine_config_from_env()
        metrics_repository = _build_metrics_repository()
        authority_service = _build_authority_service(
            redis_client=redis_client,
            strict_authority=policy_loader.strict_authority,
        )
        bootstrap_baseline = _load_bootstrap_baseline_from_env()
        if bootstrap_baseline and authority_service is None:
            raise PolicyOptimizerConfigurationError(
                "TM_POLICY_OPTIMIZER_BOOTSTRAP_BASELINE requires strict policy authority."
            )
        optimizer = OfflineOptimizer(
            metrics_repository=metrics_repository,
            policy_loader=policy_loader,
            audit_summarizer=AuditSummarizer(),
            authority_service=authority_service,
            rollout_id=config.rollout_id,
        )
        return cls(
            redis=redis_client,
            optimizer=optimizer,
            lock_ttl_seconds=_load_lock_ttl_seconds_from_env(),
            guardrail_repository=metrics_repository,
            window_seconds=config.window_seconds,
            canary_ratio=config.canary_ratio,
            min_apply_cooldown_seconds=config.min_apply_cooldown_seconds,
            bootstrap_baseline=bootstrap_baseline,
            bootstrap_authority=authority_service,
            rollout_id=config.rollout_id,
        )

    def run_once(self) -> PolicyOptimizerWorkerResult:
        token = uuid4().hex
        if not self.redis.set(self.lock_key, token, ex=self.lock_ttl_seconds, nx=True):
            return PolicyOptimizerWorkerResult(
                status="lock_missed",
                detail={"lockKey": self.lock_key},
            )
        try:
            self._bootstrap_baseline_if_enabled()
            return self._reconcile_once()
        finally:
            _release_redis_lock(self.redis, self.lock_key, token)

    def _bootstrap_baseline_if_enabled(self) -> None:
        if not self.bootstrap_baseline:
            return
        if self.bootstrap_authority is None:
            raise PolicyOptimizerConfigurationError(
                "TM_POLICY_OPTIMIZER_BOOTSTRAP_BASELINE requires strict policy authority."
            )

        snapshot = PolicySnapshot()
        baseline_version = snapshot.policy_version
        version_record = self.bootstrap_authority.version_repository.get_version(
            baseline_version
        )
        if version_record is None:
            version_record = _build_baseline_policy_record(snapshot)
            self.bootstrap_authority.save_policy_version(
                version_record,
                project_to_runtime=False,
            )

        rollout_state = self.bootstrap_authority.rollout_state_repository.get_state(
            self.rollout_id
        )
        if rollout_state is None:
            rollout_state = _build_baseline_rollout_state_record(
                rollout_id=self.rollout_id,
                baseline_version=baseline_version,
            )
            self.bootstrap_authority.save_rollout_state(
                rollout_state,
                additional_policy_versions=(baseline_version,),
            )
            return

        if _needs_projection_resync(
            redis=self.redis,
            policy_record=version_record,
            rollout_state=rollout_state,
        ):
            self.bootstrap_authority.resync_runtime_projection(
                rollout_id=self.rollout_id,
                additional_policy_versions=(baseline_version,),
            )

    def _reconcile_once(self) -> PolicyOptimizerWorkerResult:
        current = self.optimizer.current_rollout_state()
        if current is not None:
            active_result = self._reconcile_active_rollout(current)
            if active_result is not None:
                return active_result

        run_result = self.optimizer.run_once(window_seconds=self.window_seconds)
        proposal = run_result.get("proposal")
        if not isinstance(proposal, dict):
            return PolicyOptimizerWorkerResult(
                status="no_change",
                detail={"metricsSnapshotId": run_result.get("metricsSnapshotId")},
            )

        canary_result = self.optimizer.start_canary(
            proposal=proposal,
            ratio=self.canary_ratio,
        )
        return PolicyOptimizerWorkerResult(
            status="proposal_applied",
            detail={
                "metricsSnapshotId": run_result.get("metricsSnapshotId"),
                "candidatePolicyVersion": canary_result.get("candidatePolicyVersion"),
            },
        )

    def _reconcile_active_rollout(
        self,
        current: dict[str, Any],
    ) -> PolicyOptimizerWorkerResult | None:
        stage = str(current.get("stage", "")).upper()
        if stage == "ROLLED_BACK":
            if _cooldown_active(
                current,
                cooldown_seconds=self.min_apply_cooldown_seconds,
            ):
                return PolicyOptimizerWorkerResult(
                    status="rollback_cooling_down",
                    detail={"stage": stage},
                )
            return None
        if stage == "FULL" and current.get("expand_step_index") is not None:
            if _cooldown_active(
                current,
                cooldown_seconds=self.min_apply_cooldown_seconds,
            ):
                return PolicyOptimizerWorkerResult(
                    status="rollout_cooling_down",
                    detail={"stage": stage},
                )
            return None
        if stage not in {"CANARY", "EXPAND"}:
            return None
        if not _is_rollout_stage_elapsed(current):
            return PolicyOptimizerWorkerResult(
                status="rollout_waiting",
                detail={"stage": stage},
            )
        guardrail_result = self._evaluate_rollout_guardrails(current)
        if guardrail_result is None:
            return PolicyOptimizerWorkerResult(
                status="insufficient_data",
                detail={"stage": stage},
            )
        if bool(guardrail_result.get("shouldRollback")):
            rollback_result = self.optimizer.rollback(reason="guardrail")
            return PolicyOptimizerWorkerResult(
                status="rolled_back",
                detail={
                    "stage": rollback_result.get("stage"),
                    "reasons": guardrail_result.get("reasons", []),
                },
            )
        step_index = _next_expand_step_index(current)
        expanded = self.optimizer.expand_rollout(step_index=step_index)
        return PolicyOptimizerWorkerResult(
            status="rollout_expanded",
            detail={
                "stage": expanded.get("stage"),
                "stepIndex": expanded.get("expand_step_index"),
                "basePolicyVersion": expanded.get("base_policy_version"),
                "candidatePolicyVersion": expanded.get("candidate_policy_version"),
            },
        )

    def _evaluate_rollout_guardrails(
        self,
        current: dict[str, Any],
    ) -> dict[str, Any] | None:
        deltas = self._read_rollout_guardrail_deltas(current)
        if deltas is None:
            return None
        return self.optimizer.evaluate_guardrails(deltas)

    def _read_rollout_guardrail_deltas(
        self,
        current: dict[str, Any],
    ) -> dict[str, float] | None:
        base_policy_version = str(current.get("base_policy_version") or "").strip()
        candidate_policy_version = str(
            current.get("candidate_policy_version") or ""
        ).strip()
        if not base_policy_version or not candidate_policy_version:
            return None
        if self.guardrail_repository is None:
            return None
        now_ms = int(time.time() * 1000)
        stage_started_at_ms = _clean_int_value(current.get("stage_started_at_ms"))
        query = OfflineMetricsQuery(
            window_start_ms=max(
                now_ms - (self.window_seconds * 1000),
                stage_started_at_ms,
            ),
            window_end_ms=now_ms,
        )
        return self.guardrail_repository.read_rollout_guardrail_deltas(
            query,
            base_policy_version=base_policy_version,
            candidate_policy_version=candidate_policy_version,
        )


def run_policy_optimizer() -> None:
    if not _load_optimizer_enabled_from_env():
        print("Policy optimizer disabled.")
        return

    try:
        result = PolicyOptimizerWorker.from_env().run_once()
    except PolicyOptimizerConfigurationError as exc:
        logger.error("Policy optimizer configuration invalid: %s", exc)
        raise SystemExit(str(exc)) from exc
    except StorageOperationalConfigError as exc:
        logger.error("Policy optimizer storage configuration invalid: %s", exc)
        raise SystemExit(str(exc)) from exc

    print(f"Policy optimizer completed. status={result.status}")


def _validate_optimizer_storage_env() -> None:
    try:
        validate_runtime_policy_env_for_prod()
        validate_control_plane_projection_env_for_prod()
    except StorageOperationalConfigError as exc:
        raise PolicyOptimizerConfigurationError(str(exc)) from exc

    clickhouse_config = load_clickhouse_storage_config_from_env()
    if not clickhouse_config.enabled:
        raise PolicyOptimizerConfigurationError(
            "TM_CLICKHOUSE_URL must be set to run the policy optimizer worker."
        )
    policy_config = load_runtime_policy_config_from_env()
    postgres_config = load_postgres_storage_config_from_env(required=False)
    if policy_config.strict_authority and not postgres_config.enabled:
        raise PolicyOptimizerConfigurationError(
            "TM_PG_URL must be set to run the policy optimizer worker in strict authority mode."
        )


def _build_policy_store(redis_client: RedisLike) -> RedisPolicyStore:
    policy_config = load_runtime_policy_config_from_env()
    fallback = (
        FilePolicyStore(file_path=policy_config.store_path)
        if policy_config.allow_local_fallback
        else None
    )
    return RedisPolicyStore(redis_client, fallback=fallback)


def _build_metrics_repository() -> Any:
    from ...backoffice_copilot.storage import (
        build_clickhouse_offline_metrics_repository,
        build_clickhouse_read_model_config_from_env,
        build_clickhouse_select_client,
        get_clickhouse_audit_table_from_env,
    )

    read_config = build_clickhouse_read_model_config_from_env()
    return build_clickhouse_offline_metrics_repository(
        build_clickhouse_select_client(read_config),
        table_name=get_clickhouse_audit_table_from_env(),
    )


def _build_authority_service(
    *,
    redis_client: RedisLike,
    strict_authority: bool,
) -> Any | None:
    if not strict_authority:
        return None
    from ...backoffice_copilot.storage import PostgresStrictPolicyAuthorityService

    return PostgresStrictPolicyAuthorityService.from_env(redis_client=redis_client)


def _load_optimizer_enabled_from_env() -> bool:
    return _clean_bool(os.getenv("TM_POLICY_OPTIMIZER_ENABLED"), default=False)


def _load_bootstrap_baseline_from_env() -> bool:
    return _clean_bool(os.getenv("TM_POLICY_OPTIMIZER_BOOTSTRAP_BASELINE"), default=False)


def _load_worker_state_machine_config_from_env() -> PolicyOptimizerStateMachineConfig:
    return PolicyOptimizerStateMachineConfig(
        window_seconds=_load_required_positive_int_env(
            "TM_POLICY_OPTIMIZER_WINDOW_SECONDS"
        ),
        canary_ratio=_load_required_ratio_env("TM_POLICY_OPTIMIZER_CANARY_RATIO"),
        min_apply_cooldown_seconds=_load_required_positive_int_env(
            "TM_POLICY_OPTIMIZER_MIN_APPLY_COOLDOWN_SECONDS"
        ),
        rollout_id=_load_required_text_env("TM_POLICY_OPTIMIZER_ROLLOUT_ID"),
    )


def _load_lock_ttl_seconds_from_env() -> int:
    raw = os.getenv("TM_POLICY_OPTIMIZER_LOCK_TTL_SECONDS")
    if raw is None or not raw.strip():
        return DEFAULT_POLICY_OPTIMIZER_LOCK_TTL_SECONDS
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise PolicyOptimizerConfigurationError(
            "TM_POLICY_OPTIMIZER_LOCK_TTL_SECONDS must be a positive integer."
        ) from exc
    if value <= 0:
        raise PolicyOptimizerConfigurationError(
            "TM_POLICY_OPTIMIZER_LOCK_TTL_SECONDS must be a positive integer."
        )
    return value


def _clean_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_required_positive_int_env(env_name: str) -> int:
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        raise PolicyOptimizerConfigurationError(f"{env_name} must be set.")
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise PolicyOptimizerConfigurationError(
            f"{env_name} must be a positive integer."
        ) from exc
    if value <= 0:
        raise PolicyOptimizerConfigurationError(f"{env_name} must be a positive integer.")
    return value


def _load_required_ratio_env(env_name: str) -> float:
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        raise PolicyOptimizerConfigurationError(f"{env_name} must be set.")
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise PolicyOptimizerConfigurationError(
            f"{env_name} must be greater than 0 and less than or equal to 1."
        ) from exc
    if value <= 0.0 or value > 1.0:
        raise PolicyOptimizerConfigurationError(
            f"{env_name} must be greater than 0 and less than or equal to 1."
        )
    return value


def _load_required_text_env(env_name: str) -> str:
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        raise PolicyOptimizerConfigurationError(f"{env_name} must be set.")
    return raw.strip()


def _release_redis_lock(redis: RedisLike, lock_key: str, token: str) -> None:
    eval_fn = getattr(redis, "eval", None)
    if callable(eval_fn):
        eval_fn(_RELEASE_LOCK_SCRIPT, 1, lock_key, token)
        return
    if redis.get(lock_key) == token:
        redis.delete(lock_key)


def _is_rollout_stage_elapsed(state: dict[str, Any]) -> bool:
    stage_started_at_ms = _clean_int_value(state.get("stage_started_at_ms"))
    stage_duration_seconds = _clean_int_value(state.get("stage_duration_seconds"))
    if stage_started_at_ms <= 0:
        return False
    if stage_duration_seconds <= 0:
        return False
    return int(time.time() * 1000) >= stage_started_at_ms + (stage_duration_seconds * 1000)


def _next_expand_step_index(state: dict[str, Any]) -> int:
    if str(state.get("stage", "")).upper() == "CANARY":
        return 0
    raw_step_index = state.get("expand_step_index")
    if raw_step_index is None:
        return 0
    return _clean_int_value(raw_step_index) + 1


def _clean_int_value(raw: Any) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _cooldown_active(
    state: dict[str, Any],
    *,
    cooldown_seconds: int,
) -> bool:
    finished_at_ms = _clean_int_value(
        state.get("rollout_finished_at_ms") or state.get("updated_at_ms")
    )
    if finished_at_ms <= 0:
        return True
    return int(time.time() * 1000) < finished_at_ms + (cooldown_seconds * 1000)


def _build_baseline_policy_record(snapshot: PolicySnapshot) -> PolicyVersionRecord:
    now = datetime.now(UTC)
    document = snapshot_to_document(snapshot)
    return PolicyVersionRecord(
        policy_version=snapshot.policy_version,
        schema_version=str(document.get("schemaVersion", "policy.v1")),
        status="ACTIVE",
        source_type="BASELINE_BOOTSTRAP",
        document_json=document,
        validation_result_json={"errors": []},
        created_at=now,
        validated_at=now,
        activated_at=now,
    )


def _build_baseline_rollout_state_record(
    *,
    rollout_id: str,
    baseline_version: str,
) -> PolicyRolloutStateRecord:
    now_ms = int(time.time() * 1000)
    return PolicyRolloutStateRecord(
        rollout_id=rollout_id,
        stage="FULL",
        base_policy_version=baseline_version,
        candidate_policy_version=None,
        ratio=Decimal("0.00000"),
        evaluation_window_seconds=60,
        canary_duration_seconds=120,
        expand_step_index=None,
        stage_started_at_ms=now_ms,
        updated_at_ms=now_ms,
        current_status="ACTIVE",
        rollback_reason=None,
    )


def _needs_projection_resync(
    *,
    redis: RedisLike,
    policy_record: PolicyVersionRecord,
    rollout_state: PolicyRolloutStateRecord,
) -> bool:
    if _read_json(redis.get(f"{POLICY_VERSION_KEY_PREFIX}{policy_record.policy_version}")) != dict(
        serialize_redis_projected_policy_document(
            build_redis_projected_policy_document(policy_record)
        )
    ):
        return True
    rollout_payload = _read_json(redis.get(POLICY_ROLLOUT_STATE_KEY))
    if not isinstance(rollout_payload, Mapping):
        return True
    expected_rollout = dict(
        serialize_redis_projected_rollout_state(
            build_redis_projected_rollout_state(rollout_state)
        )
    )
    if _clean_int_value(rollout_payload.get("updated_at_ms")) < rollout_state.updated_at_ms:
        return True
    for key, value in expected_rollout.items():
        if rollout_payload.get(key) != value:
            return True
    version_index = _read_json(redis.get(POLICY_VERSION_INDEX_KEY))
    return not isinstance(version_index, list) or policy_record.policy_version not in version_index


def _read_json(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str):
        return raw

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
