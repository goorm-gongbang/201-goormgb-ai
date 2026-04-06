from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from traffic_master_ai.defense.api.etl_worker import run_etl
from traffic_master_ai.defense.backoffice_copilot.storage import (
    build_clickhouse_read_model_config_from_env,
    build_clickhouse_write_config_from_env,
    get_postgres_url_from_env,
)
from traffic_master_ai.defense.d0_mvp.observability.audit_logger import AuditLogger
from traffic_master_ai.defense.d0_mvp.observability.warehouse import AuditWarehouse
from traffic_master_ai.defense.d0_mvp.policy.loader import FilePolicyStore, PolicyLoader, RedisPolicyStore
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis, build_runtime_redis_from_env
from traffic_master_ai.defense.storage_env import (
    DEFAULT_CLICKHOUSE_AUDIT_TABLE,
    DEFAULT_DEFENSE_AUDIT_LOG_PATH,
    DEFAULT_POLICY_CACHE_SECONDS,
    DEFAULT_POLICY_PROJECTION_MAX_STALENESS_MS,
    DEFAULT_POLICY_STORE_PATH,
    DEFAULT_S3_ARCHIVE_INTERVAL_SECONDS,
    DEFAULT_S3_PREFIX,
    load_clickhouse_storage_config_from_env,
    load_projection_sync_config_from_env,
    load_audit_log_config_from_env,
    load_runtime_policy_config_from_env,
    load_s3_archive_config_from_env,
    validate_clickhouse_ingest_env_for_prod,
    validate_control_plane_projection_env_for_prod,
    validate_runtime_policy_env_for_prod,
    StorageOperationalConfigError,
)


class StorageEnvConfigTests(unittest.TestCase):
    def test_env_loaders_keep_documented_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            s3_config = load_s3_archive_config_from_env()
            runtime_policy_config = load_runtime_policy_config_from_env()
            clickhouse_config = load_clickhouse_storage_config_from_env()

        self.assertIsNone(s3_config.bucket)
        self.assertEqual(s3_config.prefix, DEFAULT_S3_PREFIX)
        self.assertEqual(s3_config.archive_interval_seconds, DEFAULT_S3_ARCHIVE_INTERVAL_SECONDS)
        self.assertEqual(runtime_policy_config.store_path, DEFAULT_POLICY_STORE_PATH)
        self.assertEqual(runtime_policy_config.cache_seconds, DEFAULT_POLICY_CACHE_SECONDS)
        self.assertEqual(runtime_policy_config.rollout_salt, "")
        self.assertTrue(runtime_policy_config.strict_authority)
        self.assertFalse(runtime_policy_config.allow_local_fallback)
        self.assertEqual(
            runtime_policy_config.projection_max_staleness_ms,
            DEFAULT_POLICY_PROJECTION_MAX_STALENESS_MS,
        )
        self.assertEqual(clickhouse_config.audit_table, DEFAULT_CLICKHOUSE_AUDIT_TABLE)
        self.assertIsNone(clickhouse_config.url)

    def test_postgres_and_clickhouse_config_surfaces_use_env_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TM_PG_URL": "postgresql://user:pass@localhost:5432/tm",
                "TM_CLICKHOUSE_URL": "clickhouse://localhost:8123",
                "TM_CLICKHOUSE_AUDIT_TABLE": "audit_stage",
                "TM_CLICKHOUSE_INGEST_BATCH_SIZE": "512",
                "TM_CLICKHOUSE_INGEST_TIMEOUT_MS": "9000",
            },
            clear=True,
        ):
            write_config = build_clickhouse_write_config_from_env()
            read_config = build_clickhouse_read_model_config_from_env()
            pg_url = get_postgres_url_from_env()

        self.assertEqual(pg_url, "postgresql://user:pass@localhost:5432/tm")
        self.assertEqual(write_config.url, "clickhouse://localhost:8123")
        self.assertEqual(write_config.table_name, "audit_stage")
        self.assertEqual(write_config.batch_size, 512)
        self.assertEqual(write_config.timeout_ms, 9000)
        self.assertEqual(read_config.url, "clickhouse://localhost:8123")
        self.assertEqual(read_config.timeout_ms, 9000)

    def test_missing_required_postgres_url_fails_fast(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                get_postgres_url_from_env()

    def test_runtime_redis_env_contract_fails_fast_outside_ci_and_allows_memory_in_ci(self) -> None:
        with patch.dict(os.environ, {"CI": "false"}, clear=True):
            with self.assertRaises(ValueError):
                build_runtime_redis_from_env()

        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            client, backend = build_runtime_redis_from_env()

        self.assertEqual(backend, "memory")
        self.assertIsInstance(client, InMemoryRedis)

        with patch.dict(
            os.environ,
            {"CI": "false", "TM_ALLOW_IN_MEMORY_REDIS": "true"},
            clear=True,
        ):
            client, backend = build_runtime_redis_from_env()

        self.assertEqual(backend, "memory")
        self.assertIsInstance(client, InMemoryRedis)

    def test_invalid_clickhouse_numeric_env_values_raise_value_error(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TM_CLICKHOUSE_INGEST_BATCH_SIZE": "bad-int",
            },
            clear=True,
        ):
            with self.assertRaises(ValueError):
                load_clickhouse_storage_config_from_env()

    def test_projection_retry_and_clickhouse_retry_env_surfaces_use_env_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TM_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS": "5",
                "TM_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS": "250",
                "TM_PROJECTION_RETRY_MAX_ATTEMPTS": "4",
                "TM_PROJECTION_RETRY_BACKOFF_MS": "80",
            },
            clear=True,
        ):
            clickhouse_config = load_clickhouse_storage_config_from_env()
            projection_config = load_projection_sync_config_from_env()

        self.assertEqual(clickhouse_config.write_retry_max_attempts, 5)
        self.assertEqual(clickhouse_config.write_retry_backoff_ms, 250)
        self.assertEqual(projection_config.retry_max_attempts, 4)
        self.assertEqual(projection_config.retry_backoff_ms, 80)

    def test_runtime_loader_and_local_observability_surfaces_read_env_paths(self) -> None:
        tmp_dir = Path("/tmp/tm-task14-config-test")
        audit_path = tmp_dir / "decision_audit.jsonl"
        warehouse_path = tmp_dir / "warehouse.jsonl"
        policy_store_path = tmp_dir / "policy_store.json"
        with patch.dict(
            os.environ,
            {
                "TM_DEFENSE_AUDIT_LOG_PATH": str(audit_path),
                "TM_WAREHOUSE_FILENAME": str(warehouse_path),
                "TM_POLICY_STORE_PATH": str(policy_store_path),
                "TM_POLICY_CACHE_SECONDS": "17",
                "TM_ROLLOUT_SALT": "salt-123",
                "TM_POLICY_ALLOW_LOCAL_FALLBACK": "true",
                "TM_ALLOW_IN_MEMORY_REDIS": "true",
            },
            clear=True,
        ):
            audit_log_config = load_audit_log_config_from_env()
            runtime_logger = AuditLogger.from_env()
            warehouse = AuditWarehouse.from_env()
            loader = PolicyLoader.from_env()

        self.assertEqual(audit_log_config.file_path, str(audit_path))
        self.assertEqual(runtime_logger.file_path, audit_path)
        self.assertEqual(warehouse.file_path, warehouse_path)
        self.assertEqual(loader._salt, "salt-123")
        self.assertEqual(loader._cache_seconds, 17)
        self.assertFalse(loader.strict_authority)
        fallback = getattr(loader.store, "_fallback", None)
        self.assertIsInstance(fallback, FilePolicyStore)
        self.assertEqual(fallback.file_path, policy_store_path)

    def test_runtime_loader_defaults_to_strict_redis_only_mode(self) -> None:
        store = RedisPolicyStore(InMemoryRedis())

        with patch.dict(
            os.environ,
            {
                "TM_POLICY_CACHE_SECONDS": "11",
            },
            clear=True,
        ):
            loader = PolicyLoader.from_env(store=store)

        self.assertTrue(loader.strict_authority)
        self.assertEqual(loader._cache_seconds, 11)
        self.assertIsNone(getattr(loader.store, "_fallback", None))

    def test_prod_storage_validators_fail_fast_on_missing_or_unsafe_env(self) -> None:
        with patch.dict(os.environ, {"TM_ENV": "prod"}, clear=True):
            with self.assertRaises(StorageOperationalConfigError):
                validate_runtime_policy_env_for_prod()
            with self.assertRaises(StorageOperationalConfigError):
                validate_control_plane_projection_env_for_prod()
            with self.assertRaises(StorageOperationalConfigError):
                validate_clickhouse_ingest_env_for_prod()

        with patch.dict(
            os.environ,
            {
                "TM_ENV": "prod",
                "TM_PG_URL": "postgresql://user:pass@localhost:5432/tm",
                "TM_REDIS_URL": "redis://localhost:6379/0",
                "TM_ROLLOUT_SALT": "strict-salt",
                "TM_S3_BUCKET": "audit-bucket",
                "TM_CLICKHOUSE_URL": "http://localhost:8123/default",
                "TM_POLICY_ALLOW_LOCAL_FALLBACK": "false",
                "TM_ALLOW_IN_MEMORY_REDIS": "false",
            },
            clear=True,
        ):
            validate_runtime_policy_env_for_prod()
            validate_control_plane_projection_env_for_prod()
            validate_clickhouse_ingest_env_for_prod()

    def test_etl_cli_fails_fast_when_clickhouse_env_is_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TM_S3_BUCKET": "audit-bucket",
            },
            clear=True,
        ):
            with self.assertRaises(SystemExit) as exc_info:
                run_etl()

        self.assertIn("TM_CLICKHOUSE_URL must be set", str(exc_info.exception))

    def test_etl_cli_runs_clickhouse_worker_when_env_is_configured(self) -> None:
        fake_worker = MagicMock()
        fake_worker.run_once.return_value = 7

        with patch.dict(
            os.environ,
            {
                "TM_S3_BUCKET": "audit-bucket",
                "TM_CLICKHOUSE_URL": "clickhouse://localhost:8123/default",
            },
            clear=True,
        ):
            buf = io.StringIO()
            with (
                patch("traffic_master_ai.defense.api.etl_worker.ETLWorker", return_value=fake_worker),
                redirect_stdout(buf),
            ):
                run_etl()

        output = buf.getvalue()
        self.assertIn("ClickHouse ETL completed. Accepted 7 rows.", output)


if __name__ == "__main__":
    unittest.main()
