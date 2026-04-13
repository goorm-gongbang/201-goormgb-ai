from __future__ import annotations

import io
import json
import os
import time
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from traffic_master_ai.defense.backoffice_copilot.storage import (
    POLICY_ROLLOUT_STATE_KEY,
    POLICY_VERSION_INDEX_KEY,
    POLICY_VERSION_KEY_PREFIX,
    PolicyOptimizationRunRecord,
    PolicyRolloutEventRecord,
    PolicyRolloutStateRecord,
    PolicyVersionRecord,
    PostgresStrictPolicyAuthorityService,
    RedisRuntimePolicyProjectionRepository,
)
from traffic_master_ai.defense.d0_mvp.optimizer.worker import (
    POLICY_OPTIMIZER_LOCK_KEY,
    POLICY_OPTIMIZER_ROLLOUT_ID,
    PolicyOptimizerConfigurationError,
    PolicyOptimizerWorker,
    run_policy_optimizer,
)
from traffic_master_ai.defense.d0_mvp.policy.loader import snapshot_to_document
from traffic_master_ai.defense.d0_mvp.policy.snapshot import PolicySnapshot
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis

_WORKER_FROM_ENV_PATH = (
    "traffic_master_ai.defense.d0_mvp.optimizer.worker.PolicyOptimizerWorker.from_env"
)


class _FakeOptimizer:
    def __init__(
        self,
        *,
        rollout_state: dict[str, Any] | None = None,
        proposal: dict[str, Any] | None = None,
        guardrail_result: dict[str, Any] | None = None,
    ) -> None:
        self.rollout_state = rollout_state
        self.proposal = proposal
        self.guardrail_result = guardrail_result
        self.run_once_calls = 0
        self.run_once_windows: list[int] = []
        self.start_canary_calls: list[dict[str, Any]] = []
        self.start_canary_ratios: list[float] = []
        self.expand_rollout_calls: list[int] = []
        self.rollback_reasons: list[str] = []
        self.collect_metrics_windows: list[int] = []
        self.guardrail_deltas: list[dict[str, float]] = []

    def current_rollout_state(self) -> dict[str, Any] | None:
        return self.rollout_state

    def run_once(self, *, window_seconds: int = 600) -> dict[str, Any]:
        self.run_once_calls += 1
        self.run_once_windows.append(window_seconds)
        return {
            "metricsSnapshotId": "metrics-1",
            "proposal": self.proposal,
        }

    def start_canary(
        self,
        *,
        proposal: dict[str, Any],
        ratio: float = 0.05,
    ) -> dict[str, Any]:
        self.start_canary_calls.append(proposal)
        self.start_canary_ratios.append(ratio)
        return {"candidatePolicyVersion": "policy-v1-opt"}

    def expand_rollout(self, *, step_index: int) -> dict[str, Any]:
        self.expand_rollout_calls.append(step_index)
        return {
            "stage": "EXPAND",
            "expand_step_index": step_index,
            "base_policy_version": "policy-v1",
            "candidate_policy_version": "policy-v1-opt",
        }

    def rollback(self, *, reason: str = "manual") -> dict[str, Any]:
        self.rollback_reasons.append(reason)
        return {"stage": "ROLLED_BACK"}

    def collect_metrics(self, *, window_seconds: int = 600) -> dict[str, Any]:
        self.collect_metrics_windows.append(window_seconds)
        return {
            "s3_temp_lock_rate": 0.0,
            "block_rate": 0.0,
            "avg_throttle_delay_ms": 0.0,
            "s3_fail_rate": 0.0,
            "dedup_duplicate_rate": 0.0,
        }

    def evaluate_guardrails(self, deltas: dict[str, float]) -> dict[str, Any]:
        self.guardrail_deltas.append(deltas)
        if self.guardrail_result is not None:
            return self.guardrail_result
        should_rollback = deltas.get("block_rate_pp", 0.0) > 0.3
        return {
            "shouldRollback": should_rollback,
            "reasons": ["block_rate"] if should_rollback else [],
        }


class _FakeRolloutGuardrailRepository:
    def __init__(self, deltas: dict[str, float] | None) -> None:
        self.deltas = deltas
        self.calls: list[tuple[int, int, str, str]] = []

    def read_rollout_guardrail_deltas(
        self,
        query: Any,
        *,
        base_policy_version: str,
        candidate_policy_version: str,
    ) -> dict[str, float] | None:
        self.calls.append(
            (
                query.window_start_ms,
                query.window_end_ms,
                base_policy_version,
                candidate_policy_version,
            )
        )
        return self.deltas


def _safe_guardrail_deltas() -> dict[str, float]:
    return {
        "s3_temp_lock_rate_pp": 0.0,
        "block_rate_pp": 0.0,
        "avg_throttle_delay_ms": 0.0,
        "s3_fail_rate_pp": 0.0,
        "dedup_duplicate_rate_pp": 0.0,
    }


class _EvalRedis(InMemoryRedis):
    def __init__(self) -> None:
        super().__init__()
        self.eval_calls: list[tuple[str, int, tuple[Any, ...]]] = []

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> int:
        self.eval_calls.append((script, numkeys, keys_and_args))
        lock_key, token = keys_and_args
        if self.get(str(lock_key)) == token:
            return self.delete(str(lock_key))
        return 0


class _FakePolicyVersionRepository:
    def __init__(self, records: dict[str, PolicyVersionRecord] | None = None) -> None:
        self.records = records or {}
        self.save_calls = 0

    def get_version(self, policy_version: str) -> PolicyVersionRecord | None:
        return self.records.get(policy_version)

    def save_version(self, record: PolicyVersionRecord) -> None:
        self.records[record.policy_version] = record
        self.save_calls += 1


class _FakePolicyRolloutStateRepository:
    def __init__(self, record: PolicyRolloutStateRecord | None = None) -> None:
        self.record = record
        self.save_calls = 0

    def get_state(self, rollout_id: str) -> PolicyRolloutStateRecord | None:
        if self.record is None or self.record.rollout_id != rollout_id:
            return None
        return self.record

    def save_state(self, record: PolicyRolloutStateRecord) -> None:
        self.record = record
        self.save_calls += 1


class _FakePolicyRolloutEventRepository:
    def append_event(self, record: PolicyRolloutEventRecord) -> None:
        del record


class _FakePolicyOptimizationRunRepository:
    def save_run(self, record: PolicyOptimizationRunRecord) -> None:
        del record


class PolicyOptimizerWorkerTests(unittest.TestCase):
    def test_command_import_succeeds(self) -> None:
        self.assertTrue(callable(run_policy_optimizer))

    def test_command_exits_without_applying_when_disabled(self) -> None:
        with patch.dict(os.environ, {"TM_POLICY_OPTIMIZER_ENABLED": "false"}, clear=True):
            buf = io.StringIO()
            with (
                patch(_WORKER_FROM_ENV_PATH) as from_env,
                redirect_stdout(buf),
            ):
                run_policy_optimizer()

        from_env.assert_not_called()
        self.assertIn("Policy optimizer disabled.", buf.getvalue())

    def test_policy_optimizer_worker_uses_redis_lock(self) -> None:
        redis = InMemoryRedis()
        redis.set(POLICY_OPTIMIZER_LOCK_KEY, "other-worker", ex=60, nx=True)
        optimizer = _FakeOptimizer(proposal={"proposal_id": "proposal-1"})
        worker = PolicyOptimizerWorker(
            redis=redis,
            optimizer=optimizer,
            lock_ttl_seconds=60,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "lock_missed")
        self.assertEqual(optimizer.run_once_calls, 0)
        self.assertEqual(optimizer.start_canary_calls, [])

    def test_worker_releases_redis_lock_with_atomic_eval_when_available(self) -> None:
        redis = _EvalRedis()
        optimizer = _FakeOptimizer(proposal=None)
        worker = PolicyOptimizerWorker(
            redis=redis,
            optimizer=optimizer,
            lock_ttl_seconds=60,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "no_change")
        self.assertEqual(len(redis.eval_calls), 1)
        self.assertIsNone(redis.get(POLICY_OPTIMIZER_LOCK_KEY))

    def test_policy_optimizer_worker_fails_fast_without_prod_storage_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TM_POLICY_OPTIMIZER_ENABLED": "true",
                "TM_ENV": "prod",
                "TM_REDIS_URL": "redis://localhost:6379/0",
                "TM_ROLLOUT_SALT": "prod-salt",
                "TM_ALLOW_IN_MEMORY_REDIS": "false",
                "TM_POLICY_ALLOW_LOCAL_FALLBACK": "false",
            },
            clear=True,
        ):
            with self.assertRaises(SystemExit) as exc_info:
                run_policy_optimizer()

        self.assertIn("TM_PG_URL must be set", str(exc_info.exception))

    def test_policy_optimizer_worker_never_uses_local_fallback_in_prod(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TM_POLICY_OPTIMIZER_ENABLED": "true",
                "TM_ENV": "prod",
                "TM_PG_URL": "postgresql://user:pass@localhost:5432/tm",
                "TM_REDIS_URL": "redis://localhost:6379/0",
                "TM_ROLLOUT_SALT": "prod-salt",
                "TM_CLICKHOUSE_URL": "http://localhost:8123/default",
                "TM_POLICY_ALLOW_LOCAL_FALLBACK": "true",
                "TM_ALLOW_IN_MEMORY_REDIS": "false",
                "TM_POLICY_OPTIMIZER_WINDOW_SECONDS": "300",
                "TM_POLICY_OPTIMIZER_CANARY_RATIO": "0.1",
                "TM_POLICY_OPTIMIZER_MIN_APPLY_COOLDOWN_SECONDS": "120",
                "TM_POLICY_OPTIMIZER_ROLLOUT_ID": "offline-optimizer-default",
            },
            clear=True,
        ):
            with (
                patch(
                    "traffic_master_ai.defense.d0_mvp.optimizer.worker.FilePolicyStore"
                ) as file_policy_store,
                patch(
                    "traffic_master_ai.defense.d0_mvp.optimizer.worker.build_runtime_redis_from_env"
                ) as redis_builder,
                self.assertRaises(SystemExit) as exc_info,
            ):
                run_policy_optimizer()

        self.assertIn("TM_POLICY_ALLOW_LOCAL_FALLBACK", str(exc_info.exception))
        file_policy_store.assert_not_called()
        redis_builder.assert_not_called()

    def test_policy_optimizer_worker_starts_canary_when_valid_proposal_exists(self) -> None:
        redis = InMemoryRedis()
        proposal = {"proposal_id": "proposal-1", "patches": []}
        optimizer = _FakeOptimizer(proposal=proposal)
        worker = PolicyOptimizerWorker(
            redis=redis,
            optimizer=optimizer,
            lock_ttl_seconds=60,
            window_seconds=900,
            canary_ratio=0.1,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "proposal_applied")
        self.assertEqual(optimizer.run_once_calls, 1)
        self.assertEqual(optimizer.run_once_windows, [900])
        self.assertEqual(optimizer.start_canary_calls, [proposal])
        self.assertEqual(optimizer.start_canary_ratios, [0.1])

    def test_policy_optimizer_worker_does_not_apply_when_proposal_missing(self) -> None:
        optimizer = _FakeOptimizer(proposal=None)
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
            window_seconds=300,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "no_change")
        self.assertEqual(optimizer.run_once_windows, [300])
        self.assertEqual(optimizer.start_canary_calls, [])

    def test_worker_waits_before_canary_duration_elapsed(self) -> None:
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "CANARY",
                "stage_started_at_ms": int(time.time() * 1000),
                "stage_duration_seconds": 120,
            },
            proposal={"proposal_id": "proposal-1"},
        )
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "rollout_waiting")
        self.assertEqual(optimizer.collect_metrics_windows, [])
        self.assertEqual(optimizer.expand_rollout_calls, [])

    def test_policy_optimizer_worker_expands_after_canary_duration(self) -> None:
        redis = InMemoryRedis()
        stage_started_at_ms = int(time.time() * 1000) - 121000
        guardrail_repository = _FakeRolloutGuardrailRepository(_safe_guardrail_deltas())
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "CANARY",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "stage_started_at_ms": stage_started_at_ms,
                "stage_duration_seconds": 120,
            },
            proposal={"proposal_id": "proposal-1"},
        )
        worker = PolicyOptimizerWorker(
            redis=redis,
            optimizer=optimizer,
            lock_ttl_seconds=60,
            window_seconds=240,
            guardrail_repository=guardrail_repository,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "rollout_expanded")
        self.assertEqual(optimizer.expand_rollout_calls, [0])
        self.assertEqual(optimizer.run_once_calls, 0)
        self.assertEqual(optimizer.collect_metrics_windows, [])
        self.assertEqual(guardrail_repository.calls[0][0], stage_started_at_ms)

    def test_policy_optimizer_worker_rolls_back_on_guardrail_delta(self) -> None:
        stage_started_at_ms = int(time.time() * 1000) - 121000
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "CANARY",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "stage_started_at_ms": stage_started_at_ms,
                "stage_duration_seconds": 120,
            },
        )
        guardrail_repository = _FakeRolloutGuardrailRepository(
            {
                "s3_temp_lock_rate_pp": 0.0,
                "block_rate_pp": 0.31,
                "avg_throttle_delay_ms": 0.0,
                "s3_fail_rate_pp": 0.0,
                "dedup_duplicate_rate_pp": 0.0,
                "internal_error_rate_pp": 0.0,
            }
        )
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
            guardrail_repository=guardrail_repository,
            window_seconds=300,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "rolled_back")
        self.assertEqual(optimizer.rollback_reasons, ["guardrail"])
        self.assertEqual(optimizer.expand_rollout_calls, [])
        self.assertEqual(optimizer.guardrail_deltas[0]["block_rate_pp"], 0.31)
        self.assertEqual(guardrail_repository.calls[0][0], stage_started_at_ms)
        self.assertEqual(guardrail_repository.calls[0][2:], ("policy-v1", "policy-v2"))

    def test_worker_does_not_apply_when_rollout_guardrail_data_is_insufficient(self) -> None:
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "CANARY",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "stage_started_at_ms": int(time.time() * 1000) - 121000,
                "stage_duration_seconds": 120,
            }
        )
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
            guardrail_repository=_FakeRolloutGuardrailRepository(None),
        )

        result = worker.run_once()

        self.assertEqual(result.status, "insufficient_data")
        self.assertEqual(optimizer.rollback_reasons, [])
        self.assertEqual(optimizer.expand_rollout_calls, [])

    def test_worker_does_not_use_aggregate_metrics_as_guardrail_delta(self) -> None:
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "CANARY",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "stage_started_at_ms": int(time.time() * 1000) - 121000,
                "stage_duration_seconds": 120,
            }
        )
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
            guardrail_repository=None,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "insufficient_data")
        self.assertEqual(optimizer.collect_metrics_windows, [])
        self.assertEqual(optimizer.guardrail_deltas, [])
        self.assertEqual(optimizer.expand_rollout_calls, [])

    def test_worker_waits_before_expand_duration_elapsed(self) -> None:
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "EXPAND",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "stage_started_at_ms": int(time.time() * 1000),
                "stage_duration_seconds": 180,
                "expand_step_index": 0,
            }
        )
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "rollout_waiting")
        self.assertEqual(optimizer.expand_rollout_calls, [])

    def test_worker_advances_elapsed_expand_to_next_step(self) -> None:
        stage_started_at_ms = int(time.time() * 1000) - 181000
        guardrail_repository = _FakeRolloutGuardrailRepository(_safe_guardrail_deltas())
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "EXPAND",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "stage_started_at_ms": stage_started_at_ms,
                "stage_duration_seconds": 180,
                "expand_step_index": 0,
            }
        )
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
            guardrail_repository=guardrail_repository,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "rollout_expanded")
        self.assertEqual(optimizer.expand_rollout_calls, [1])
        self.assertEqual(guardrail_repository.calls[0][0], stage_started_at_ms)

    def test_worker_blocks_new_proposal_during_rolled_back_cooldown(self) -> None:
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "ROLLED_BACK",
                "updated_at_ms": int(time.time() * 1000),
                "rollout_finished_at_ms": int(time.time() * 1000),
            },
            proposal={"proposal_id": "proposal-1"},
        )
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
            min_apply_cooldown_seconds=300,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "rollback_cooling_down")
        self.assertEqual(optimizer.run_once_calls, 0)

    def test_worker_blocks_new_proposal_during_full_rollout_cooldown(self) -> None:
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "FULL",
                "base_policy_version": "policy-v2",
                "candidate_policy_version": None,
                "updated_at_ms": int(time.time() * 1000),
                "rollout_finished_at_ms": int(time.time() * 1000),
                "expand_step_index": 2,
            },
            proposal={"proposal_id": "proposal-1"},
        )
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
            min_apply_cooldown_seconds=300,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "rollout_cooling_down")
        self.assertEqual(optimizer.run_once_calls, 0)

    def test_worker_allows_new_proposal_after_full_rollout_cooldown(self) -> None:
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "FULL",
                "base_policy_version": "policy-v2",
                "candidate_policy_version": None,
                "updated_at_ms": int(time.time() * 1000) - 301000,
                "rollout_finished_at_ms": int(time.time() * 1000) - 301000,
                "expand_step_index": 2,
            },
            proposal={"proposal_id": "proposal-1", "patches": []},
        )
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
            min_apply_cooldown_seconds=300,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "proposal_applied")
        self.assertEqual(optimizer.run_once_calls, 1)

    def test_worker_does_not_cooldown_baseline_full_without_expand_history(self) -> None:
        proposal = {"proposal_id": "proposal-1", "patches": []}
        optimizer = _FakeOptimizer(
            rollout_state={
                "stage": "FULL",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": None,
                "updated_at_ms": int(time.time() * 1000),
                "rollout_finished_at_ms": int(time.time() * 1000),
                "expand_step_index": None,
            },
            proposal=proposal,
        )
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=optimizer,
            lock_ttl_seconds=60,
            min_apply_cooldown_seconds=300,
        )

        result = worker.run_once()

        self.assertEqual(result.status, "proposal_applied")
        self.assertEqual(optimizer.start_canary_calls, [proposal])

    def test_policy_optimizer_worker_bootstraps_baseline_authoritatively(self) -> None:
        redis = InMemoryRedis()
        version_repository = _FakePolicyVersionRepository()
        rollout_repository = _FakePolicyRolloutStateRepository()
        authority = _build_authority(
            redis=redis,
            version_repository=version_repository,
            rollout_repository=rollout_repository,
        )
        worker = PolicyOptimizerWorker(
            redis=redis,
            optimizer=_FakeOptimizer(),
            lock_ttl_seconds=60,
            bootstrap_baseline=True,
            bootstrap_authority=authority,
        )

        result = worker.run_once()

        baseline_version = PolicySnapshot().policy_version
        self.assertEqual(result.status, "no_change")
        self.assertIn(baseline_version, version_repository.records)
        self.assertIsNotNone(rollout_repository.record)
        self.assertEqual(rollout_repository.record.stage, "FULL")
        self.assertEqual(rollout_repository.record.base_policy_version, baseline_version)
        self.assertIsNotNone(redis.get(f"{POLICY_VERSION_KEY_PREFIX}{baseline_version}"))
        self.assertIsNotNone(redis.get(POLICY_ROLLOUT_STATE_KEY))
        self.assertIsNotNone(redis.get(POLICY_VERSION_INDEX_KEY))
        worker.run_once()
        self.assertEqual(version_repository.save_calls, 1)
        self.assertEqual(rollout_repository.save_calls, 1)

    def test_worker_bootstrap_is_idempotent_when_baseline_is_ready(self) -> None:
        redis = InMemoryRedis()
        baseline = PolicySnapshot()
        baseline_version = baseline.policy_version
        version_repository = _FakePolicyVersionRepository(
            {baseline_version: _baseline_policy_record(baseline)}
        )
        rollout_repository = _FakePolicyRolloutStateRepository(
            _baseline_rollout_state_record(baseline_version)
        )
        authority = _build_authority(
            redis=redis,
            version_repository=version_repository,
            rollout_repository=rollout_repository,
        )
        worker = PolicyOptimizerWorker(
            redis=redis,
            optimizer=_FakeOptimizer(),
            lock_ttl_seconds=60,
            bootstrap_baseline=True,
            bootstrap_authority=authority,
        )

        worker.run_once()
        version_repository.save_calls = 0
        rollout_repository.save_calls = 0
        worker.run_once()

        self.assertEqual(version_repository.save_calls, 0)
        self.assertEqual(rollout_repository.save_calls, 0)

    def test_worker_bootstrap_resyncs_missing_redis_projection_from_pg(self) -> None:
        redis = InMemoryRedis()
        baseline = PolicySnapshot()
        baseline_version = baseline.policy_version
        version_repository = _FakePolicyVersionRepository(
            {baseline_version: _baseline_policy_record(baseline)}
        )
        rollout_repository = _FakePolicyRolloutStateRepository(
            _baseline_rollout_state_record(baseline_version)
        )
        authority = _build_authority(
            redis=redis,
            version_repository=version_repository,
            rollout_repository=rollout_repository,
        )
        worker = PolicyOptimizerWorker(
            redis=redis,
            optimizer=_FakeOptimizer(),
            lock_ttl_seconds=60,
            bootstrap_baseline=True,
            bootstrap_authority=authority,
        )

        worker.run_once()

        self.assertEqual(version_repository.save_calls, 0)
        self.assertEqual(rollout_repository.save_calls, 0)
        self.assertIsNotNone(redis.get(f"{POLICY_VERSION_KEY_PREFIX}{baseline_version}"))
        self.assertIsNotNone(redis.get(POLICY_ROLLOUT_STATE_KEY))
        self.assertIsNotNone(redis.get(POLICY_VERSION_INDEX_KEY))

    def test_worker_bootstrap_resyncs_stale_redis_projection_from_pg(self) -> None:
        redis = InMemoryRedis()
        baseline = PolicySnapshot()
        baseline_version = baseline.policy_version
        version_repository = _FakePolicyVersionRepository(
            {baseline_version: _baseline_policy_record(baseline)}
        )
        fresh_state = _baseline_rollout_state_record(
            baseline_version,
            updated_at_ms=1712966500000,
        )
        stale_state = _baseline_rollout_state_record(
            baseline_version,
            updated_at_ms=1712966400000,
        )
        _build_authority(
            redis=redis,
            version_repository=version_repository,
            rollout_repository=_FakePolicyRolloutStateRepository(stale_state),
        ).resync_runtime_projection(
            rollout_id=POLICY_OPTIMIZER_ROLLOUT_ID,
            additional_policy_versions=(baseline_version,),
        )
        rollout_repository = _FakePolicyRolloutStateRepository(fresh_state)
        authority = _build_authority(
            redis=redis,
            version_repository=version_repository,
            rollout_repository=rollout_repository,
        )
        worker = PolicyOptimizerWorker(
            redis=redis,
            optimizer=_FakeOptimizer(),
            lock_ttl_seconds=60,
            bootstrap_baseline=True,
            bootstrap_authority=authority,
        )

        worker.run_once()

        rollout_payload = json.loads(str(redis.get(POLICY_ROLLOUT_STATE_KEY)))
        self.assertEqual(rollout_payload["updated_at_ms"], fresh_state.updated_at_ms)
        self.assertEqual(version_repository.save_calls, 0)
        self.assertEqual(rollout_repository.save_calls, 0)

    def test_worker_bootstrap_requires_strict_authority(self) -> None:
        worker = PolicyOptimizerWorker(
            redis=InMemoryRedis(),
            optimizer=_FakeOptimizer(),
            lock_ttl_seconds=60,
            bootstrap_baseline=True,
            bootstrap_authority=None,
        )

        with self.assertRaises(PolicyOptimizerConfigurationError):
            worker.run_once()


def _build_authority(
    *,
    redis: InMemoryRedis,
    version_repository: _FakePolicyVersionRepository,
    rollout_repository: _FakePolicyRolloutStateRepository,
) -> PostgresStrictPolicyAuthorityService:
    return PostgresStrictPolicyAuthorityService(
        version_repository=version_repository,
        rollout_state_repository=rollout_repository,
        rollout_event_repository=_FakePolicyRolloutEventRepository(),
        optimization_run_repository=_FakePolicyOptimizationRunRepository(),
        projection_repository=RedisRuntimePolicyProjectionRepository(redis),
    )


def _baseline_policy_record(snapshot: PolicySnapshot) -> PolicyVersionRecord:
    now = datetime(2026, 4, 13, 0, 0, 0, tzinfo=UTC)
    document = snapshot_to_document(snapshot)
    return PolicyVersionRecord(
        policy_version=snapshot.policy_version,
        schema_version="policy.v1",
        status="ACTIVE",
        source_type="BASELINE_BOOTSTRAP",
        document_json=document,
        validation_result_json={"errors": []},
        created_at=now,
        validated_at=now,
        activated_at=now,
    )


def _baseline_rollout_state_record(
    baseline_version: str,
    *,
    updated_at_ms: int = 1712966400000,
) -> PolicyRolloutStateRecord:
    return PolicyRolloutStateRecord(
        rollout_id=POLICY_OPTIMIZER_ROLLOUT_ID,
        stage="FULL",
        base_policy_version=baseline_version,
        candidate_policy_version=None,
        ratio=Decimal("0.00000"),
        evaluation_window_seconds=60,
        canary_duration_seconds=120,
        expand_step_index=None,
        stage_started_at_ms=updated_at_ms,
        updated_at_ms=updated_at_ms,
        current_status="ACTIVE",
        rollback_reason=None,
    )


if __name__ == "__main__":
    unittest.main()
