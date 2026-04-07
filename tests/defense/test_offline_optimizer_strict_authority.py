from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from traffic_master_ai.defense.backoffice_copilot.storage.policy_control_plane_models import (
    PolicyOptimizationRunRecord,
    PolicyRolloutEventRecord,
    PolicyRolloutStateRecord,
    PolicyVersionRecord,
)
from traffic_master_ai.defense.backoffice_copilot.storage.policy_projection_repository import (
    PostgresStrictPolicyAuthorityService,
    RedisRuntimePolicyProjectionRepository,
)
from traffic_master_ai.defense.d0_mvp.optimizer.pipeline import OfflineOptimizer
from traffic_master_ai.defense.d0_mvp.policy.loader import (
    InMemoryPolicyStore,
    PolicyLoader,
    RedisPolicyStore,
    resolve_policy_version,
    snapshot_to_document,
)
from traffic_master_ai.defense.d0_mvp.policy.snapshot import PolicySnapshot
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis


def _now() -> datetime:
    return datetime(2026, 4, 6, 16, 0, 0, tzinfo=UTC)


def _policy_record(version: str) -> PolicyVersionRecord:
    return PolicyVersionRecord(
        policy_version=version,
        schema_version="policy.v1",
        status="ACTIVE",
        source_type="test",
        document_json=snapshot_to_document(PolicySnapshot(policy_version=version)),
        created_at=_now(),
        activated_at=_now(),
    )


class _FakePolicyVersionRepository:
    def __init__(self, records: dict[str, PolicyVersionRecord]) -> None:
        self.records = dict(records)

    def get_version(self, policy_version: str) -> PolicyVersionRecord | None:
        return self.records.get(policy_version)

    def save_version(self, record: PolicyVersionRecord) -> None:
        self.records[record.policy_version] = record


class _FakePolicyRolloutStateRepository:
    def __init__(self, record: PolicyRolloutStateRecord | None = None) -> None:
        self.record = record

    def get_state(self, rollout_id: str) -> PolicyRolloutStateRecord | None:
        if self.record is None or self.record.rollout_id != rollout_id:
            return None
        return self.record

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


class _FakeWarehouse:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = list(rows or [])

    def read_all(self) -> list[dict[str, object]]:
        return list(self._rows)

    def query(self, **kwargs: object) -> list[dict[str, object]]:
        limit = kwargs.get("limit")
        rows = list(self._rows)
        if isinstance(limit, int) and limit >= 0:
            return rows[:limit]
        return rows


class _NoProposalEffectEvaluator:
    def propose(self, **kwargs: object):
        return None


class _NoSummary:
    report_id = None


class _NoSummaryAuditSummarizer:
    def summarize(self, **kwargs: object):
        return _NoSummary()

    def latest(self):
        return None


def _find_candidate_session_id(rollout_state: dict[str, object], *, salt: str) -> str:
    for idx in range(200000):
        session_id = f"strict-authority-session-{idx}"
        if (
            resolve_policy_version(session_id, rollout_state, salt)
            == rollout_state.get("candidate_policy_version")
        ):
            return session_id
    raise AssertionError("failed to find candidate session id for rollout state")


class OfflineOptimizerStrictAuthorityTests(unittest.TestCase):
    def test_offline_optimizer_rollout_writes_flow_through_strict_authority_service(self) -> None:
        redis = InMemoryRedis()
        base_version = PolicySnapshot().policy_version
        version_repository = _FakePolicyVersionRepository({base_version: _policy_record(base_version)})
        rollout_repository = _FakePolicyRolloutStateRepository()
        rollout_event_repository = _FakePolicyRolloutEventRepository()
        optimization_run_repository = _FakePolicyOptimizationRunRepository()
        authority = PostgresStrictPolicyAuthorityService(
            version_repository=version_repository,
            rollout_state_repository=rollout_repository,
            rollout_event_repository=rollout_event_repository,
            optimization_run_repository=optimization_run_repository,
            projection_repository=RedisRuntimePolicyProjectionRepository(redis),
        )
        authority.save_policy_version(_policy_record(base_version), project_to_runtime=True)
        authority.save_rollout_state(
            PolicyRolloutStateRecord(
                rollout_id="offline-optimizer-default",
                stage="FULL",
                base_policy_version=base_version,
                candidate_policy_version=None,
                ratio=Decimal("0.00000"),
                evaluation_window_seconds=60,
                canary_duration_seconds=120,
                stage_started_at_ms=1710000000000,
                updated_at_ms=1710000000000,
                current_status="ACTIVE",
            ),
            additional_policy_versions=(base_version,),
        )
        loader = PolicyLoader(
            store=RedisPolicyStore(redis),
            rollout_salt="strict-salt",
            cache_seconds=0,
            strict_authority=True,
        )
        optimizer = OfflineOptimizer(
            warehouse=_FakeWarehouse(),
            policy_loader=loader,
            authority_service=authority,
            audit_summarizer=_NoSummaryAuditSummarizer(),
            audit_file=str(Path("/tmp/tm-offline-optimizer-authority-audit.jsonl")),
        )

        proposal = {
            "proposal_id": "proposal-1",
            "base_policy_version": base_version,
            "patches": [
                {"path": "risk.alpha", "op": "set", "value": 0.31, "why": "canary test"}
            ],
            "rationale": "small reversible change",
            "confidence": 0.8,
            "rollback_conditions": ["block_rate increases > +0.3%p"],
            "notes": "strict authority smoke",
        }

        start_result = optimizer.start_canary(proposal=proposal, ratio=0.05)
        current_rollout = optimizer.current_rollout_state()
        self.assertIsNotNone(current_rollout)
        self.assertEqual(current_rollout["stage"], "CANARY")
        self.assertEqual(len(rollout_event_repository.records), 1)
        self.assertEqual(rollout_event_repository.records[0].event_type, "OFFLINE_OPT_CANARY_STARTED")

        candidate_version = start_result["candidatePolicyVersion"]
        self.assertIn(candidate_version, version_repository.records)
        strict_session = _find_candidate_session_id(current_rollout or {}, salt="strict-salt")
        self.assertEqual(loader.load(strict_session).policy_version, candidate_version)

        expanded = optimizer.expand_rollout(step_index=0)
        self.assertEqual(expanded["stage"], "EXPAND")
        self.assertEqual(len(rollout_event_repository.records), 2)
        self.assertEqual(rollout_event_repository.records[-1].event_type, "OFFLINE_OPT_ROLLOUT_EXPANDED")
        self.assertEqual(loader.load(strict_session).policy_version, candidate_version)

        rolled_back = optimizer.rollback()
        self.assertEqual(rolled_back["stage"], "ROLLED_BACK")
        self.assertEqual(len(rollout_event_repository.records), 3)
        self.assertEqual(rollout_event_repository.records[-1].event_type, "OFFLINE_OPT_ROLLBACK_TRIGGERED")
        self.assertEqual(loader.load(strict_session).policy_version, base_version)

    def test_offline_optimizer_run_once_persists_optimization_run_via_authority_service(self) -> None:
        redis = InMemoryRedis()
        base_version = PolicySnapshot().policy_version
        authority = PostgresStrictPolicyAuthorityService(
            version_repository=_FakePolicyVersionRepository({base_version: _policy_record(base_version)}),
            rollout_state_repository=_FakePolicyRolloutStateRepository(),
            rollout_event_repository=_FakePolicyRolloutEventRepository(),
            optimization_run_repository=_FakePolicyOptimizationRunRepository(),
            projection_repository=RedisRuntimePolicyProjectionRepository(redis),
        )
        loader = PolicyLoader(store=InMemoryPolicyStore(), cache_seconds=0)
        optimizer = OfflineOptimizer(
            warehouse=_FakeWarehouse(),
            policy_loader=loader,
            effect_evaluator=_NoProposalEffectEvaluator(),
            audit_summarizer=_NoSummaryAuditSummarizer(),
            authority_service=authority,
            audit_file=str(Path("/tmp/tm-offline-optimizer-run-audit.jsonl")),
        )

        result = optimizer.run_once(window_seconds=60)
        run_records = list(authority.optimization_run_repository.records.values())

        self.assertEqual(len(run_records), 1)
        self.assertEqual(run_records[0].base_policy_version, base_version)
        self.assertEqual(run_records[0].result_status, "NO_CHANGE")
        self.assertEqual(run_records[0].metrics_snapshot_id, result["metricsSnapshotId"])


if __name__ == "__main__":
    unittest.main()
