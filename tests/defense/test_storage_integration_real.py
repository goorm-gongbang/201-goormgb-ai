from __future__ import annotations

import json
import os
import time
import unittest
import base64
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from traffic_master_ai.defense.api.etl_worker import ETLWorker
from traffic_master_ai.defense.backoffice_copilot.storage.clickhouse_connection import (
    ClickHouseReadModelConfig,
    build_clickhouse_select_client,
    get_clickhouse_url_from_env,
)
from traffic_master_ai.defense.backoffice_copilot.storage.clickhouse_read_models import (
    ClickHouseMatchRollupQuery,
    ClickHousePostReviewCandidateQuery,
    ClickHouseSessionRollupQuery,
)
from traffic_master_ai.defense.backoffice_copilot.storage.clickhouse_read_repository import (
    ClickHouseMatchRollupReaderRepository,
    ClickHousePostReviewCandidateReaderRepository,
    ClickHouseSessionRollupReaderRepository,
)
from traffic_master_ai.defense.backoffice_copilot.storage.connection import (
    build_postgres_engine_from_env,
)
from traffic_master_ai.defense.backoffice_copilot.storage.policy_control_plane_models import (
    PolicyOptimizationRunRecord,
    PolicyRolloutEventRecord,
    PolicyRolloutStateRecord,
    PolicyVersionRecord,
)
from traffic_master_ai.defense.backoffice_copilot.storage.policy_control_plane_repository import (
    PostgresPolicyOptimizationRunRepository,
    PostgresPolicyRolloutEventRepository,
    PostgresPolicyRolloutStateRepository,
    PostgresPolicyVersionRepository,
)
from traffic_master_ai.defense.backoffice_copilot.storage.policy_projection_repository import (
    POLICY_ROLLOUT_STATE_KEY,
    POLICY_VERSION_INDEX_KEY,
    POLICY_VERSION_KEY_PREFIX,
    PostgresStrictPolicyAuthorityService,
)
from traffic_master_ai.defense.d0_mvp.policy import PolicyLoader, PolicySnapshot, snapshot_to_document
from traffic_master_ai.defense.d0_mvp.state.redis_client import build_runtime_redis_from_env
from traffic_master_ai.defense.storage_env import (
    load_etl_worker_config_from_env,
    validate_clickhouse_ingest_env_for_prod,
    validate_control_plane_projection_env_for_prod,
    validate_runtime_policy_env_for_prod,
)


_ROOT = Path(__file__).resolve().parents[2]
_PG_SCHEMA_SQL = _ROOT / "src/traffic_master_ai/defense/backoffice_copilot/storage/sql/002_postgresql_policy_control_plane_tables.sql"
_CH_RAW_SQL = _ROOT / "src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql"
_CH_READ_MODEL_SQL = _ROOT / "src/traffic_master_ai/defense/backoffice_copilot/storage/sql/004_clickhouse_read_models.sql"
_REAL_SMOKE_ENV = "TM_REAL_STORAGE_SMOKE"


class _FakeStreamingBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _FakeS3Client:
    def __init__(self, objects: dict[str, str]) -> None:
        self._objects = dict(objects)

    def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
        prefix = str(kwargs.get("Prefix", ""))
        keys = [
            {"Key": key, "ETag": self._etag_for_key(key)}
            for key in sorted(self._objects)
            if key.startswith(prefix)
        ]
        return {"Contents": keys, "IsTruncated": False}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        del Bucket
        return {"ETag": self._etag_for_key(Key)}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        del Bucket
        payload = self._objects[Key].encode("utf-8")
        return {"Body": _FakeStreamingBody(payload)}

    def _etag_for_key(self, key: str) -> str:
        payload = self._objects[key].encode("utf-8")
        return f'"{hashlib.md5(payload).hexdigest()}"'


@unittest.skipUnless(
    os.getenv(_REAL_SMOKE_ENV) == "1",
    "Set TM_REAL_STORAGE_SMOKE=1 with running PostgreSQL/Redis/ClickHouse infra to execute.",
)
class RealStorageIntegrationSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        validate_runtime_policy_env_for_prod()
        validate_control_plane_projection_env_for_prod()
        validate_clickhouse_ingest_env_for_prod()

        cls._wait_for_postgres()
        cls._wait_for_redis()
        cls._wait_for_clickhouse()

        cls.pg_engine = build_postgres_engine_from_env()
        cls.redis_client, _ = build_runtime_redis_from_env()
        cls.clickhouse_client = build_clickhouse_select_client(
            ClickHouseReadModelConfig(url=get_clickhouse_url_from_env())
        )

        cls._apply_postgres_sql(_PG_SCHEMA_SQL)
        cls._apply_clickhouse_sql(_CH_RAW_SQL)
        cls._apply_clickhouse_sql(_CH_READ_MODEL_SQL)
        cls._reset_postgres_state()
        cls._reset_redis_state()
        cls._reset_clickhouse_state()

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls._reset_postgres_state()
        except Exception:
            pass
        try:
            cls._reset_redis_state()
        except Exception:
            pass
        try:
            cls._reset_clickhouse_state()
        except Exception:
            pass
        if hasattr(cls, "pg_engine"):
            cls.pg_engine.dispose()

    def test_control_plane_projection_runtime_real_smoke(self) -> None:
        version_repository = PostgresPolicyVersionRepository(self.pg_engine)
        rollout_state_repository = PostgresPolicyRolloutStateRepository(self.pg_engine)
        rollout_event_repository = PostgresPolicyRolloutEventRepository(self.pg_engine)
        optimization_run_repository = PostgresPolicyOptimizationRunRepository(self.pg_engine)
        authority = PostgresStrictPolicyAuthorityService.from_env()

        created_at = datetime.now(timezone.utc)
        now_ms = int(created_at.timestamp() * 1000)
        policy_version = "policy-real-v1"
        rollout_id = "rollout-real-v1"
        run_id = "optimization-real-v1"
        event_id = "event-real-v1"

        version_record = PolicyVersionRecord(
            policy_version=policy_version,
            schema_version="policy.v1",
            status="ACTIVE",
            source_type="integration_smoke",
            document_json=snapshot_to_document(PolicySnapshot(policy_version=policy_version)),
            created_at=created_at,
            activated_at=created_at,
        )
        authority.save_policy_version(version_record, project_to_runtime=True)

        rollout_record = PolicyRolloutStateRecord(
            rollout_id=rollout_id,
            stage="FULL",
            base_policy_version=policy_version,
            ratio=Decimal("1.00000"),
            evaluation_window_seconds=300,
            canary_duration_seconds=300,
            stage_started_at_ms=now_ms,
            updated_at_ms=now_ms,
            current_status="ACTIVE",
        )
        projection_result = authority.save_rollout_state(rollout_record)

        event_record = PolicyRolloutEventRecord(
            event_id=event_id,
            rollout_id=rollout_id,
            event_type="ROLLOUT_PROMOTED",
            base_policy_version=policy_version,
            created_at=created_at,
            stage_before="CANARY",
            stage_after="FULL",
            ratio_before=Decimal("0.50000"),
            ratio_after=Decimal("1.00000"),
            reason_json={"source": "integration_smoke"},
        )
        authority.append_rollout_event(event_record)

        run_record = PolicyOptimizationRunRecord(
            run_id=run_id,
            base_policy_version=policy_version,
            trigger_type="manual_smoke",
            result_status="SUCCEEDED",
            created_at=created_at,
            proposed_policy_version=policy_version,
            metrics_snapshot_id="snapshot-real-v1",
            window_start_ms=1712400000000,
            window_end_ms=1712400300000,
            metrics_snapshot_json={"traffic": 1},
            proposal_json={"promote": True},
            finished_at=created_at,
        )
        authority.save_optimization_run(run_record)

        fetched_version = version_repository.get_version(policy_version)
        fetched_rollout = rollout_state_repository.get_state(rollout_id)
        fetched_events = rollout_event_repository.list_events(rollout_id)
        fetched_run = optimization_run_repository.get_run(run_id)

        self.assertIsNotNone(fetched_version)
        self.assertIsNotNone(fetched_rollout)
        self.assertEqual(fetched_events[0].event_id, event_id)
        self.assertIsNotNone(fetched_run)
        self.assertEqual(projection_result.projected_policy_versions, (policy_version,))

        projected_policy = self.redis_client.get(f"{POLICY_VERSION_KEY_PREFIX}{policy_version}")
        projected_rollout = self.redis_client.get(POLICY_ROLLOUT_STATE_KEY)
        projected_index = self.redis_client.get(POLICY_VERSION_INDEX_KEY)

        self.assertIsNotNone(projected_policy)
        self.assertIsNotNone(projected_rollout)
        self.assertIsNotNone(projected_index)

        loader = PolicyLoader.from_env()
        snapshot = loader.load("session-real-1")
        self.assertEqual(snapshot.policy_version, policy_version)

    def test_clickhouse_ingest_and_read_models_real_smoke(self) -> None:
        ts_ms = 1712400000000
        window_start_ms = ts_ms - (ts_ms % 600000)
        window_end_ms = window_start_ms + 600000
        # defense_match_rollups는 post-review 경로와 무관한 독립 5분 집계다.
        # defense_session_rollups / defense_post_review_candidates_v1(10분)과 window 크기가 다르므로
        # 별도 변수로 조회한다.
        match_window_start_ms = ts_ms - (ts_ms % 300000)
        match_window_end_ms = match_window_start_ms + 300000
        archive_key = "ai-defense/audit/2026/04/06/storage_real_smoke.jsonl"
        payload = {
            "ts_ms": ts_ms,
            "session_id": "sid:42",
            "event_type": "CHALLENGE_ISSUED",
            "trace_id": "trace-real-1",
            "challenge_id": "challenge-real-1",
            "flow_state": "S3",
            "risk_tier": "T2",
            "action": "BLOCK",
            "reason_code": "BOT_SIGNAL",
            "policy_version": "policy-real-v1",
            "raw_payload": {
                "path": "/matches/42/action",
            },
        }
        s3_client = _FakeS3Client(
            {
                archive_key: json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            }
        )

        worker = ETLWorker(
            config=load_etl_worker_config_from_env(),
            s3_client=s3_client,
        )
        replay_result = worker.replay_key(archive_key)
        self.assertEqual(replay_result.accepted_row_count, 1)
        self.assertEqual(replay_result.duplicate_row_count, 0)

        session_repo = ClickHouseSessionRollupReaderRepository(self.clickhouse_client)
        candidate_repo = ClickHousePostReviewCandidateReaderRepository(self.clickhouse_client)
        match_repo = ClickHouseMatchRollupReaderRepository(self.clickhouse_client)

        session_rows = session_repo.read_rollups(
            ClickHouseSessionRollupQuery(
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
            )
        )
        candidate_rows = candidate_repo.read_candidates(
            ClickHousePostReviewCandidateQuery(
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
            )
        )
        match_rows = match_repo.read_match_rollups(
            ClickHouseMatchRollupQuery(
                window_start_ms=match_window_start_ms,
                window_end_ms=match_window_end_ms,
            )
        )

        self.assertEqual(len(session_rows), 1)
        self.assertEqual(session_rows[0].session_id, "sid:42")
        self.assertEqual(session_rows[0].block_action_count, 1)
        self.assertEqual(len(candidate_rows), 1)
        self.assertEqual(candidate_rows[0].candidate_reason, "block_action_detected")
        self.assertEqual(len(match_rows), 1)
        self.assertEqual(match_rows[0].match_id, "42")

    @classmethod
    def _wait_for_postgres(cls) -> None:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                engine = build_postgres_engine_from_env()
                with engine.connect() as conn:
                    conn.exec_driver_sql("SELECT 1")
                engine.dispose()
                return
            except Exception:
                time.sleep(1)
        raise RuntimeError("PostgreSQL real smoke backend did not become ready in time.")

    @classmethod
    def _wait_for_redis(cls) -> None:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                redis_client, _ = build_runtime_redis_from_env()
                redis_client.set("tm:storage-smoke:ping", "1", ex=5)
                if redis_client.get("tm:storage-smoke:ping") == "1":
                    redis_client.delete("tm:storage-smoke:ping")
                    return
            except Exception:
                time.sleep(1)
        raise RuntimeError("Redis real smoke backend did not become ready in time.")

    @classmethod
    def _wait_for_clickhouse(cls) -> None:
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                rows = cls._clickhouse_query_json("SELECT 1 AS ok FORMAT JSON")
                if rows and int(rows[0]["ok"]) == 1:
                    return
            except Exception:
                time.sleep(1)
        raise RuntimeError("ClickHouse real smoke backend did not become ready in time.")

    @classmethod
    def _apply_postgres_sql(cls, path: Path) -> None:
        statements = _split_sql_statements(path.read_text())
        with cls.pg_engine.begin() as conn:
            for statement in statements:
                conn.exec_driver_sql(statement)

    @classmethod
    def _reset_postgres_state(cls) -> None:
        with cls.pg_engine.begin() as conn:
            conn.exec_driver_sql(
                "TRUNCATE TABLE "
                "policy_rollout_events, policy_optimization_runs, policy_rollout_state, policy_versions"
            )

    @classmethod
    def _apply_clickhouse_sql(cls, path: Path) -> None:
        for statement in _split_sql_statements(path.read_text()):
            cls._clickhouse_execute(statement)

    @classmethod
    def _reset_clickhouse_state(cls) -> None:
        cls._clickhouse_execute("TRUNCATE TABLE defense_audit_events")

    @classmethod
    def _reset_redis_state(cls) -> None:
        cls.redis_client.delete(
            POLICY_ROLLOUT_STATE_KEY,
            POLICY_VERSION_INDEX_KEY,
            f"{POLICY_VERSION_KEY_PREFIX}policy-real-v1",
        )

    @classmethod
    def _clickhouse_execute(cls, query: str) -> bytes:
        raw_url = get_clickhouse_url_from_env() or ""
        endpoint = _build_clickhouse_http_query_url(raw_url, query)
        request = Request(
            url=endpoint,
            data=b"",
            method="POST",
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        auth_header = _build_clickhouse_auth_header(raw_url)
        if auth_header is not None:
            request.add_header("Authorization", auth_header)
        with urlopen(request, timeout=10.0) as response:
            body = response.read()
            if response.status >= 400:
                raise RuntimeError(body.decode("utf-8", errors="replace"))
            return body

    @classmethod
    def _clickhouse_query_json(cls, query: str) -> list[dict[str, object]]:
        body = cls._clickhouse_execute(query)
        parsed = json.loads(body.decode("utf-8"))
        data = parsed.get("data")
        if not isinstance(data, list):
            raise RuntimeError("ClickHouse JSON response did not contain data array.")
        return [row for row in data if isinstance(row, dict)]


def _split_sql_statements(sql_text: str) -> list[str]:
    statements = []
    current: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(current).strip()
            if statement.endswith(";"):
                statement = statement[:-1].strip()
            if statement:
                statements.append(statement)
            current = []
    trailing = "\n".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def _build_clickhouse_http_query_url(raw_url: str, query: str) -> str:
    parsed = urlsplit(raw_url)
    scheme = parsed.scheme.lower()
    if scheme == "clickhouse":
        scheme = "http"
    if scheme not in {"http", "https"}:
        raise ValueError("TM_CLICKHOUSE_URL must use clickhouse://, http://, or https:// scheme.")
    if not parsed.hostname:
        raise ValueError("TM_CLICKHOUSE_URL must include a hostname.")
    netloc = parsed.hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    database = None
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if path_segments:
        database = path_segments[0]
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if database is None:
        database = query_items.get("database")
    if database:
        query_items["database"] = database
    query_items["query"] = query
    return urlunsplit((scheme, netloc, "/", urlencode(query_items), ""))


def _build_clickhouse_auth_header(raw_url: str) -> str | None:
    parsed = urlsplit(raw_url)
    if parsed.username is None:
        return None
    userpass = f"{parsed.username}:{parsed.password or ''}".encode("utf-8")
    return "Basic " + base64.b64encode(userpass).decode("ascii")
