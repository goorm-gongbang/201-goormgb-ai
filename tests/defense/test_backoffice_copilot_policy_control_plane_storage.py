from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from traffic_master_ai.defense.backoffice_copilot.storage import (
    PkConflictPolicy,
    PolicyOptimizationRunRecord,
    PolicyRolloutEventRecord,
    PolicyRolloutStateRecord,
    PolicyVersionRecord,
    PostgresControlPlaneWriteError,
    PostgresPolicyOptimizationRunRepository,
    PostgresPolicyRolloutEventRepository,
    PostgresPolicyRolloutStateRepository,
    PostgresPolicyVersionRepository,
    parse_policy_rollout_event_record,
    serialize_policy_optimization_run_record,
    serialize_policy_rollout_state_record,
    serialize_policy_version_record,
)
from traffic_master_ai.defense.backoffice_copilot.storage.validators import StorageValidationError


def _now() -> datetime:
    return datetime(2026, 4, 6, 10, 30, 0, tzinfo=UTC)


def _policy_version_record() -> PolicyVersionRecord:
    return PolicyVersionRecord(
        policy_version="policy-v2",
        schema_version="policy.v1",
        status="VALIDATED",
        source_type="OFFLINE_LLM",
        parent_policy_version="policy-v1",
        document_json={
            "schemaVersion": "policy.v1",
            "parameters": {
                "turnstile": {"enabled": True},
                "planner": {"action_matrix": {"T0": "NONE", "T1": "THROTTLE"}},
            },
        },
        validation_result_json={"errors": [], "warnings": ["none"]},
        created_at=_now(),
        validated_at=_now(),
        activated_at=None,
    )


def _rollout_state_record() -> PolicyRolloutStateRecord:
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


def _rollout_event_record() -> PolicyRolloutEventRecord:
    return PolicyRolloutEventRecord(
        event_id="event-1",
        rollout_id="rollout-1",
        event_type="OFFLINE_OPT_CANARY_STARTED",
        base_policy_version="policy-v1",
        candidate_policy_version="policy-v2",
        stage_before="FULL",
        stage_after="CANARY",
        ratio_before=Decimal("0.00000"),
        ratio_after=Decimal("0.05000"),
        reason_json={"trigger": "optimizer"},
        metrics_snapshot_json={"block_rate_pp": 0.02},
        created_at=_now(),
    )


def _optimization_run_record() -> PolicyOptimizationRunRecord:
    return PolicyOptimizationRunRecord(
        run_id="run-1",
        base_policy_version="policy-v1",
        proposed_policy_version="policy-v2",
        trigger_type="WINDOW_DRIFT",
        metrics_snapshot_id="metrics-1",
        window_start_ms=100,
        window_end_ms=200,
        metrics_snapshot_json={"window_size": 100},
        proposal_json={"candidate": "policy-v2"},
        validation_result_json={"errors": []},
        result_status="COMPLETED",
        created_at=_now(),
        finished_at=_now(),
    )


class _FakeConnection:
    pass


class _FakeBegin:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> _FakeConnection:
        return self.connection

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeEngine:
    def __init__(self) -> None:
        self.connection = _FakeConnection()

    def begin(self) -> _FakeBegin:
        return _FakeBegin(self.connection)


class _InspectablePolicyVersionRepository(PostgresPolicyVersionRepository):
    def __init__(self, *, fetch_row: dict[str, object] | None = None, fail_execute: bool = False) -> None:
        super().__init__(engine=_FakeEngine(), conflict_policy=PkConflictPolicy.UPSERT)
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.fetch_row = fetch_row
        self.fail_execute = fail_execute

    def _execute(self, connection, sql_text: str, params: dict[str, object]) -> None:
        if self.fail_execute:
            raise RuntimeError("pg unavailable")
        self.executed.append((sql_text, params))

    def _fetch_one(self, connection, sql_text: str, params: dict[str, object]) -> dict[str, object] | None:
        self.executed.append((sql_text, params))
        return self.fetch_row


class _InspectablePolicyRolloutStateRepository(PostgresPolicyRolloutStateRepository):
    def __init__(self, *, fetch_row: dict[str, object] | None = None, fail_execute: bool = False) -> None:
        super().__init__(engine=_FakeEngine(), conflict_policy=PkConflictPolicy.UPSERT)
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.fetch_row = fetch_row
        self.fail_execute = fail_execute

    def _execute(self, connection, sql_text: str, params: dict[str, object]) -> None:
        if self.fail_execute:
            raise RuntimeError("pg unavailable")
        self.executed.append((sql_text, params))

    def _fetch_one(self, connection, sql_text: str, params: dict[str, object]) -> dict[str, object] | None:
        self.executed.append((sql_text, params))
        return self.fetch_row


class _InspectablePolicyRolloutEventRepository(PostgresPolicyRolloutEventRepository):
    def __init__(self, *, fetch_rows: list[dict[str, object]] | None = None, fail_execute: bool = False) -> None:
        super().__init__(engine=_FakeEngine())
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.fetch_rows = fetch_rows or []
        self.fail_execute = fail_execute

    def _execute(self, connection, sql_text: str, params: dict[str, object]) -> None:
        if self.fail_execute:
            raise RuntimeError("pg unavailable")
        self.executed.append((sql_text, params))

    def _fetch_all(self, connection, sql_text: str, params: dict[str, object]) -> list[dict[str, object]]:
        self.executed.append((sql_text, params))
        return self.fetch_rows


class _InspectablePolicyOptimizationRunRepository(PostgresPolicyOptimizationRunRepository):
    def __init__(self, *, fetch_row: dict[str, object] | None = None, fail_execute: bool = False) -> None:
        super().__init__(engine=_FakeEngine(), conflict_policy=PkConflictPolicy.UPSERT)
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.fetch_row = fetch_row
        self.fail_execute = fail_execute

    def _execute(self, connection, sql_text: str, params: dict[str, object]) -> None:
        if self.fail_execute:
            raise RuntimeError("pg unavailable")
        self.executed.append((sql_text, params))

    def _fetch_one(self, connection, sql_text: str, params: dict[str, object]) -> dict[str, object] | None:
        self.executed.append((sql_text, params))
        return self.fetch_row


class BackofficeCopilotPolicyControlPlaneStorageTests(unittest.TestCase):
    def test_policy_version_contract_matches_current_snapshot_document_shape(self) -> None:
        payload = serialize_policy_version_record(_policy_version_record())

        self.assertEqual(payload["policy_version"], "policy-v2")
        self.assertEqual(payload["schema_version"], "policy.v1")
        self.assertIn("parameters", payload["document_json"])
        self.assertIn("turnstile", payload["document_json"]["parameters"])

    def test_rollout_state_and_optimization_run_serializers_reject_invalid_ranges(self) -> None:
        invalid_state = PolicyRolloutStateRecord(
            rollout_id="rollout-2",
            stage="CANARY",
            base_policy_version="policy-v1",
            candidate_policy_version="policy-v2",
            ratio=Decimal("1.10000"),
            evaluation_window_seconds=60,
            canary_duration_seconds=120,
            expand_step_index=None,
            stage_started_at_ms=2000,
            updated_at_ms=1000,
            current_status="ACTIVE",
            rollback_reason=None,
        )
        with self.assertRaises(StorageValidationError):
            serialize_policy_rollout_state_record(invalid_state)

        invalid_run = PolicyOptimizationRunRecord(
            run_id="run-2",
            base_policy_version="policy-v1",
            proposed_policy_version="policy-v2",
            trigger_type="WINDOW_DRIFT",
            metrics_snapshot_id="metrics-2",
            window_start_ms=300,
            window_end_ms=200,
            metrics_snapshot_json=None,
            proposal_json=None,
            validation_result_json=None,
            result_status="FAILED",
            created_at=_now(),
            finished_at=_now(),
        )
        with self.assertRaises(StorageValidationError):
            serialize_policy_optimization_run_record(invalid_run)

    def test_policy_version_repository_only_handles_authoritative_policy_document_reads_and_writes(self) -> None:
        record = _policy_version_record()
        repository = _InspectablePolicyVersionRepository(fetch_row=serialize_policy_version_record(record))

        repository.save_version(record)
        loaded = repository.get_version("policy-v2")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.policy_version, "policy-v2")
        self.assertIn("INSERT INTO policy_versions", repository.executed[0][0])
        self.assertIn("ON CONFLICT (policy_version)", repository.executed[0][0])
        self.assertIn("FROM policy_versions", repository.executed[1][0])

    def test_policy_version_repository_fail_fast_conflict_policy_keeps_plain_insert_contract(self) -> None:
        repository = _InspectablePolicyVersionRepository()
        repository.conflict_policy = PkConflictPolicy.FAIL_FAST

        repository.save_version(_policy_version_record())

        self.assertIn("INSERT INTO policy_versions", repository.executed[0][0])
        self.assertNotIn("ON CONFLICT", repository.executed[0][0])

    def test_rollout_state_and_event_repositories_keep_state_upsert_separate_from_append_only_history(self) -> None:
        state_record = _rollout_state_record()
        event_row = {
            "event_id": "event-1",
            "rollout_id": "rollout-1",
            "event_type": "OFFLINE_OPT_CANARY_STARTED",
            "base_policy_version": "policy-v1",
            "candidate_policy_version": "policy-v2",
            "stage_before": "FULL",
            "stage_after": "CANARY",
            "ratio_before": Decimal("0.00000"),
            "ratio_after": Decimal("0.05000"),
            "reason_json": {"trigger": "optimizer"},
            "metrics_snapshot_json": {"block_rate_pp": 0.02},
            "created_at": _now(),
        }
        state_repository = _InspectablePolicyRolloutStateRepository(
            fetch_row=serialize_policy_rollout_state_record(state_record)
        )
        event_repository = _InspectablePolicyRolloutEventRepository(fetch_rows=[event_row])

        state_repository.save_state(state_record)
        loaded_state = state_repository.get_state("rollout-1")
        event_repository.append_event(_rollout_event_record())
        loaded_events = event_repository.list_events("rollout-1")

        self.assertIsNotNone(loaded_state)
        self.assertEqual(loaded_state.current_status, "ACTIVE")
        self.assertIn("INSERT INTO policy_rollout_state", state_repository.executed[0][0])
        self.assertIn("ON CONFLICT (rollout_id)", state_repository.executed[0][0])
        self.assertIn("INSERT INTO policy_rollout_events", event_repository.executed[0][0])
        self.assertNotIn("ON CONFLICT", event_repository.executed[0][0])
        self.assertEqual(tuple(event.event_id for event in loaded_events), ("event-1",))

    def test_optimization_run_repository_handles_write_then_read_without_runtime_projection_logic(self) -> None:
        record = _optimization_run_record()
        repository = _InspectablePolicyOptimizationRunRepository(
            fetch_row=serialize_policy_optimization_run_record(record)
        )

        repository.save_run(record)
        loaded = repository.get_run("run-1")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.metrics_snapshot_id, "metrics-1")
        self.assertIn("INSERT INTO policy_optimization_runs", repository.executed[0][0])
        self.assertIn("ON CONFLICT (run_id)", repository.executed[0][0])
        self.assertIn("FROM policy_optimization_runs", repository.executed[1][0])
        self.assertNotIn("redis", repository.executed[0][0].lower())

    def test_authoritative_write_failures_raise_typed_postgres_control_plane_error(self) -> None:
        version_repository = _InspectablePolicyVersionRepository(fail_execute=True)
        rollout_state_repository = _InspectablePolicyRolloutStateRepository(fail_execute=True)
        event_repository = _InspectablePolicyRolloutEventRepository(fail_execute=True)
        run_repository = _InspectablePolicyOptimizationRunRepository(fail_execute=True)

        with self.assertRaises(PostgresControlPlaneWriteError) as version_exc:
            version_repository.save_version(_policy_version_record())
        with self.assertRaises(PostgresControlPlaneWriteError) as state_exc:
            rollout_state_repository.save_state(_rollout_state_record())
        with self.assertRaises(PostgresControlPlaneWriteError) as event_exc:
            event_repository.append_event(_rollout_event_record())
        with self.assertRaises(PostgresControlPlaneWriteError) as run_exc:
            run_repository.save_run(_optimization_run_record())

        self.assertEqual(version_exc.exception.table_name, "policy_versions")
        self.assertEqual(state_exc.exception.table_name, "policy_rollout_state")
        self.assertEqual(event_exc.exception.table_name, "policy_rollout_events")
        self.assertEqual(run_exc.exception.table_name, "policy_optimization_runs")
        self.assertIn("Redis projection", version_exc.exception.recovery_hint)

    def test_rollout_event_parser_keeps_append_only_metrics_payload_shape(self) -> None:
        parsed = parse_policy_rollout_event_record(
            {
                "event_id": "event-2",
                "rollout_id": "rollout-2",
                "event_type": "OFFLINE_OPT_ROLLOUT_EXPANDED",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "stage_before": "CANARY",
                "stage_after": "EXPAND",
                "ratio_before": Decimal("0.05000"),
                "ratio_after": Decimal("0.20000"),
                "reason_json": {"guardrail_passed": True},
                "metrics_snapshot_json": {"dedup_duplicate_rate_pp": 0.01},
                "created_at": _now(),
            }
        )

        self.assertEqual(parsed.stage_after, "EXPAND")
        self.assertEqual(parsed.ratio_after, Decimal("0.20000"))
        self.assertIn("dedup_duplicate_rate_pp", parsed.metrics_snapshot_json or {})


if __name__ == "__main__":
    unittest.main()
