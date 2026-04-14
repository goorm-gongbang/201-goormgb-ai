from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from traffic_master_ai.defense.backoffice_copilot.storage.migration import (
    apply_postgres_storage_migrations,
    run_storage_migration,
)

_BUILD_ENGINE = (
    "traffic_master_ai.defense.backoffice_copilot.storage.migration."
    "build_postgres_engine_from_env"
)


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.closed = False

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def close(self) -> None:
        self.closed = True


class _FakeRawConnection:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class _FakeEngine:
    def __init__(self) -> None:
        self.raw_connection_obj = _FakeRawConnection()
        self.disposed = False

    def raw_connection(self) -> _FakeRawConnection:
        return self.raw_connection_obj

    def dispose(self) -> None:
        self.disposed = True


class _FailingCursor(_FakeCursor):
    def execute(self, sql: str) -> None:
        super().execute(sql)
        if "CREATE TABLE IF NOT EXISTS policy_versions" in sql:
            raise RuntimeError("boom")


class _FailingRawConnection(_FakeRawConnection):
    def __init__(self) -> None:
        super().__init__()
        self.cursor_obj = _FailingCursor()


class _FailingEngine(_FakeEngine):
    def __init__(self) -> None:
        super().__init__()
        self.raw_connection_obj = _FailingRawConnection()


class StorageMigrationCommandTests(unittest.TestCase):
    def test_storage_migration_applies_postgres_ddl_in_order(self) -> None:
        engine = _FakeEngine()

        applied = apply_postgres_storage_migrations(engine)

        executed_sql = "\n".join(engine.raw_connection_obj.cursor_obj.executed)
        self.assertEqual(
            applied,
            (
                "001_post_review_tables.sql",
                "002_postgresql_policy_control_plane_tables.sql",
            ),
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS post_review_runs", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS post_review_session_results", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_versions", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_rollout_state", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_rollout_events", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_optimization_runs", executed_sql)
        self.assertTrue(engine.raw_connection_obj.committed)
        self.assertFalse(engine.raw_connection_obj.rolled_back)
        self.assertFalse(engine.disposed)

    def test_storage_migration_command_fails_fast_without_pg_url(self) -> None:
        stdout = io.StringIO()

        with patch.dict(os.environ, {}, clear=True):
            with patch("sys.argv", ["tm-ai-storage-migrate"]):
                with redirect_stdout(stdout):
                    with self.assertRaises(SystemExit) as exc_info:
                        run_storage_migration()

        self.assertEqual(exc_info.exception.code, 1)
        summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["error_count"], 1)
        self.assertIn("TM_PG_URL", summary["error"])

    def test_storage_migration_dry_run_prints_postgres_ddl_plan_without_pg_url(self) -> None:
        stdout = io.StringIO()

        with patch.dict(os.environ, {}, clear=True):
            with patch("sys.argv", ["tm-ai-storage-migrate", "--dry-run"]):
                with redirect_stdout(stdout):
                    run_storage_migration()

        self.assertIn("planned 001_post_review_tables.sql", stdout.getvalue())
        self.assertIn("planned 002_postgresql_policy_control_plane_tables.sql", stdout.getvalue())
        summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["command"], "tm-ai-storage-migrate")
        self.assertEqual(summary["mode"], "dry_run")
        self.assertEqual(summary["status"], "dry_run")
        self.assertEqual(summary["output_count"], 2)

    def test_storage_migration_fails_with_clear_error_when_sql_file_is_missing(self) -> None:
        engine = _FakeEngine()

        with self.assertRaisesRegex(RuntimeError, "missing.sql"):
            apply_postgres_storage_migrations(engine, migration_files=("missing.sql",))

        self.assertTrue(engine.raw_connection_obj.rolled_back)
        self.assertFalse(engine.raw_connection_obj.committed)

    def test_storage_migration_logs_failed_sql_file(self) -> None:
        engine = _FailingEngine()

        with self.assertLogs(
            "traffic_master_ai.defense.backoffice_copilot.storage.migration",
            level="ERROR",
        ) as logs:
            with self.assertRaisesRegex(RuntimeError, "boom"):
                apply_postgres_storage_migrations(engine)

        self.assertIn("002_postgresql_policy_control_plane_tables.sql", "\n".join(logs.output))
        self.assertTrue(engine.raw_connection_obj.rolled_back)
        self.assertFalse(engine.raw_connection_obj.committed)

    def test_storage_migration_command_builds_engine_from_env_and_disposes_it(self) -> None:
        engine = _FakeEngine()

        with patch.dict(
            os.environ,
            {"TM_PG_URL": "postgresql+psycopg://user:pass@host/db"},
            clear=True,
        ):
            with patch("sys.argv", ["tm-ai-storage-migrate"]):
                with patch(
                    _BUILD_ENGINE,
                    return_value=engine,
                ):
                    run_storage_migration()

        self.assertTrue(engine.raw_connection_obj.committed)
        self.assertTrue(engine.disposed)
