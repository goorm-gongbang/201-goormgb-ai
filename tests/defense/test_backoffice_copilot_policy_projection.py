from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

from traffic_master_ai.defense.backoffice_copilot.storage import (
    POLICY_ROLLOUT_STATE_KEY,
    POLICY_VERSION_INDEX_KEY,
    POLICY_VERSION_KEY_PREFIX,
    PostgresStrictPolicyAuthorityService,
    PolicyOptimizationRunRecord,
    PolicyProjectionNotFoundError,
    ProjectionRetryPolicy,
    PolicyRolloutEventRecord,
    PolicyRolloutStateRecord,
    PolicyRuntimeProjectionInput,
    PolicyVersionRecord,
    RedisProjectionApplyError,
    RedisRuntimePolicyProjectionRepository,
    apply_policy_runtime_projection,
    apply_policy_runtime_projection_with_retry,
    build_redis_projected_rollout_state,
    build_redis_projected_policy_document,
    load_policy_runtime_projection_input,
    project_policy_version_activation,
    project_rollout_state_change,
    reconcile_policy_runtime_projection,
    serialize_redis_projected_policy_document,
    serialize_redis_projected_rollout_state,
    serialize_redis_projected_version_index,
)


def _now() -> datetime:
    return datetime(2026, 4, 6, 11, 0, 0, tzinfo=UTC)


def _policy_record(version: str) -> PolicyVersionRecord:
    return PolicyVersionRecord(
        policy_version=version,
        schema_version="policy.v1",
        status="ACTIVE",
        source_type="OFFLINE_LLM",
        parent_policy_version=None,
        document_json={
            "schemaVersion": "policy.v1",
            "parameters": {
                "planner": {"action_matrix": {"T0": "NONE", "T1": "THROTTLE"}},
                "turnstile": {"enabled": True},
            },
            "flags": {"runtime_llm_enabled": False},
            "status": "should-not-project",
        },
        validation_result_json={"errors": []},
        created_at=_now(),
        validated_at=_now(),
        activated_at=_now(),
    )


def _rollout_state() -> PolicyRolloutStateRecord:
    return PolicyRolloutStateRecord(
        rollout_id="rollout-1",
        stage="CANARY",
        base_policy_version="policy-v1",
        candidate_policy_version="policy-v2",
        ratio=Decimal("0.05000"),
        evaluation_window_seconds=60,
        canary_duration_seconds=120,
        expand_step_index=None,
        stage_started_at_ms=1000,
        updated_at_ms=2000,
        current_status="ACTIVE",
        rollback_reason=None,
    )


class _FakeRedisClient:
    def __init__(self, *, failures_before_success: int = 0, always_return_false: bool = False) -> None:
        self.data: dict[str, object] = {}
        self.calls: list[tuple[str, str, object]] = []
        self.failures_before_success = failures_before_success
        self.always_return_false = always_return_false

    def set(self, name: str, value: object, ex: int | None = None, nx: bool = False) -> bool:
        if self.failures_before_success > 0:
            self.failures_before_success -= 1
            raise RuntimeError("redis unavailable")
        if self.always_return_false:
            self.calls.append(("set", name, value))
            return False
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


class _FakePolicyVersionRepository:
    def __init__(self, records: dict[str, PolicyVersionRecord]) -> None:
        self.records = records
        self.calls: list[str] = []

    def get_version(self, policy_version: str) -> PolicyVersionRecord | None:
        self.calls.append(policy_version)
        return self.records.get(policy_version)

    def save_version(self, record: PolicyVersionRecord) -> None:
        self.records[record.policy_version] = record


class _FakePolicyRolloutStateRepository:
    def __init__(self, record: PolicyRolloutStateRecord | None) -> None:
        self.record = record
        self.calls: list[str] = []

    def get_state(self, rollout_id: str) -> PolicyRolloutStateRecord | None:
        self.calls.append(rollout_id)
        return self.record if self.record and self.record.rollout_id == rollout_id else None

    def save_state(self, record: PolicyRolloutStateRecord) -> None:
        self.record = record


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


class BackofficeCopilotPolicyProjectionTests(unittest.TestCase):
    def test_projected_policy_document_keeps_runtime_payload_only(self) -> None:
        projected = build_redis_projected_policy_document(_policy_record("policy-v2"))
        payload = serialize_redis_projected_policy_document(projected)

        self.assertEqual(set(payload.keys()), {"schemaVersion", "parameters", "flags"})
        self.assertEqual(payload["schemaVersion"], "policy.v1")
        self.assertIn("planner", payload["parameters"])
        self.assertNotIn("status", payload)

    def test_rollout_projection_serializers_keep_runtime_minimum_fields_and_sorted_version_index(self) -> None:
        rollout_payload = serialize_redis_projected_rollout_state(
            build_redis_projected_rollout_state(_rollout_state())
        )
        version_index = serialize_redis_projected_version_index(
            ["policy-v2", "policy-v1", "policy-v2"]
        )

        self.assertEqual(
            tuple(rollout_payload.keys()),
            (
                "stage",
                "base_policy_version",
                "candidate_policy_version",
                "ratio",
                "updated_at_ms",
            ),
        )
        self.assertNotIn("current_status", rollout_payload)
        self.assertEqual(version_index, ["policy-v1", "policy-v2"])

    def test_rollout_projection_entrypoint_writes_documents_then_rollout_then_index(self) -> None:
        version_repository = _FakePolicyVersionRepository(
            {
                "policy-v1": _policy_record("policy-v1"),
                "policy-v2": _policy_record("policy-v2"),
            }
        )
        rollout_repository = _FakePolicyRolloutStateRepository(_rollout_state())
        redis_client = _FakeRedisClient()
        projection_repository = RedisRuntimePolicyProjectionRepository(redis_client)

        result = project_rollout_state_change(
            rollout_id="rollout-1",
            version_repository=version_repository,
            rollout_state_repository=rollout_repository,
            projection_repository=projection_repository,
        )

        self.assertEqual(
            [name for op, name, _ in redis_client.calls if op == "set"],
            [
                f"{POLICY_VERSION_KEY_PREFIX}policy-v1",
                f"{POLICY_VERSION_KEY_PREFIX}policy-v2",
                POLICY_ROLLOUT_STATE_KEY,
                POLICY_VERSION_INDEX_KEY,
            ],
        )
        rollout_payload = json.loads(str(redis_client.data[POLICY_ROLLOUT_STATE_KEY]))
        self.assertEqual(
            rollout_payload,
            {
                "stage": "CANARY",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "ratio": 0.05,
                "updated_at_ms": 2000,
            },
        )
        self.assertEqual(result.projected_policy_versions, ("policy-v1", "policy-v2"))
        self.assertEqual(result.version_index, ("policy-v1", "policy-v2"))
        self.assertTrue(result.wrote_rollout_state)

    def test_policy_version_activation_updates_version_doc_and_index_without_rollout_write(self) -> None:
        version_repository = _FakePolicyVersionRepository({"policy-v2": _policy_record("policy-v2")})
        redis_client = _FakeRedisClient()
        redis_client.set(POLICY_VERSION_INDEX_KEY, json.dumps(["policy-v1"]))
        projection_repository = RedisRuntimePolicyProjectionRepository(redis_client)

        result = project_policy_version_activation(
            policy_version="policy-v2",
            version_repository=version_repository,
            projection_repository=projection_repository,
        )

        self.assertEqual(
            [name for op, name, _ in redis_client.calls if op == "set"][-2:],
            [f"{POLICY_VERSION_KEY_PREFIX}policy-v2", POLICY_VERSION_INDEX_KEY],
        )
        self.assertNotIn(POLICY_ROLLOUT_STATE_KEY, redis_client.data)
        self.assertEqual(result.version_index, ("policy-v1", "policy-v2"))
        self.assertFalse(result.wrote_rollout_state)

    def test_load_and_reconcile_helpers_fail_fast_when_authoritative_rows_are_missing(self) -> None:
        version_repository = _FakePolicyVersionRepository({"policy-v1": _policy_record("policy-v1")})
        rollout_repository = _FakePolicyRolloutStateRepository(_rollout_state())
        projection_repository = RedisRuntimePolicyProjectionRepository(_FakeRedisClient())

        with self.assertRaises(PolicyProjectionNotFoundError):
            load_policy_runtime_projection_input(
                rollout_id="rollout-1",
                version_repository=version_repository,
                rollout_state_repository=rollout_repository,
            )

        with self.assertRaises(PolicyProjectionNotFoundError):
            reconcile_policy_runtime_projection(
                rollout_id="rollout-1",
                version_repository=version_repository,
                rollout_state_repository=rollout_repository,
                projection_repository=projection_repository,
            )

    def test_apply_projection_uses_existing_index_for_reconcile_safe_union(self) -> None:
        projection_repository = RedisRuntimePolicyProjectionRepository(_FakeRedisClient())
        projection_repository.project_version_index(("policy-v0",))
        projection_input = PolicyRuntimeProjectionInput(
            policy_versions=(_policy_record("policy-v1"),),
            rollout_state=None,
        )

        result = apply_policy_runtime_projection(
            projection_input,
            projection_repository=projection_repository,
        )

        self.assertEqual(result.projected_policy_versions, ("policy-v1",))
        self.assertEqual(result.version_index, ("policy-v0", "policy-v1"))
        self.assertFalse(result.wrote_rollout_state)

    def test_projection_retry_helper_retries_transient_redis_failure(self) -> None:
        projection_repository = RedisRuntimePolicyProjectionRepository(
            _FakeRedisClient(failures_before_success=1)
        )
        projection_input = PolicyRuntimeProjectionInput(
            policy_versions=(_policy_record("policy-v1"),),
            rollout_state=None,
        )

        result = apply_policy_runtime_projection_with_retry(
            projection_input,
            projection_repository=projection_repository,
            retry_policy=ProjectionRetryPolicy(max_attempts=2, backoff_ms=0),
            scope="policy_version:policy-v1",
        )

        self.assertEqual(result.projected_policy_versions, ("policy-v1",))
        self.assertEqual(result.version_index, ("policy-v1",))

    def test_projection_failure_raises_typed_error_with_reconcile_hint(self) -> None:
        projection_repository = RedisRuntimePolicyProjectionRepository(
            _FakeRedisClient(always_return_false=True)
        )
        projection_input = PolicyRuntimeProjectionInput(
            policy_versions=(_policy_record("policy-v1"),),
            rollout_state=None,
        )

        with self.assertRaises(RedisProjectionApplyError) as exc_info:
            apply_policy_runtime_projection_with_retry(
                projection_input,
                projection_repository=projection_repository,
                retry_policy=ProjectionRetryPolicy(max_attempts=2, backoff_ms=0),
                scope="policy_version:policy-v1",
            )

        self.assertIn("reconcile_policy_runtime_projection", exc_info.exception.resync_hint)
        self.assertEqual(exc_info.exception.max_attempts, 2)

    def test_strict_authority_service_saves_rollout_state_and_syncs_runtime_projection(self) -> None:
        version_repository = _FakePolicyVersionRepository(
            {
                "policy-v1": _policy_record("policy-v1"),
                "policy-v2": _policy_record("policy-v2"),
            }
        )
        rollout_repository = _FakePolicyRolloutStateRepository(None)
        redis_client = _FakeRedisClient()
        service = PostgresStrictPolicyAuthorityService(
            version_repository=version_repository,
            rollout_state_repository=rollout_repository,
            rollout_event_repository=_FakePolicyRolloutEventRepository(),
            optimization_run_repository=_FakePolicyOptimizationRunRepository(),
            projection_repository=RedisRuntimePolicyProjectionRepository(redis_client),
        )

        result = service.save_rollout_state(_rollout_state())

        self.assertEqual(rollout_repository.record, _rollout_state())
        self.assertTrue(result.wrote_rollout_state)
        self.assertEqual(
            [name for op, name, _ in redis_client.calls if op == "set"],
            [
                f"{POLICY_VERSION_KEY_PREFIX}policy-v1",
                f"{POLICY_VERSION_KEY_PREFIX}policy-v2",
                POLICY_ROLLOUT_STATE_KEY,
                POLICY_VERSION_INDEX_KEY,
            ],
        )

    def test_strict_authority_service_resync_restores_evicted_runtime_rollout_key(self) -> None:
        version_repository = _FakePolicyVersionRepository(
            {
                "policy-v1": _policy_record("policy-v1"),
                "policy-v2": _policy_record("policy-v2"),
            }
        )
        rollout_repository = _FakePolicyRolloutStateRepository(_rollout_state())
        redis_client = _FakeRedisClient()
        service = PostgresStrictPolicyAuthorityService(
            version_repository=version_repository,
            rollout_state_repository=rollout_repository,
            rollout_event_repository=_FakePolicyRolloutEventRepository(),
            optimization_run_repository=_FakePolicyOptimizationRunRepository(),
            projection_repository=RedisRuntimePolicyProjectionRepository(redis_client),
        )
        service.save_rollout_state(_rollout_state())
        redis_client.delete(POLICY_ROLLOUT_STATE_KEY)

        result = service.resync_runtime_projection(rollout_id="rollout-1")

        self.assertTrue(result.wrote_rollout_state)
        self.assertIn(POLICY_ROLLOUT_STATE_KEY, redis_client.data)

    def test_strict_authority_service_from_env_uses_retry_env_and_validates_prod_contract(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "TM_ENV": "prod",
                "TM_PG_URL": "postgresql://user:pass@localhost:5432/tm",
                "TM_REDIS_URL": "redis://localhost:6379/0",
                "TM_PROJECTION_RETRY_MAX_ATTEMPTS": "4",
                "TM_PROJECTION_RETRY_BACKOFF_MS": "120",
                "TM_ALLOW_IN_MEMORY_REDIS": "false",
            },
            clear=True,
        ):
            with (
                patch(
                    "traffic_master_ai.defense.backoffice_copilot.storage.policy_projection_repository.build_postgres_engine_from_env",
                    return_value=object(),
                ),
                patch(
                    "traffic_master_ai.defense.backoffice_copilot.storage.policy_projection_repository.build_runtime_redis_from_env",
                    return_value=(_FakeRedisClient(), "redis"),
                ),
            ):
                service = PostgresStrictPolicyAuthorityService.from_env()

        self.assertEqual(service.projection_retry_policy.max_attempts, 4)
        self.assertEqual(service.projection_retry_policy.backoff_ms, 120)


if __name__ == "__main__":
    unittest.main()
