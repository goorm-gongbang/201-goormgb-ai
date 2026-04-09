from __future__ import annotations

import hashlib
import os
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from io import BytesIO
from unittest.mock import patch

from traffic_master_ai.defense.api.etl_worker import ETLIngestError, ETLWorker
from traffic_master_ai.defense.backoffice_copilot.storage import (
    ClickHouseAuditEventInsertRow,
    ClickHouseAuditEventWriterRepository,
    ClickHouseBatchWriteRequest,
    ClickHouseBatchWriteRetryPolicy,
    ClickHouseMatchRollupQuery,
    ClickHousePostReviewCandidateQuery,
    ClickHouseSessionRollupQuery,
    ClickHouseWriteConfig,
    PostgresStrictPolicyAuthorityService,
    RedisRuntimePolicyProjectionRepository,
    build_clickhouse_match_rollup_reader_repository,
    build_clickhouse_post_review_candidate_reader_repository,
    build_clickhouse_read_model_config_from_env,
    build_clickhouse_session_rollup_reader_repository,
    build_clickhouse_write_config_from_env,
    load_backoffice_clickhouse_read_model_input,
    project_rollout_state_change,
    reconcile_policy_runtime_projection,
)
from traffic_master_ai.defense.backoffice_copilot.storage.policy_control_plane_models import (
    PolicyOptimizationRunRecord,
    PolicyRolloutEventRecord,
    PolicyRolloutStateRecord,
    PolicyVersionRecord,
)
from traffic_master_ai.defense.storage_env import ETLWorkerConfig, S3ArchiveConfig, PostgresStorageConfig, ClickHouseStorageConfig
from traffic_master_ai.defense.d0_mvp.policy.loader import (
    PolicyLoader,
    RedisPolicyStore,
    resolve_policy_version,
    snapshot_to_document,
)
from traffic_master_ai.defense.d0_mvp.policy.snapshot import PolicySnapshot
from traffic_master_ai.defense.d0_mvp.state.keyspace import POLICY_ROLLOUT_STATE_KEY, POLICY_VERSION_KEY_PREFIX
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis, build_runtime_redis_from_env


def _now() -> datetime:
    return datetime(2026, 4, 6, 12, 0, 0, tzinfo=UTC)


def _policy_record(version: str) -> PolicyVersionRecord:
    snapshot = PolicySnapshot(policy_version=version)
    return PolicyVersionRecord(
        policy_version=version,
        schema_version="policy.v1",
        status="ACTIVE",
        source_type="OFFLINE_LLM",
        parent_policy_version=None,
        document_json=snapshot_to_document(snapshot),
        validation_result_json={"errors": []},
        created_at=_now(),
        validated_at=_now(),
        activated_at=_now(),
    )


def _rollout_state_record() -> PolicyRolloutStateRecord:
    return PolicyRolloutStateRecord(
        rollout_id="rollout-smoke-1",
        stage="CANARY",
        base_policy_version="policy-v1",
        candidate_policy_version="policy-v2",
        ratio=Decimal("0.50000"),
        evaluation_window_seconds=60,
        canary_duration_seconds=120,
        expand_step_index=None,
        stage_started_at_ms=1710000000000,
        updated_at_ms=1710000005000,
        current_status="ACTIVE",
        rollback_reason=None,
    )


class _FakeClickHouseBatchClient:
    def __init__(self, *, failures_before_success: int = 0) -> None:
        self.calls: list[tuple[str, list[dict[str, object]]]] = []
        self.failures_before_success = failures_before_success

    def execute(self, sql_text: str, rows: list[dict[str, object]]) -> None:
        if self.failures_before_success > 0:
            self.failures_before_success -= 1
            raise RuntimeError("clickhouse unavailable")
        self.calls.append((sql_text, rows))


class _FakeS3Client:
    def __init__(self, *, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.list_calls: list[dict[str, object]] = []
        self.get_calls: list[tuple[str, str]] = []
        self.head_calls: list[tuple[str, str]] = []

    def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
        self.list_calls.append(dict(kwargs))
        prefix = str(kwargs.get("Prefix", ""))
        return {
            "Contents": [
                {"Key": key, "ETag": self._etag_for_key(key)}
                for key in sorted(self.objects)
                if key.startswith(prefix)
            ],
            "IsTruncated": False,
        }

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        self.head_calls.append((Bucket, Key))
        return {
            "ETag": self._etag_for_key(Key),
        }

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        self.get_calls.append((Bucket, Key))
        return {
            "Body": BytesIO(self.objects[Key]),
        }

    def _etag_for_key(self, key: str) -> str:
        return f'"{hashlib.md5(self.objects[key]).hexdigest()}"'


class _FakeClickHouseSelectClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def query(self, sql_text: str, params: dict[str, object]) -> list[dict[str, object]]:
        self.calls.append((sql_text, params))
        if "candidate_view_smoke" in sql_text:
            return [
                {
                    "window_start_ms": 100,
                    "window_end_ms": 200,
                    "session_id": "sess-candidate",
                    "first_ts_ms": 120,
                    "last_ts_ms": 180,
                    "latest_action": "THROTTLE",
                    "latest_risk_tier": "T2",
                    "latest_reason_code": "RULE_HIT",
                    "latest_policy_version": "policy-v2",
                    "block_action_count": 0,
                    "throttle_action_count": 1,
                    "challenge_issue_count": 1,
                    "challenge_verified_count": 0,
                    "candidate_reason": "throttle_action_detected",
                }
            ]
        if "match_rollups_smoke" in sql_text:
            return [
                {
                    "window_start_ms": 100,
                    "window_end_ms": 200,
                    "match_id": "687",
                    "session_count": 2,
                    "event_count": 5,
                    "block_action_count": 0,
                    "throttle_action_count": 1,
                    "challenge_issue_count": 1,
                    "challenge_verified_count": 1,
                    "latest_policy_version": "policy-v2",
                }
            ]
        return [
            {
                "window_start_ms": 100,
                "window_end_ms": 200,
                "session_id": "sess-rollup",
                "first_ts_ms": 110,
                "last_ts_ms": 190,
                "event_count": 4,
                "latest_flow_state": "F4M",
                "latest_action": "THROTTLE",
                "latest_risk_tier": "T2",
                "latest_reason_code": "RULE_HIT",
                "latest_policy_version": "policy-v2",
                "throttle_action_count": 1,
                "block_action_count": 0,
                "challenge_issue_count": 1,
                "challenge_verified_count": 1,
            }
        ]


class _FakePolicyVersionRepository:
    def __init__(self, records: dict[str, PolicyVersionRecord]) -> None:
        self.records = records

    def get_version(self, policy_version: str) -> PolicyVersionRecord | None:
        return self.records.get(policy_version)


class _FakePolicyRolloutStateRepository:
    def __init__(self, record: PolicyRolloutStateRecord) -> None:
        self.record = record

    def get_state(self, rollout_id: str) -> PolicyRolloutStateRecord | None:
        return self.record if rollout_id == self.record.rollout_id else None

    def save_state(self, record: PolicyRolloutStateRecord) -> None:
        self.record = record


class _FakePolicyRolloutEventRepository:
    def append_event(self, record: PolicyRolloutEventRecord) -> None:
        self.record = record


class _FakePolicyOptimizationRunRepository:
    def save_run(self, record: PolicyOptimizationRunRecord) -> None:
        self.record = record


def _find_candidate_session_id(rollout_state: dict[str, object], *, salt: str) -> str:
    for index in range(5000):
        session_id = f"smoke-session-{index}"
        if resolve_policy_version(session_id, rollout_state, salt) == "policy-v2":
            return session_id
    raise AssertionError("could not find deterministic candidate session for smoke test")


class BackofficeCopilotDBSmokeTests(unittest.TestCase):
    def test_archive_to_clickhouse_ingest_smoke_uses_real_etl_path(self) -> None:
        client = _FakeClickHouseBatchClient()
        s3 = _FakeS3Client(
            objects={
                "ai-defense/audit/2026/04/06/audit_1.jsonl": (
                    b'{"ts_ms":1710000000000,"session_id":"sess-1","trace_id":"trace-1","event_type":"EVALUATE","flow_state":"F4M","risk_tier":"T2","action":"THROTTLE","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{"path":"/matches/1"}}\n'
                    b'{"ts_ms":1710000000000,"session_id":"sess-1","trace_id":"trace-1","event_type":"EVALUATE","flow_state":"F4M","risk_tier":"T2","action":"THROTTLE","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{"path":"/matches/1"}}\n'
                    b'{"ts_ms":1710000000100,"session_id":"sess-1","challenge_id":"challenge-1","event_type":"CHALLENGE_VERIFIED","raw_payload":{"result":"PASS"}}\n'
                ),
            }
        )
        worker = ETLWorker(
            config=ETLWorkerConfig(
                s3=S3ArchiveConfig(bucket="audit-bucket", prefix="ai-defense/audit/"),
                postgres=PostgresStorageConfig(url=None),
                clickhouse=ClickHouseStorageConfig(
                    url="clickhouse://localhost:8123/default",
                    audit_table="defense_audit_events_smoke",
                    ingest_batch_size=2,
                    ingest_timeout_ms=4000,
                ),
            ),
            s3_client=s3,
            clickhouse_writer=ClickHouseAuditEventWriterRepository(
                client=client,
                config=ClickHouseWriteConfig(
                    url="clickhouse://localhost:8123/default",
                    table_name="defense_audit_events_smoke",
                    batch_size=2,
                    timeout_ms=4000,
                ),
            ),
            processed_key_redis=InMemoryRedis(),
        )

        accepted_row_count = worker.run_once()

        self.assertEqual(accepted_row_count, 2)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(s3.get_calls, [("audit-bucket", "ai-defense/audit/2026/04/06/audit_1.jsonl")])
        _, rows = client.calls[0]
        self.assertEqual(rows[0]["risk_tier"], "T2")
        self.assertEqual(rows[1]["challenge_id"], "challenge-1")

    def test_archive_replay_key_smoke_reingests_one_explicit_s3_object(self) -> None:
        client = _FakeClickHouseBatchClient()
        key = "ai-defense/audit/2026/04/06/replay_audit.jsonl"
        s3 = _FakeS3Client(
            objects={
                key: (
                    b'{"ts_ms":1710000000200,"session_id":"sess-replay","event_type":"EVALUATE","action":"BLOCK","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{}}\n'
                ),
            }
        )
        worker = ETLWorker(
            config=ETLWorkerConfig(
                s3=S3ArchiveConfig(bucket="audit-bucket", prefix="ai-defense/audit/"),
                postgres=PostgresStorageConfig(url=None),
                clickhouse=ClickHouseStorageConfig(
                    url="clickhouse://localhost:8123/default",
                    audit_table="defense_audit_events_smoke",
                ),
            ),
            s3_client=s3,
            clickhouse_writer=ClickHouseAuditEventWriterRepository(
                client=client,
                config=ClickHouseWriteConfig(
                    url="clickhouse://localhost:8123/default",
                    table_name="defense_audit_events_smoke",
                    batch_size=1000,
                    timeout_ms=5000,
                ),
            ),
            processed_key_redis=InMemoryRedis(),
        )

        result = worker.replay_key(key)

        self.assertEqual(result.accepted_row_count, 1)
        self.assertEqual(result.duplicate_row_count, 0)
        self.assertEqual(len(client.calls), 1)

    def test_archive_replay_key_smoke_tracks_multi_flush_result_for_short_batch_size(self) -> None:
        client = _FakeClickHouseBatchClient()
        key = "ai-defense/audit/2026/04/06/short_interval_audit.jsonl"
        s3 = _FakeS3Client(
            objects={
                key: (
                    b'{"ts_ms":1710000000200,"session_id":"sess-1","event_type":"EVALUATE","action":"THROTTLE","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{"rank":1}}\n'
                    b'{"ts_ms":1710000000201,"session_id":"sess-2","event_type":"EVALUATE","action":"THROTTLE","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{"rank":2}}\n'
                    b'{"ts_ms":1710000000202,"session_id":"sess-3","event_type":"EVALUATE","action":"THROTTLE","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{"rank":3}}\n'
                    b'{"ts_ms":1710000000203,"session_id":"sess-4","event_type":"EVALUATE","action":"THROTTLE","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{"rank":4}}\n'
                    b'{"ts_ms":1710000000204,"session_id":"sess-5","event_type":"EVALUATE","action":"THROTTLE","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{"rank":5}}\n'
                ),
            }
        )
        worker = ETLWorker(
            config=ETLWorkerConfig(
                s3=S3ArchiveConfig(bucket="audit-bucket", prefix="ai-defense/audit/"),
                postgres=PostgresStorageConfig(url=None),
                clickhouse=ClickHouseStorageConfig(
                    url="clickhouse://localhost:8123/default",
                    audit_table="defense_audit_events_smoke",
                    ingest_batch_size=2,
                    ingest_timeout_ms=4000,
                    write_retry_max_attempts=3,
                    write_retry_backoff_ms=200,
                ),
            ),
            s3_client=s3,
            clickhouse_writer=ClickHouseAuditEventWriterRepository(
                client=client,
                config=ClickHouseWriteConfig(
                    url="clickhouse://localhost:8123/default",
                    table_name="defense_audit_events_smoke",
                    batch_size=2,
                    timeout_ms=4000,
                ),
            ),
            processed_key_redis=InMemoryRedis(),
        )

        result = worker.replay_key(key)

        self.assertEqual(result.source_row_count, 5)
        self.assertEqual(result.attempted_row_count, 5)
        self.assertEqual(result.accepted_row_count, 5)
        self.assertEqual(result.duplicate_row_count, 0)
        self.assertEqual(result.flush_count, 3)
        self.assertEqual(result.batch_size, 2)
        self.assertEqual(result.retry_max_attempts, 3)
        self.assertEqual(result.retry_backoff_ms, 200)
        self.assertEqual(len(client.calls), 3)

    def test_archive_replay_key_smoke_surfaces_key_and_retry_context_on_failure(self) -> None:
        client = _FakeClickHouseBatchClient(failures_before_success=3)
        key = "ai-defense/audit/2026/04/06/failing_audit.jsonl"
        s3 = _FakeS3Client(
            objects={
                key: (
                    b'{"ts_ms":1710000000200,"session_id":"sess-fail","event_type":"EVALUATE","action":"BLOCK","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{}}\n'
                ),
            }
        )
        worker = ETLWorker(
            config=ETLWorkerConfig(
                s3=S3ArchiveConfig(bucket="audit-bucket", prefix="ai-defense/audit/"),
                postgres=PostgresStorageConfig(url=None),
                clickhouse=ClickHouseStorageConfig(
                    url="clickhouse://localhost:8123/default",
                    audit_table="defense_audit_events_smoke",
                    ingest_batch_size=1,
                    ingest_timeout_ms=4000,
                    write_retry_max_attempts=3,
                    write_retry_backoff_ms=0,
                ),
            ),
            s3_client=s3,
            clickhouse_writer=ClickHouseAuditEventWriterRepository(
                client=client,
                config=ClickHouseWriteConfig(
                    url="clickhouse://localhost:8123/default",
                    table_name="defense_audit_events_smoke",
                    batch_size=1,
                    timeout_ms=4000,
                ),
            ),
            processed_key_redis=InMemoryRedis(),
        )

        with self.assertRaises(ETLIngestError) as exc_info:
            worker.replay_key(key)

        self.assertIn(key, str(exc_info.exception))
        self.assertIn("retry_max_attempts=3", str(exc_info.exception))
        self.assertIn("flush_count=1", str(exc_info.exception))
        self.assertIn("last_error=ClickHouseBatchWriteError", str(exc_info.exception))

    def test_normal_ingest_skips_already_processed_object_across_runs(self) -> None:
        redis = InMemoryRedis()
        client = _FakeClickHouseBatchClient()
        key = "ai-defense/audit/2026/04/06/processed_audit.jsonl"
        s3 = _FakeS3Client(
            objects={
                key: (
                    b'{"ts_ms":1710000000300,"session_id":"sess-processed","event_type":"EVALUATE","action":"THROTTLE","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{}}\n'
                ),
            }
        )
        worker = ETLWorker(
            config=ETLWorkerConfig(
                s3=S3ArchiveConfig(bucket="audit-bucket", prefix="ai-defense/audit/"),
                postgres=PostgresStorageConfig(url=None),
                clickhouse=ClickHouseStorageConfig(
                    url="clickhouse://localhost:8123/default",
                    audit_table="defense_audit_events_smoke",
                ),
            ),
            s3_client=s3,
            clickhouse_writer=ClickHouseAuditEventWriterRepository(
                client=client,
                config=ClickHouseWriteConfig(
                    url="clickhouse://localhost:8123/default",
                    table_name="defense_audit_events_smoke",
                    batch_size=1000,
                    timeout_ms=5000,
                ),
            ),
            processed_key_redis=redis,
        )

        first_total = worker.run_once()
        second_total = worker.run_once()

        self.assertEqual(first_total, 1)
        self.assertEqual(second_total, 0)
        self.assertEqual(len(client.calls), 1)
        replay_result = worker.replay_key(key)
        self.assertTrue(replay_result.skipped_by_processed_ledger)
        self.assertEqual(replay_result.object_etag, s3._etag_for_key(key))

    def test_force_replay_bypasses_processed_key_ledger(self) -> None:
        redis = InMemoryRedis()
        client = _FakeClickHouseBatchClient()
        key = "ai-defense/audit/2026/04/06/force_replay_audit.jsonl"
        s3 = _FakeS3Client(
            objects={
                key: (
                    b'{"ts_ms":1710000000400,"session_id":"sess-force","event_type":"EVALUATE","action":"BLOCK","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{}}\n'
                ),
            }
        )
        worker = ETLWorker(
            config=ETLWorkerConfig(
                s3=S3ArchiveConfig(bucket="audit-bucket", prefix="ai-defense/audit/"),
                postgres=PostgresStorageConfig(url=None),
                clickhouse=ClickHouseStorageConfig(
                    url="clickhouse://localhost:8123/default",
                    audit_table="defense_audit_events_smoke",
                ),
            ),
            s3_client=s3,
            clickhouse_writer=ClickHouseAuditEventWriterRepository(
                client=client,
                config=ClickHouseWriteConfig(
                    url="clickhouse://localhost:8123/default",
                    table_name="defense_audit_events_smoke",
                    batch_size=1000,
                    timeout_ms=5000,
                ),
            ),
            processed_key_redis=redis,
        )

        first_result = worker.replay_key(key)
        forced_result = worker.replay_key(key, force=True)

        self.assertFalse(first_result.skipped_by_processed_ledger)
        self.assertFalse(forced_result.skipped_by_processed_ledger)
        self.assertEqual(forced_result.accepted_row_count, 1)
        self.assertEqual(len(client.calls), 2)

    def test_failed_ingest_does_not_mark_processed_key_ledger(self) -> None:
        redis = InMemoryRedis()
        key = "ai-defense/audit/2026/04/06/retry_after_failure.jsonl"
        s3 = _FakeS3Client(
            objects={
                key: (
                    b'{"ts_ms":1710000000500,"session_id":"sess-retry","event_type":"EVALUATE","action":"THROTTLE","reason_code":"RULE_HIT","policy_version":"policy-v1","raw_payload":{}}\n'
                ),
            }
        )
        failing_worker = ETLWorker(
            config=ETLWorkerConfig(
                s3=S3ArchiveConfig(bucket="audit-bucket", prefix="ai-defense/audit/"),
                postgres=PostgresStorageConfig(url=None),
                clickhouse=ClickHouseStorageConfig(
                    url="clickhouse://localhost:8123/default",
                    audit_table="defense_audit_events_smoke",
                    write_retry_max_attempts=1,
                ),
            ),
            s3_client=s3,
            clickhouse_writer=ClickHouseAuditEventWriterRepository(
                client=_FakeClickHouseBatchClient(failures_before_success=1),
                config=ClickHouseWriteConfig(
                    url="clickhouse://localhost:8123/default",
                    table_name="defense_audit_events_smoke",
                    batch_size=1000,
                    timeout_ms=5000,
                ),
            ),
            processed_key_redis=redis,
        )
        recovered_client = _FakeClickHouseBatchClient()
        recovered_worker = ETLWorker(
            config=ETLWorkerConfig(
                s3=S3ArchiveConfig(bucket="audit-bucket", prefix="ai-defense/audit/"),
                postgres=PostgresStorageConfig(url=None),
                clickhouse=ClickHouseStorageConfig(
                    url="clickhouse://localhost:8123/default",
                    audit_table="defense_audit_events_smoke",
                    write_retry_max_attempts=1,
                ),
            ),
            s3_client=s3,
            clickhouse_writer=ClickHouseAuditEventWriterRepository(
                client=recovered_client,
                config=ClickHouseWriteConfig(
                    url="clickhouse://localhost:8123/default",
                    table_name="defense_audit_events_smoke",
                    batch_size=1000,
                    timeout_ms=5000,
                ),
            ),
            processed_key_redis=redis,
        )

        with self.assertRaises(ETLIngestError):
            failing_worker.run_once()

        recovered_total = recovered_worker.run_once()

        self.assertEqual(recovered_total, 1)
        self.assertEqual(len(recovered_client.calls), 1)

    def test_clickhouse_raw_fact_write_smoke_uses_env_config_and_writer_surface(self) -> None:
        client = _FakeClickHouseBatchClient()
        with patch.dict(
            os.environ,
            {
                "TM_CLICKHOUSE_URL": "clickhouse://localhost:8123",
                "TM_CLICKHOUSE_AUDIT_TABLE": "defense_audit_events_smoke",
                "TM_CLICKHOUSE_INGEST_BATCH_SIZE": "128",
                "TM_CLICKHOUSE_INGEST_TIMEOUT_MS": "4000",
            },
            clear=True,
        ):
            config = build_clickhouse_write_config_from_env()

        repository = ClickHouseAuditEventWriterRepository(client=client, config=config)
        result = repository.write_batch_request_with_retry(
            ClickHouseBatchWriteRequest(
                rows=(
                    ClickHouseAuditEventInsertRow(
                        ts_ms=1000,
                        session_id="sess-1",
                        event_type="EVALUATE",
                        trace_id="trace-1",
                        flow_state="F4M",
                        risk_tier="T2",
                        action="THROTTLE",
                        reason_code="RULE_HIT",
                        policy_version="policy-v1",
                        raw_payload_json='{"request_id":"req-1"}',
                    ),
                )
            ),
            retry_policy=ClickHouseBatchWriteRetryPolicy(max_attempts=1, backoff_ms=0),
        )

        self.assertEqual(result.table_name, "defense_audit_events_smoke")
        self.assertEqual(result.accepted_row_count, 1)
        self.assertEqual(client.calls[0][0], repository.insert_sql)
        self.assertEqual(client.calls[0][1][0]["policy_version"], "policy-v1")

    def test_control_plane_to_projection_to_runtime_loader_smoke(self) -> None:
        redis = InMemoryRedis()
        projection_repository = RedisRuntimePolicyProjectionRepository(redis)
        version_repository = _FakePolicyVersionRepository(
            {
                "policy-v1": _policy_record("policy-v1"),
                "policy-v2": _policy_record("policy-v2"),
            }
        )
        rollout_repository = _FakePolicyRolloutStateRepository(_rollout_state_record())

        projection_result = project_rollout_state_change(
            rollout_id="rollout-smoke-1",
            version_repository=version_repository,
            rollout_state_repository=rollout_repository,
            projection_repository=projection_repository,
        )
        store = RedisPolicyStore(redis)
        loader = PolicyLoader(store=store, rollout_salt="smoke-salt", cache_seconds=0)
        rollout_state = store.get_primary_rollout_state()
        self.assertIsNotNone(rollout_state)
        session_id = _find_candidate_session_id(rollout_state or {}, salt="smoke-salt")
        loaded = loader.load(session_id)

        self.assertEqual(projection_result.projected_policy_versions, ("policy-v1", "policy-v2"))
        self.assertEqual(loaded.policy_version, "policy-v2")
        self.assertIn(POLICY_ROLLOUT_STATE_KEY, redis._data)
        self.assertIn(f"{POLICY_VERSION_KEY_PREFIX}policy-v2", redis._data)

    def test_strict_authority_smoke_runs_pg_write_to_projection_to_runtime_read_only(self) -> None:
        redis = InMemoryRedis()
        service = PostgresStrictPolicyAuthorityService(
            version_repository=_FakePolicyVersionRepository(
                {
                    "policy-v1": _policy_record("policy-v1"),
                    "policy-v2": _policy_record("policy-v2"),
                }
            ),
            rollout_state_repository=_FakePolicyRolloutStateRepository(None),
            rollout_event_repository=_FakePolicyRolloutEventRepository(),
            optimization_run_repository=_FakePolicyOptimizationRunRepository(),
            projection_repository=RedisRuntimePolicyProjectionRepository(redis),
        )

        service.save_rollout_state(_rollout_state_record())
        strict_loader = PolicyLoader(
            store=RedisPolicyStore(redis),
            rollout_salt="smoke-salt",
            cache_seconds=0,
            strict_authority=True,
            projection_max_staleness_ms=None,
        )
        session_id = _find_candidate_session_id(
            {
                "stage": "CANARY",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "ratio": 0.5,
                "updated_at_ms": 1710000005000,
            },
            salt="smoke-salt",
        )

        loaded = strict_loader.load(session_id)

        self.assertEqual(loaded.policy_version, "policy-v2")

    def test_projection_reconcile_smoke_restores_runtime_keys_after_eviction(self) -> None:
        redis = InMemoryRedis()
        projection_repository = RedisRuntimePolicyProjectionRepository(redis)
        version_repository = _FakePolicyVersionRepository(
            {
                "policy-v1": _policy_record("policy-v1"),
                "policy-v2": _policy_record("policy-v2"),
            }
        )
        rollout_repository = _FakePolicyRolloutStateRepository(_rollout_state_record())

        project_rollout_state_change(
            rollout_id="rollout-smoke-1",
            version_repository=version_repository,
            rollout_state_repository=rollout_repository,
            projection_repository=projection_repository,
        )
        redis.delete(POLICY_ROLLOUT_STATE_KEY, f"{POLICY_VERSION_KEY_PREFIX}policy-v2")
        store = RedisPolicyStore(redis)
        loader = PolicyLoader(store=store, rollout_salt="smoke-salt", cache_seconds=0)
        baseline = loader.load("smoke-session-baseline")

        reconcile_policy_runtime_projection(
            rollout_id="rollout-smoke-1",
            version_repository=version_repository,
            rollout_state_repository=rollout_repository,
            projection_repository=projection_repository,
        )
        rollout_state = store.get_primary_rollout_state()
        session_id = _find_candidate_session_id(rollout_state or {}, salt="smoke-salt")
        recovered = loader.load(session_id)

        self.assertEqual(baseline.policy_version, PolicySnapshot().policy_version)
        self.assertEqual(recovered.policy_version, "policy-v2")

    def test_session_rollup_candidate_read_bundle_smoke(self) -> None:
        client = _FakeClickHouseSelectClient()
        session_repository = build_clickhouse_session_rollup_reader_repository(
            client,
            table_name="session_rollups_smoke",
        )
        match_repository = build_clickhouse_match_rollup_reader_repository(
            client,
            table_name="match_rollups_smoke",
        )
        candidate_repository = build_clickhouse_post_review_candidate_reader_repository(
            client,
            view_name="candidate_view_smoke",
        )

        match_rows = match_repository.read_match_rollups(
            ClickHouseMatchRollupQuery(
                window_start_ms=100,
                window_end_ms=200,
                match_ids=("687",),
                limit=3,
            )
        )
        bundle = load_backoffice_clickhouse_read_model_input(
            window_start_ms=100,
            window_end_ms=200,
            session_rollup_repository=session_repository,
            candidate_repository=candidate_repository,
            limit=5,
        )

        self.assertEqual(tuple(row.session_id for row in bundle.session_rollups), ("sess-rollup",))
        self.assertEqual(tuple(row.match_id for row in match_rows), ("687",))
        self.assertEqual(tuple(row.session_id for row in bundle.candidate_rows), ("sess-candidate",))
        self.assertIn("FROM match_rollups_smoke", client.calls[0][0])
        self.assertIn("FROM session_rollups_smoke", client.calls[1][0])
        self.assertIn("FROM candidate_view_smoke", client.calls[2][0])

    def test_config_bootstrap_smoke_uses_ci_memory_redis_and_env_loader(self) -> None:
        tmp_dir = Path("/tmp/tm-task17-smoke")
        policy_store_path = tmp_dir / "policy_store.json"
        with patch.dict(
            os.environ,
            {
                "CI": "true",
                "TM_POLICY_STORE_PATH": str(policy_store_path),
                "TM_POLICY_CACHE_SECONDS": "9",
                "TM_ROLLOUT_SALT": "env-smoke-salt",
            },
            clear=True,
        ):
            redis, backend = build_runtime_redis_from_env()
            self.assertEqual(backend, "memory")
            store = RedisPolicyStore(redis)
            baseline_snapshot = PolicySnapshot()
            store.save_policy_version(
                baseline_snapshot.policy_version,
                snapshot_to_document(baseline_snapshot),
            )
            store.set_rollout_state(
                {
                    "stage": "FULL",
                    "base_policy_version": baseline_snapshot.policy_version,
                    "candidate_policy_version": None,
                    "ratio": 0.0,
                    "updated_at_ms": 1710000009999,
                }
            )
            loader = PolicyLoader.from_env(store=store)
            loaded = loader.load("sess-bootstrap")

        self.assertIsInstance(redis, InMemoryRedis)
        self.assertEqual(loader._cache_seconds, 9)
        self.assertEqual(loader._salt, "env-smoke-salt")
        self.assertEqual(loaded.policy_version, PolicySnapshot().policy_version)


if __name__ == "__main__":
    unittest.main()
