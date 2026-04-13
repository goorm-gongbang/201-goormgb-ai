from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from traffic_master_ai.defense.backoffice_copilot.storage.migration import (
    apply_postgres_storage_migrations,
    run_storage_migration,
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


class StorageMigrationCommandTests(unittest.TestCase):
    def test_storage_migration_applies_policy_control_plane_tables(self) -> None:
        engine = _FakeEngine()

        applied = apply_postgres_storage_migrations(engine)

        executed_sql = "\n".join(engine.raw_connection_obj.cursor_obj.executed)
        self.assertEqual(applied, ("002_postgresql_policy_control_plane_tables.sql",))
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_versions", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_rollout_state", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_rollout_events", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_optimization_runs", executed_sql)
        self.assertTrue(engine.raw_connection_obj.committed)
        self.assertFalse(engine.raw_connection_obj.rolled_back)
        self.assertFalse(engine.disposed)

    def test_storage_migration_command_fails_fast_without_pg_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                run_storage_migration()

    def test_storage_migration_command_builds_engine_from_env_and_disposes_it(self) -> None:
        engine = _FakeEngine()

        with patch.dict(
            os.environ,
            {"TM_PG_URL": "postgresql+psycopg://user:pass@host/db"},
            clear=True,
        ):
            with patch(
                "traffic_master_ai.defense.backoffice_copilot.storage.migration.build_postgres_engine_from_env",
                return_value=engine,
            ):
                run_storage_migration()

        self.assertTrue(engine.raw_connection_obj.committed)
        self.assertTrue(engine.disposed)
