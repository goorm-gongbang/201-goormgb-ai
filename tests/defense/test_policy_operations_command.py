from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
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
from traffic_master_ai.defense.backoffice_copilot.storage.policy_operations import (
    bootstrap_baseline_policy,
    run_policy_bootstrap,
    run_policy_projection_resync,
)
from traffic_master_ai.defense.d0_mvp.core.constants import DEFAULT_POLICY_VERSION


def _now() -> datetime:
    return datetime(2026, 4, 14, 11, 0, 0, tzinfo=UTC)


def _policy_record(version: str = DEFAULT_POLICY_VERSION) -> PolicyVersionRecord:
    return PolicyVersionRecord(
        policy_version=version,
        schema_version="policy.v1",
        status="ACTIVE",
        source_type="BASELINE_BOOTSTRAP",
        document_json={
            "schemaVersion": "policy.v1",
            "parameters": {"planner": {"action_matrix": {"T0": "NONE"}}},
            "flags": {"runtime_llm_enabled": False},
        },
        validation_result_json={"errors": []},
        created_at=_now(),
        validated_at=_now(),
        activated_at=_now(),
    )


def _rollout_state(
    *,
    rollout_id: str = "offline-optimizer-default",
    policy_version: str = DEFAULT_POLICY_VERSION,
) -> PolicyRolloutStateRecord:
    return PolicyRolloutStateRecord(
        rollout_id=rollout_id,
        stage="FULL",
        base_policy_version=policy_version,
        candidate_policy_version=None,
        ratio=Decimal("0.00000"),
        evaluation_window_seconds=60,
        canary_duration_seconds=120,
        expand_step_index=None,
        stage_started_at_ms=1000,
        updated_at_ms=2000,
        current_status="ACTIVE",
        rollback_reason=None,
    )


class _FakePolicyVersionRepository:
    def __init__(self, records: dict[str, PolicyVersionRecord] | None = None) -> None:
        self.records = records or {}
        self.save_calls = 0

    def get_version(self, policy_version: str) -> PolicyVersionRecord | None:
        return self.records.get(policy_version)

    def save_version(self, record: PolicyVersionRecord) -> None:
        self.records[record.policy_version] = record
        self.save_calls += 1


class _FailingPolicyVersionRepository(_FakePolicyVersionRepository):
    def get_version(self, policy_version: str) -> PolicyVersionRecord | None:
        del policy_version
        raise RuntimeError("relation policy_versions does not exist")


class _FakePolicyRolloutStateRepository:
    def __init__(self, record: PolicyRolloutStateRecord | None = None) -> None:
        self.record = record
        self.save_calls = 0
        self.current_calls = 0

    def get_state(self, rollout_id: str) -> PolicyRolloutStateRecord | None:
        if self.record is None or self.record.rollout_id != rollout_id:
            return None
        return self.record

    def get_current_state(self) -> PolicyRolloutStateRecord | None:
        self.current_calls += 1
        return self.record

    def save_state(self, record: PolicyRolloutStateRecord) -> None:
        self.record = record
        self.save_calls += 1


class _FakePolicyRolloutEventRepository:
    def __init__(self) -> None:
        self.records: list[PolicyRolloutEventRecord] = []

    def append_event(self, record: PolicyRolloutEventRecord) -> None:
        self.records.append(record)


class _FakePolicyOptimizationRunRepository:
    def __init__(self) -> None:
        self.records: dict[str, PolicyOptimizationRunRecord] = {}

    def save_run(self, record: PolicyOptimizationRunRecord) -> None:
        self.records[record.run_id] = record


class _FakeRedisClient:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.calls: list[tuple[str, str, object]] = []

    def set(self, name: str, value: object, ex: int | None = None, nx: bool = False) -> bool:
        self.data[name] = value
        self.calls.append(("set", name, value))
        return True

    def get(self, name: str) -> object | None:
        return self.data.get(name)

    def delete(self, *names: str) -> int:
        deleted = 0
        for name in names:
            if name in self.data:
                del self.data[name]
                deleted += 1
            self.calls.append(("delete", name, None))
        return deleted


@dataclass(slots=True)
class _RepositoryBundle:
    version_repository: _FakePolicyVersionRepository
    rollout_state_repository: _FakePolicyRolloutStateRepository
    disposed: bool = False

    def dispose(self) -> None:
        self.disposed = True


class _DisposableService:
    def __init__(self, service: PostgresStrictPolicyAuthorityService) -> None:
        self.service = service
        self.disposed = False
        self.version_repository = service.version_repository
        self.rollout_state_repository = service.rollout_state_repository
        self.rollout_event_repository = service.rollout_event_repository
        self.optimization_run_repository = service.optimization_run_repository
        self.projection_repository = service.projection_repository
        self.projection_retry_policy = service.projection_retry_policy

    def refresh_current_runtime_projection(self, *, additional_policy_versions=()):
        return self.service.refresh_current_runtime_projection(
            additional_policy_versions=additional_policy_versions
        )

    def resync_runtime_projection(self, *, rollout_id, additional_policy_versions=()):
        return self.service.resync_runtime_projection(
            rollout_id=rollout_id,
            additional_policy_versions=additional_policy_versions,
        )

    def dispose(self) -> None:
        self.disposed = True


class PolicyOperationsCommandTests(unittest.TestCase):
    def test_bootstrap_creates_missing_baseline_policy_and_rollout_without_projection(self) -> None:
        repositories = _RepositoryBundle(
            version_repository=_FakePolicyVersionRepository(),
            rollout_state_repository=_FakePolicyRolloutStateRepository(),
        )

        result = bootstrap_baseline_policy(
            repositories=repositories,
            rollout_id="offline-optimizer-default",
        )

        self.assertEqual(result.policy_version, DEFAULT_POLICY_VERSION)
        self.assertEqual(result.policy_action, "create")
        self.assertEqual(result.rollout_action, "create")
        self.assertTrue(result.wrote_policy_version)
        self.assertTrue(result.wrote_rollout_state)
        self.assertEqual(repositories.version_repository.save_calls, 1)
        self.assertEqual(repositories.rollout_state_repository.save_calls, 1)
        self.assertEqual(
            repositories.rollout_state_repository.record.base_policy_version,
            DEFAULT_POLICY_VERSION,
        )

    def test_bootstrap_skips_existing_seed_rows_for_idempotent_rerun(self) -> None:
        repositories = _RepositoryBundle(
            version_repository=_FakePolicyVersionRepository(
                {DEFAULT_POLICY_VERSION: _policy_record()}
            ),
            rollout_state_repository=_FakePolicyRolloutStateRepository(_rollout_state()),
        )

        result = bootstrap_baseline_policy(
            repositories=repositories,
            rollout_id="offline-optimizer-default",
        )

        self.assertFalse(result.wrote_policy_version)
        self.assertFalse(result.wrote_rollout_state)
        self.assertEqual(result.policy_action, "skip_existing")
        self.assertEqual(result.rollout_action, "skip_existing")
        self.assertEqual(repositories.version_repository.save_calls, 0)
        self.assertEqual(repositories.rollout_state_repository.save_calls, 0)

    def test_bootstrap_dry_run_reads_existing_state_without_writes(self) -> None:
        repositories = _RepositoryBundle(
            version_repository=_FakePolicyVersionRepository(),
            rollout_state_repository=_FakePolicyRolloutStateRepository(),
        )

        result = bootstrap_baseline_policy(
            repositories=repositories,
            rollout_id="offline-optimizer-default",
            dry_run=True,
        )

        self.assertTrue(result.dry_run)
        self.assertEqual(result.policy_action, "create")
        self.assertEqual(result.rollout_action, "create")
        self.assertFalse(result.wrote_policy_version)
        self.assertFalse(result.wrote_rollout_state)
        self.assertEqual(repositories.version_repository.save_calls, 0)
        self.assertEqual(repositories.rollout_state_repository.save_calls, 0)

    def test_bootstrap_cli_uses_env_rollout_id_and_prints_skip_or_write_contract(self) -> None:
        repositories = _RepositoryBundle(
            version_repository=_FakePolicyVersionRepository(),
            rollout_state_repository=_FakePolicyRolloutStateRepository(),
        )
        stdout = io.StringIO()

        with patch.dict(
            "os.environ",
            {"TM_POLICY_BOOTSTRAP_ROLLOUT_ID": "rollout-env"},
            clear=True,
        ):
            with patch(
                "traffic_master_ai.defense.backoffice_copilot.storage.policy_operations."
                "_build_bootstrap_repositories_from_env",
                return_value=repositories,
            ):
                with patch("sys.argv", ["tm-ai-policy-bootstrap"]):
                    with redirect_stdout(stdout):
                        run_policy_bootstrap()

        self.assertIn("rollout_id=rollout-env", stdout.getvalue())
        self.assertIn("policy_action=create", stdout.getvalue())
        self.assertIn("rollout_action=create", stdout.getvalue())
        self.assertIn("wrote_policy_version=true", stdout.getvalue())
        self.assertIn("wrote_rollout_state=true", stdout.getvalue())
        summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["command"], "tm-ai-policy-bootstrap")
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["output_count"], 2)
        self.assertTrue(repositories.disposed)

    def test_bootstrap_cli_disposes_repositories_after_failure(self) -> None:
        repositories = _RepositoryBundle(
            version_repository=_FailingPolicyVersionRepository(),
            rollout_state_repository=_FakePolicyRolloutStateRepository(),
        )
        stdout = io.StringIO()

        with patch(
            "traffic_master_ai.defense.backoffice_copilot.storage.policy_operations."
            "_build_bootstrap_repositories_from_env",
            return_value=repositories,
        ):
            with patch("sys.argv", ["tm-ai-policy-bootstrap", "--dry-run"]):
                with redirect_stdout(stdout):
                    with self.assertRaises(SystemExit):
                        run_policy_bootstrap()

        self.assertTrue(repositories.disposed)

    def test_projection_resync_cli_defaults_to_current_active_rollout(self) -> None:
        service, redis_client, rollout_repository = _service_with_fake_repositories()
        disposable_service = _DisposableService(service)
        stdout = io.StringIO()

        with patch(
            "traffic_master_ai.defense.backoffice_copilot.storage.policy_operations."
            "PostgresStrictPolicyAuthorityService.from_env",
            return_value=disposable_service,
        ):
            with patch("sys.argv", ["tm-ai-policy-projection-resync"]):
                with redirect_stdout(stdout):
                    run_policy_projection_resync()

        self.assertEqual(rollout_repository.current_calls, 1)
        self.assertIn(POLICY_ROLLOUT_STATE_KEY, redis_client.data)
        self.assertIn("wrote_rollout_state=true", stdout.getvalue())
        summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["command"], "tm-ai-policy-projection-resync")
        self.assertEqual(summary["scope"], "current")
        self.assertEqual(summary["status"], "success")
        self.assertTrue(disposable_service.disposed)

    def test_projection_resync_cli_can_target_specific_rollout_or_policy_version(self) -> None:
        service, redis_client, _ = _service_with_fake_repositories()

        with patch(
            "traffic_master_ai.defense.backoffice_copilot.storage.policy_operations."
            "PostgresStrictPolicyAuthorityService.from_env",
            return_value=service,
        ):
            with patch(
                "sys.argv",
                ["tm-ai-policy-projection-resync", "--rollout-id", "rollout-1"],
            ):
                run_policy_projection_resync()
            with patch(
                "sys.argv",
                ["tm-ai-policy-projection-resync", "--policy-version", "policy-v1"],
            ):
                run_policy_projection_resync()

        written_keys = [name for op, name, _ in redis_client.calls if op == "set"]
        self.assertIn(POLICY_ROLLOUT_STATE_KEY, written_keys)
        self.assertIn(f"{POLICY_VERSION_KEY_PREFIX}policy-v1", written_keys)
        self.assertIn(POLICY_VERSION_INDEX_KEY, written_keys)

    def test_bootstrap_cli_surfaces_migration_precondition_failure(self) -> None:
        repositories = _RepositoryBundle(
            version_repository=_FailingPolicyVersionRepository(),
            rollout_state_repository=_FakePolicyRolloutStateRepository(),
        )
        stdout = io.StringIO()

        with patch(
            "traffic_master_ai.defense.backoffice_copilot.storage.policy_operations."
            "_build_bootstrap_repositories_from_env",
            return_value=repositories,
        ):
            with patch("sys.argv", ["tm-ai-policy-bootstrap", "--dry-run"]):
                with redirect_stdout(stdout):
                    with self.assertRaises(SystemExit) as exc_info:
                        run_policy_bootstrap()

        self.assertEqual(exc_info.exception.code, 1)
        summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["error_count"], 1)
        self.assertIn("policy_versions", summary["error"])

    def test_projection_resync_cli_surfaces_missing_current_rollout(self) -> None:
        service, _, _ = _service_with_fake_repositories()
        service.rollout_state_repository = _FakePolicyRolloutStateRepository()
        disposable_service = _DisposableService(service)
        stdout = io.StringIO()

        with patch(
            "traffic_master_ai.defense.backoffice_copilot.storage.policy_operations."
            "PostgresStrictPolicyAuthorityService.from_env",
            return_value=disposable_service,
        ):
            with patch("sys.argv", ["tm-ai-policy-projection-resync", "--current"]):
                with redirect_stdout(stdout):
                    with self.assertRaises(SystemExit) as exc_info:
                        run_policy_projection_resync()

        self.assertEqual(exc_info.exception.code, 1)
        summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["scope"], "current")
        self.assertEqual(summary["status"], "failed")
        self.assertIn("policy_rollout_state", summary["error"])
        self.assertTrue(disposable_service.disposed)


def _service_with_fake_repositories() -> tuple[
    PostgresStrictPolicyAuthorityService,
    _FakeRedisClient,
    _FakePolicyRolloutStateRepository,
]:
    version_repository = _FakePolicyVersionRepository(
        {
            "policy-v1": _policy_record("policy-v1"),
            DEFAULT_POLICY_VERSION: _policy_record(DEFAULT_POLICY_VERSION),
        }
    )
    rollout_repository = _FakePolicyRolloutStateRepository(
        _rollout_state(rollout_id="rollout-1", policy_version="policy-v1")
    )
    redis_client = _FakeRedisClient()
    service = PostgresStrictPolicyAuthorityService(
        version_repository=version_repository,
        rollout_state_repository=rollout_repository,
        rollout_event_repository=_FakePolicyRolloutEventRepository(),
        optimization_run_repository=_FakePolicyOptimizationRunRepository(),
        projection_repository=RedisRuntimePolicyProjectionRepository(redis_client),
    )
    redis_client.set(POLICY_VERSION_INDEX_KEY, json.dumps([]))
    return service, redis_client, rollout_repository


if __name__ == "__main__":
    unittest.main()
