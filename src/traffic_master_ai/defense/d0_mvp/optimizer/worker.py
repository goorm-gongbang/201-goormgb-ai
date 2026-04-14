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
    DEFAULT_POLICY_OPTIMIZER_LOCK_TTL_SECONDS,
    DEFAULT_POLICY_OPTIMIZER_ROLLOUT_ID,
    StorageOperationalConfigError,
    load_clickhouse_storage_config_from_env,
    load_policy_optimizer_config_from_env,
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
POLICY_OPTIMIZER_ROLLOUT_ID = DEFAULT_POLICY_OPTIMIZER_ROLLOUT_ID
_RELEASE_LOCK_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) else return 0 end"
)

PolicyOptimizerWorkerStatus = Literal[
    "apply_blocked",
    "disabled",
    "failed",
    "insufficient_data",
    "lock_missed",
    "metrics_read_failed",
    "no_active_rollout",
    "no_candidate_or_no_baseline",
    "no_change",
    "projection_not_ready",
    "proposal_applied",
    "rolled_back",
    "rollout_expanded",
    "rollout_waiting",
    "rollback_cooling_down",
    "rollout_cooling_down",
    "dry_run",
]


class PolicyOptimizerConfigurationError(StorageOperationalConfigError):
    pass


class PolicyOptimizerPostCheckError(RuntimeError):
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
    dry_run: bool = False
    apply_enabled: bool = False

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
        config = load_policy_optimizer_config_from_env()
        metrics_repository = _build_metrics_repository()
        authority_service = _build_authority_service(
            redis_client=redis_client,
            strict_authority=policy_loader.strict_authority,
        )
        if config.bootstrap_baseline and authority_service is None:
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
            lock_ttl_seconds=config.lock_ttl_seconds,
            guardrail_repository=metrics_repository,
            window_seconds=config.window_seconds,
            canary_ratio=config.canary_ratio,
            min_apply_cooldown_seconds=config.min_apply_cooldown_seconds,
            bootstrap_baseline=config.bootstrap_baseline,
            bootstrap_authority=authority_service,
            rollout_id=config.rollout_id,
            dry_run=config.dry_run,
            apply_enabled=config.apply_enabled,
        )

    def run_once(self) -> PolicyOptimizerWorkerResult:
        token = uuid4().hex
        if not self.redis.set(self.lock_key, token, ex=self.lock_ttl_seconds, nx=True):
            return PolicyOptimizerWorkerResult(
                status="lock_missed",
                detail={"lockKey": self.lock_key},
            )
        try:
            if self.dry_run:
                return self._dry_run_once()
            if not self.apply_enabled:
                return PolicyOptimizerWorkerResult(
                    status="apply_blocked",
                    detail={
                        "reason": "TM_POLICY_OPTIMIZER_APPLY_ENABLED must be true when TM_POLICY_OPTIMIZER_DRY_RUN=false.",
                        "applyEnabled": False,
                        "attemptedAction": None,
                        "appliedAction": None,
                        "verificationStatus": "not_checked",
                    },
                )
            self._bootstrap_baseline_if_enabled()
            precondition = self._check_apply_preconditions()
            if precondition is not None:
                return precondition
            return self._reconcile_once()
        finally:
            _release_redis_lock(self.redis, self.lock_key, token)

    def _dry_run_once(self) -> PolicyOptimizerWorkerResult:
        current = self.optimizer.current_rollout_state()
        if current is None:
            metrics = self.optimizer.collect_metrics(window_seconds=self.window_seconds)
            return PolicyOptimizerWorkerResult(
                status="dry_run",
                detail={
                    "wouldStatus": "collect_metrics_only",
                    "windowSeconds": self.window_seconds,
                    "metricKeys": sorted(str(key) for key in metrics.keys()),
                    "applyEnabled": False,
                    "bootstrapSkipped": self.bootstrap_baseline,
                },
            )
        stage = str(current.get("stage", "")).upper()
        if stage in {"CANARY", "EXPAND"}:
            if not _is_rollout_stage_elapsed(current):
                return PolicyOptimizerWorkerResult(
                    status="dry_run",
                    detail={
                        "wouldStatus": "rollout_waiting",
                        "stage": stage,
                        "applyEnabled": False,
                    },
                )
            deltas = self._read_rollout_guardrail_deltas(current)
            if deltas is None:
                return PolicyOptimizerWorkerResult(
                    status="dry_run",
                    detail={
                        "wouldStatus": "insufficient_data",
                        "stage": stage,
                        "applyEnabled": False,
                    },
                )
            guardrail_result = self.optimizer.evaluate_guardrails(deltas)
            if bool(guardrail_result.get("shouldRollback")):
                return PolicyOptimizerWorkerResult(
                    status="dry_run",
                    detail={
                        "wouldStatus": "rolled_back",
                        "stage": stage,
                        "reasons": guardrail_result.get("reasons", []),
                        "applyEnabled": False,
                    },
                )
            return PolicyOptimizerWorkerResult(
                status="dry_run",
                detail={
                    "wouldStatus": "rollout_expanded",
                    "stage": stage,
                    "stepIndex": _next_expand_step_index(current),
                    "applyEnabled": False,
                },
            )
        return PolicyOptimizerWorkerResult(
            status="dry_run",
            detail={
                "wouldStatus": "no_mutation",
                "stage": stage,
                "applyEnabled": False,
            },
        )

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
        if current is None:
            return PolicyOptimizerWorkerResult(
                status="no_active_rollout",
                detail={
                    "reason": "active rollout state is required before auto-apply.",
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "not_checked",
                },
            )
        active_result = self._reconcile_active_rollout(current)
        if active_result is not None:
            return active_result
        return self._start_new_canary()

    def _start_new_canary(self) -> PolicyOptimizerWorkerResult:
        try:
            run_result = self.optimizer.run_once(window_seconds=self.window_seconds)
        except Exception as exc:
            return PolicyOptimizerWorkerResult(
                status="metrics_read_failed",
                detail={
                    "reason": str(exc),
                    "errorType": type(exc).__name__,
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": "canary_start",
                    "appliedAction": None,
                    "verificationStatus": "not_checked",
                },
            )
        proposal = run_result.get("proposal")
        if not isinstance(proposal, dict):
            return PolicyOptimizerWorkerResult(
                status="no_change",
                detail={
                    "metricsSnapshotId": run_result.get("metricsSnapshotId"),
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "not_checked",
                },
            )

        before_projection = _read_projected_rollout_state(self.redis)
        canary_result = self.optimizer.start_canary(
            proposal=proposal,
            ratio=self.canary_ratio,
        )
        try:
            verification = self._verify_apply_post_check(
                attempted_action="canary_start",
                expected_stage="CANARY",
                before_projection=before_projection,
            )
        except PolicyOptimizerPostCheckError as exc:
            return PolicyOptimizerWorkerResult(
                status="failed",
                detail={
                    "reason": str(exc),
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": "canary_start",
                    "appliedAction": "canary_start",
                    "verificationStatus": "failed",
                },
            )
        return PolicyOptimizerWorkerResult(
            status="proposal_applied",
            detail={
                "metricsSnapshotId": run_result.get("metricsSnapshotId"),
                "candidatePolicyVersion": canary_result.get("candidatePolicyVersion"),
                "applyEnabled": self.apply_enabled,
                "attemptedAction": "canary_start",
                "appliedAction": "canary_start",
                "verificationStatus": "success",
                "verification": verification,
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
                    detail={
                        "stage": stage,
                        "applyEnabled": self.apply_enabled,
                        "attemptedAction": None,
                        "appliedAction": None,
                        "verificationStatus": "not_checked",
                    },
                )
            return None
        if stage == "FULL" and current.get("expand_step_index") is not None:
            if _cooldown_active(
                current,
                cooldown_seconds=self.min_apply_cooldown_seconds,
            ):
                return PolicyOptimizerWorkerResult(
                    status="rollout_cooling_down",
                    detail={
                        "stage": stage,
                        "applyEnabled": self.apply_enabled,
                        "attemptedAction": None,
                        "appliedAction": None,
                        "verificationStatus": "not_checked",
                    },
                )
            return None
        if stage not in {"CANARY", "EXPAND"}:
            return None
        if not _has_required_rollout_versions(current):
            return PolicyOptimizerWorkerResult(
                status="no_candidate_or_no_baseline",
                detail={
                    "stage": stage,
                    "reason": "active rollout is missing base or candidate policy version.",
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "not_checked",
                },
            )
        if not _is_rollout_stage_elapsed(current):
            return PolicyOptimizerWorkerResult(
                status="rollout_waiting",
                detail={
                    "stage": stage,
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "not_checked",
                },
            )
        try:
            guardrail_result = self._evaluate_rollout_guardrails(current)
        except Exception as exc:
            return PolicyOptimizerWorkerResult(
                status="metrics_read_failed",
                detail={
                    "stage": stage,
                    "reason": str(exc),
                    "errorType": type(exc).__name__,
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "not_checked",
                },
            )
        if guardrail_result is None:
            return PolicyOptimizerWorkerResult(
                status="insufficient_data",
                detail={
                    "stage": stage,
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "not_checked",
                },
            )
        before_projection = _read_projected_rollout_state(self.redis)
        if bool(guardrail_result.get("shouldRollback")):
            rollback_result = self.optimizer.rollback(reason="guardrail")
            try:
                verification = self._verify_apply_post_check(
                    attempted_action="rollback",
                    expected_stage="ROLLED_BACK",
                    before_projection=before_projection,
                )
            except PolicyOptimizerPostCheckError as exc:
                return PolicyOptimizerWorkerResult(
                    status="failed",
                    detail={
                        "stage": rollback_result.get("stage"),
                        "reasons": guardrail_result.get("reasons", []),
                        "guardrailResult": guardrail_result,
                        "reason": str(exc),
                        "applyEnabled": self.apply_enabled,
                        "attemptedAction": "rollback",
                        "appliedAction": "rollback",
                        "verificationStatus": "failed",
                    },
                )
            return PolicyOptimizerWorkerResult(
                status="rolled_back",
                detail={
                    "stage": rollback_result.get("stage"),
                    "reasons": guardrail_result.get("reasons", []),
                    "guardrailResult": guardrail_result,
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": "rollback",
                    "appliedAction": "rollback",
                    "verificationStatus": "success",
                    "verification": verification,
                },
            )
        step_index = _next_expand_step_index(current)
        expanded = self.optimizer.expand_rollout(step_index=step_index)
        try:
            verification = self._verify_apply_post_check(
                attempted_action="rollout_expand",
                expected_stage=str(expanded.get("stage") or ""),
                before_projection=before_projection,
            )
        except PolicyOptimizerPostCheckError as exc:
            return PolicyOptimizerWorkerResult(
                status="failed",
                detail={
                    "stage": expanded.get("stage"),
                    "stepIndex": expanded.get("expand_step_index"),
                    "basePolicyVersion": expanded.get("base_policy_version"),
                    "candidatePolicyVersion": expanded.get("candidate_policy_version"),
                    "guardrailResult": guardrail_result,
                    "reason": str(exc),
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": "rollout_expand",
                    "appliedAction": "rollout_expand",
                    "verificationStatus": "failed",
                },
            )
        return PolicyOptimizerWorkerResult(
            status="rollout_expanded",
            detail={
                "stage": expanded.get("stage"),
                "stepIndex": expanded.get("expand_step_index"),
                "basePolicyVersion": expanded.get("base_policy_version"),
                "candidatePolicyVersion": expanded.get("candidate_policy_version"),
                "guardrailResult": guardrail_result,
                "applyEnabled": self.apply_enabled,
                "attemptedAction": "rollout_expand",
                "appliedAction": "rollout_expand",
                "verificationStatus": "success",
                "verification": verification,
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

    def _check_apply_preconditions(self) -> PolicyOptimizerWorkerResult | None:
        if self.bootstrap_authority is None:
            return PolicyOptimizerWorkerResult(
                status="projection_not_ready",
                detail={
                    "reason": "strict PostgreSQL authority service is required for auto-apply.",
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "not_checked",
                },
            )
        current = self.optimizer.current_rollout_state()
        if current is None:
            return PolicyOptimizerWorkerResult(
                status="no_active_rollout",
                detail={
                    "reason": "active rollout state is required before auto-apply.",
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "not_checked",
                },
            )
        if not _has_required_rollout_versions(current):
            return PolicyOptimizerWorkerResult(
                status="no_candidate_or_no_baseline",
                detail={
                    "stage": current.get("stage"),
                    "reason": "active rollout is missing base or candidate policy version.",
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "not_checked",
                },
            )
        try:
            verification = self._verify_projection_matches_authoritative(
                current,
                before_projection=None,
            )
        except PolicyOptimizerPostCheckError as exc:
            return PolicyOptimizerWorkerResult(
                status="projection_not_ready",
                detail={
                    "stage": current.get("stage"),
                    "reason": str(exc),
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "failed",
                },
            )
        if not verification["projected_policy_versions"]:
            return PolicyOptimizerWorkerResult(
                status="projection_not_ready",
                detail={
                    "stage": current.get("stage"),
                    "reason": "Redis projection version index is empty.",
                    "applyEnabled": self.apply_enabled,
                    "attemptedAction": None,
                    "appliedAction": None,
                    "verificationStatus": "failed",
                },
            )
        return None

    def _verify_apply_post_check(
        self,
        *,
        attempted_action: str,
        expected_stage: str,
        before_projection: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        current = self.optimizer.current_rollout_state()
        if current is None:
            raise PolicyOptimizerPostCheckError(
                f"{attempted_action} verification failed: authoritative rollout state missing."
            )
        actual_stage = str(current.get("stage") or "").upper()
        if expected_stage and actual_stage != expected_stage.upper():
            raise PolicyOptimizerPostCheckError(
                f"{attempted_action} verification failed: expected stage {expected_stage}, got {actual_stage}."
            )
        return self._verify_projection_matches_authoritative(
            current,
            before_projection=before_projection,
        )

    def _verify_projection_matches_authoritative(
        self,
        current: Mapping[str, Any],
        *,
        before_projection: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        rollout_projection = _read_projected_rollout_state(self.redis)
        if not isinstance(rollout_projection, Mapping):
            raise PolicyOptimizerPostCheckError("Redis rollout projection is missing or invalid.")
        _assert_projection_field(
            rollout_projection,
            current,
            field="stage",
        )
        _assert_projection_field(
            rollout_projection,
            current,
            field="base_policy_version",
        )
        _assert_projection_field(
            rollout_projection,
            current,
            field="candidate_policy_version",
        )
        _assert_projection_float_field(
            rollout_projection,
            current,
            field="ratio",
        )
        _assert_projection_int_field(
            rollout_projection,
            current,
            field="updated_at_ms",
        )
        refreshed_at = _clean_int_value(
            rollout_projection.get("projection_refreshed_at_ms")
        )
        if refreshed_at <= 0:
            raise PolicyOptimizerPostCheckError(
                "Redis rollout projection is missing projection_refreshed_at_ms."
            )
        if before_projection is not None:
            before_refreshed_at = _clean_int_value(
                before_projection.get("projection_refreshed_at_ms")
            )
            if refreshed_at < before_refreshed_at:
                raise PolicyOptimizerPostCheckError(
                    "Redis rollout projection refreshed timestamp moved backwards."
                )
        required_versions = _required_projection_versions(current)
        version_index = _read_projected_version_index(self.redis)
        missing_index_versions = [
            version for version in required_versions if version not in version_index
        ]
        if missing_index_versions:
            raise PolicyOptimizerPostCheckError(
                "Redis version index is missing projected policy versions: "
                + ", ".join(missing_index_versions)
            )
        missing_policy_keys = [
            version
            for version in required_versions
            if _read_json(self.redis.get(f"{POLICY_VERSION_KEY_PREFIX}{version}")) is None
        ]
        if missing_policy_keys:
            raise PolicyOptimizerPostCheckError(
                "Redis policy projection keys are missing: "
                + ", ".join(missing_policy_keys)
            )
        return {
            "rolloutId": self.rollout_id,
            "stage": rollout_projection.get("stage"),
            "basePolicyVersion": rollout_projection.get("base_policy_version"),
            "candidatePolicyVersion": rollout_projection.get("candidate_policy_version"),
            "projectionRefreshedAtMs": refreshed_at,
            "projected_policy_versions": required_versions,
        }


def run_policy_optimizer() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    started = time.monotonic()
    if not _load_optimizer_enabled_from_env():
        summary = _build_policy_optimizer_summary(
            mode="disabled",
            status="disabled",
            detail={"reason": "TM_POLICY_OPTIMIZER_ENABLED is false or unset."},
            started_at_monotonic=started,
        )
        _log_policy_optimizer_summary(summary)
        print("Policy optimizer disabled.")
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return
    if _optimizer_mode_from_env() == "apply" and not _load_optimizer_apply_enabled_from_env():
        summary = _build_policy_optimizer_summary(
            mode="apply",
            status="apply_blocked",
            detail={
                "reason": "TM_POLICY_OPTIMIZER_APPLY_ENABLED must be true when TM_POLICY_OPTIMIZER_DRY_RUN=false.",
                "applyEnabled": False,
                "attemptedAction": None,
                "appliedAction": None,
                "verificationStatus": "not_checked",
            },
            started_at_monotonic=started,
        )
        _log_policy_optimizer_summary(summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1)

    try:
        result = PolicyOptimizerWorker.from_env().run_once()
    except PolicyOptimizerConfigurationError as exc:
        summary = _build_policy_optimizer_summary(
            mode=_optimizer_mode_from_env(),
            status="failed",
            detail={},
            started_at_monotonic=started,
            error=f"{type(exc).__name__}: {exc}",
        )
        _log_policy_optimizer_summary(summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1) from exc
    except StorageOperationalConfigError as exc:
        summary = _build_policy_optimizer_summary(
            mode=_optimizer_mode_from_env(),
            status="failed",
            detail={},
            started_at_monotonic=started,
            error=f"{type(exc).__name__}: {exc}",
        )
        _log_policy_optimizer_summary(summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1) from exc
    except Exception as exc:
        summary = _build_policy_optimizer_summary(
            mode=_optimizer_mode_from_env(),
            status="failed",
            detail={},
            started_at_monotonic=started,
            error=f"{type(exc).__name__}: {exc}",
        )
        _log_policy_optimizer_summary(summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1) from exc

    summary = _build_policy_optimizer_summary(
        mode="dry_run" if result.status == "dry_run" or _optimizer_mode_from_env() == "dry_run" else "apply",
        status=result.status,
        detail=result.detail,
        started_at_monotonic=started,
    )
    _log_policy_optimizer_summary(summary)
    print(
        "Policy optimizer completed. "
        f"status={result.status} detail={json.dumps(result.detail, sort_keys=True)}"
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if _policy_optimizer_status_exits_nonzero(result.status):
        raise SystemExit(1)


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


def _optimizer_mode_from_env() -> str:
    return "dry_run" if _clean_bool(os.getenv("TM_POLICY_OPTIMIZER_DRY_RUN"), default=False) else "apply"


def _load_optimizer_apply_enabled_from_env() -> bool:
    return _clean_bool(os.getenv("TM_POLICY_OPTIMIZER_APPLY_ENABLED"), default=False)


def _build_policy_optimizer_summary(
    *,
    mode: str,
    status: str,
    detail: Mapping[str, Any],
    started_at_monotonic: float,
    error: str | None = None,
) -> dict[str, Any]:
    output_count = 0
    skipped_count = 0
    if status in {
        "disabled",
        "lock_missed",
        "no_change",
        "rollout_waiting",
        "insufficient_data",
        "rollback_cooling_down",
        "rollout_cooling_down",
        "dry_run",
    }:
        skipped_count = 1
    if status in {"proposal_applied", "rollout_expanded", "rolled_back"}:
        output_count = 1
    summary: dict[str, Any] = {
        "command": "tm-ai-policy-optimizer",
        "mode": mode,
        "status": "failed" if error is not None else status,
        "rollout_id": detail.get("rolloutId") or os.getenv("TM_POLICY_OPTIMIZER_ROLLOUT_ID") or POLICY_OPTIMIZER_ROLLOUT_ID,
        "input_count": 1,
        "output_count": output_count,
        "skipped_count": skipped_count,
        "error_count": (
            1
            if error is not None or _policy_optimizer_status_exits_nonzero(status)
            else 0
        ),
        "duration_ms": max(int((time.monotonic() - started_at_monotonic) * 1000), 0),
        "dry_run": mode == "dry_run",
        "apply_enabled": bool(
            detail.get("applyEnabled", _load_optimizer_apply_enabled_from_env())
        ),
        "guardrail_result": detail.get("guardrailResult"),
        "attempted_action": detail.get("attemptedAction"),
        "applied_action": detail.get("appliedAction"),
        "verification_status": detail.get(
            "verificationStatus",
            "not_checked" if error is None else "failed",
        ),
        "detail": dict(detail),
    }
    if error is not None:
        summary["error"] = error
    return summary


def _log_policy_optimizer_summary(summary: Mapping[str, Any]) -> None:
    logger.info(
        "policy_optimizer_summary mode=%s status=%s rollout_id=%s input_count=%s "
        "output_count=%s skipped_count=%s error_count=%s duration_ms=%s dry_run=%s "
        "apply_enabled=%s attempted_action=%s applied_action=%s verification_status=%s",
        summary["mode"],
        summary["status"],
        summary["rollout_id"],
        summary["input_count"],
        summary["output_count"],
        summary["skipped_count"],
        summary["error_count"],
        summary["duration_ms"],
        summary["dry_run"],
        summary["apply_enabled"],
        summary["attempted_action"],
        summary["applied_action"],
        summary["verification_status"],
    )


def _policy_optimizer_status_exits_nonzero(status: str) -> bool:
    return status in {
        "apply_blocked",
        "failed",
        "metrics_read_failed",
        "no_active_rollout",
        "no_candidate_or_no_baseline",
        "projection_not_ready",
    }


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


def _has_required_rollout_versions(state: Mapping[str, Any]) -> bool:
    stage = str(state.get("stage") or "").upper()
    base_policy_version = str(state.get("base_policy_version") or "").strip()
    candidate_policy_version = str(
        state.get("candidate_policy_version") or ""
    ).strip()
    if not base_policy_version:
        return False
    if stage in {"CANARY", "EXPAND"} and not candidate_policy_version:
        return False
    return True


def _required_projection_versions(state: Mapping[str, Any]) -> tuple[str, ...]:
    versions: list[str] = []
    for value in (
        state.get("base_policy_version"),
        state.get("candidate_policy_version"),
    ):
        version = str(value or "").strip()
        if version and version not in versions:
            versions.append(version)
    return tuple(versions)


def _read_projected_rollout_state(redis: RedisLike) -> Mapping[str, Any] | None:
    parsed = _read_json(redis.get(POLICY_ROLLOUT_STATE_KEY))
    if isinstance(parsed, Mapping):
        return parsed
    return None


def _read_projected_version_index(redis: RedisLike) -> tuple[str, ...]:
    parsed = _read_json(redis.get(POLICY_VERSION_INDEX_KEY))
    if not isinstance(parsed, list):
        return ()
    return tuple(value for value in parsed if isinstance(value, str) and value)


def _assert_projection_field(
    projection: Mapping[str, Any],
    authoritative: Mapping[str, Any],
    *,
    field: str,
) -> None:
    if projection.get(field) != authoritative.get(field):
        raise PolicyOptimizerPostCheckError(
            f"Redis projection field mismatch for {field}: "
            f"expected {authoritative.get(field)!r}, got {projection.get(field)!r}."
        )


def _assert_projection_int_field(
    projection: Mapping[str, Any],
    authoritative: Mapping[str, Any],
    *,
    field: str,
) -> None:
    if _clean_int_value(projection.get(field)) != _clean_int_value(
        authoritative.get(field)
    ):
        raise PolicyOptimizerPostCheckError(
            f"Redis projection field mismatch for {field}: "
            f"expected {authoritative.get(field)!r}, got {projection.get(field)!r}."
        )


def _assert_projection_float_field(
    projection: Mapping[str, Any],
    authoritative: Mapping[str, Any],
    *,
    field: str,
) -> None:
    try:
        projected_value = float(projection.get(field))
        authoritative_value = float(authoritative.get(field))
    except (TypeError, ValueError) as exc:
        raise PolicyOptimizerPostCheckError(
            f"Redis projection field mismatch for {field}: non-numeric value."
        ) from exc
    if abs(projected_value - authoritative_value) > 0.00001:
        raise PolicyOptimizerPostCheckError(
            f"Redis projection field mismatch for {field}: "
            f"expected {authoritative_value!r}, got {projected_value!r}."
        )


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
