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
                "005_post_review_runs_schema_drift.sql",
                "006_post_review_session_results_schema_drift.sql",
            ),
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS post_review_runs", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS post_review_session_results", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_versions", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_rollout_state", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_rollout_events", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_optimization_runs", executed_sql)
        # runs schema drift migration must be included
        self.assertIn("ADD COLUMN IF NOT EXISTS candidate_count", executed_sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS suspicious_count", executed_sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS summary_text_json", executed_sql)
        # session results schema drift migration must be included
        self.assertIn("ADD COLUMN IF NOT EXISTS evidence_summary", executed_sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS session_analysis_json", executed_sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS backend_delivery_status", executed_sql)
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
        self.assertIn("planned 005_post_review_runs_schema_drift.sql", stdout.getvalue())
        self.assertIn("planned 006_post_review_session_results_schema_drift.sql", stdout.getvalue())
        summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["command"], "tm-ai-storage-migrate")
        self.assertEqual(summary["mode"], "dry_run")
        self.assertEqual(summary["status"], "dry_run")
        self.assertEqual(summary["output_count"], 4)

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


class SchemaDriftMigrationTests(unittest.TestCase):
    """Verify that 005_post_review_runs_schema_drift.sql is correct and idempotent."""

    def _get_schema_drift_sql(self) -> str:
        """Read the schema drift migration file directly."""
        from pathlib import Path
        sql_path = (
            Path(__file__).resolve().parents[2]
            / "src/traffic_master_ai/defense/backoffice_copilot/storage/sql"
            / "005_post_review_runs_schema_drift.sql"
        )
        return sql_path.read_text(encoding="utf-8")

    def test_schema_drift_file_exists_and_is_registered(self) -> None:
        from traffic_master_ai.defense.backoffice_copilot.storage.migration import (
            _POSTGRES_MIGRATION_FILES,
        )
        self.assertIn("005_post_review_runs_schema_drift.sql", _POSTGRES_MIGRATION_FILES)
        # verify file is readable (would raise if absent)
        self.assertGreater(len(self._get_schema_drift_sql()), 0)

    def test_schema_drift_sql_contains_add_column_if_not_exists_for_all_missing_columns(self) -> None:
        sql = self._get_schema_drift_sql()
        # All three columns that triggered the production error must be covered
        self.assertIn("ADD COLUMN IF NOT EXISTS candidate_count", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS suspicious_count", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS summary_text_json", sql)

    def test_schema_drift_sql_contains_not_null_enforcement(self) -> None:
        sql = self._get_schema_drift_sql()
        self.assertIn("ALTER COLUMN candidate_count SET NOT NULL", sql)
        self.assertIn("ALTER COLUMN suspicious_count SET NOT NULL", sql)
        self.assertIn("ALTER COLUMN summary_text_json SET NOT NULL", sql)

    def test_schema_drift_sql_contains_null_backfill_before_not_null(self) -> None:
        sql = self._get_schema_drift_sql()
        # Backfill must appear before SET NOT NULL
        backfill_pos = sql.index("candidate_count IS NULL")
        not_null_pos = sql.index("ALTER COLUMN candidate_count SET NOT NULL")
        self.assertLess(backfill_pos, not_null_pos, "Backfill UPDATE must precede SET NOT NULL")

    def test_schema_drift_sql_contains_idempotent_constraint_guards(self) -> None:
        sql = self._get_schema_drift_sql()
        self.assertIn("post_review_runs_counts_check", sql)
        self.assertIn("post_review_runs_summary_text_json_check", sql)
        # constraints must be guarded by IF NOT EXISTS check
        self.assertIn("IF NOT EXISTS", sql)

    def test_schema_drift_applied_via_migration_runner(self) -> None:
        """Migration runner executes 005 SQL and includes it in the applied list."""
        engine = _FakeEngine()

        applied = apply_postgres_storage_migrations(engine)

        self.assertIn("005_post_review_runs_schema_drift.sql", applied)
        # 005 must come AFTER 001 and 002, and BEFORE 006
        applied_list = list(applied)
        self.assertLess(
            applied_list.index("001_post_review_tables.sql"),
            applied_list.index("005_post_review_runs_schema_drift.sql"),
        )
        self.assertLess(
            applied_list.index("002_postgresql_policy_control_plane_tables.sql"),
            applied_list.index("005_post_review_runs_schema_drift.sql"),
        )
        self.assertLess(
            applied_list.index("005_post_review_runs_schema_drift.sql"),
            applied_list.index("006_post_review_session_results_schema_drift.sql"),
        )

    def test_schema_drift_sql_rolled_back_on_failure(self) -> None:
        """A failure in 005 triggers rollback and does not commit."""
        class _FailOn005Cursor(_FakeCursor):
            def execute(self, sql: str) -> None:
                super().execute(sql)
                if "ADD COLUMN IF NOT EXISTS candidate_count" in sql:
                    raise RuntimeError("column error")

        class _FailOn005RawConnection(_FakeRawConnection):
            def __init__(self) -> None:
                super().__init__()
                self.cursor_obj = _FailOn005Cursor()

        class _FailOn005Engine(_FakeEngine):
            def __init__(self) -> None:
                super().__init__()
                self.raw_connection_obj = _FailOn005RawConnection()

        engine = _FailOn005Engine()

        with self.assertRaisesRegex(RuntimeError, "column error"):
            apply_postgres_storage_migrations(engine)

        self.assertTrue(engine.raw_connection_obj.rolled_back)
        self.assertFalse(engine.raw_connection_obj.committed)


class SessionResultsSchemaDriftMigrationTests(unittest.TestCase):
    """Verify that 006_post_review_session_results_schema_drift.sql is correct and idempotent."""

    def _get_schema_drift_sql(self) -> str:
        """Read the session results schema drift migration file directly."""
        from pathlib import Path
        sql_path = (
            Path(__file__).resolve().parents[2]
            / "src/traffic_master_ai/defense/backoffice_copilot/storage/sql"
            / "006_post_review_session_results_schema_drift.sql"
        )
        return sql_path.read_text(encoding="utf-8")

    def test_schema_drift_file_exists_and_is_registered(self) -> None:
        from traffic_master_ai.defense.backoffice_copilot.storage.migration import (
            _POSTGRES_MIGRATION_FILES,
        )
        self.assertIn("006_post_review_session_results_schema_drift.sql", _POSTGRES_MIGRATION_FILES)
        # verify file is readable (would raise if absent)
        self.assertGreater(len(self._get_schema_drift_sql()), 0)

    def test_schema_drift_sql_contains_add_column_if_not_exists_for_all_missing_columns(self) -> None:
        sql = self._get_schema_drift_sql()
        self.assertIn("ADD COLUMN IF NOT EXISTS evidence_summary", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS session_analysis_json", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS backend_delivery_status", sql)

    def test_schema_drift_sql_contains_not_null_enforcement(self) -> None:
        sql = self._get_schema_drift_sql()
        self.assertIn("ALTER COLUMN evidence_summary SET NOT NULL", sql)
        self.assertIn("ALTER COLUMN session_analysis_json SET NOT NULL", sql)
        self.assertIn("ALTER COLUMN backend_delivery_status SET NOT NULL", sql)

    def test_schema_drift_sql_uses_single_coalesce_update(self) -> None:
        sql = self._get_schema_drift_sql()
        # All three columns backfilled in the same UPDATE via COALESCE
        self.assertIn("COALESCE(evidence_summary", sql)
        self.assertIn("COALESCE(session_analysis_json", sql)
        self.assertIn("COALESCE(backend_delivery_status", sql)
        # Must have exactly one UPDATE statement
        self.assertEqual(sql.upper().count("\nUPDATE "), 1)

    def test_schema_drift_sql_contains_null_backfill_before_not_null(self) -> None:
        sql = self._get_schema_drift_sql()
        # Backfill must appear before SET NOT NULL
        backfill_pos = sql.index("COALESCE(evidence_summary")
        not_null_pos = sql.index("ALTER COLUMN evidence_summary SET NOT NULL")
        self.assertLess(backfill_pos, not_null_pos, "Backfill UPDATE must precede SET NOT NULL")

    def test_schema_drift_sql_contains_idempotent_constraint_guards(self) -> None:
        sql = self._get_schema_drift_sql()
        self.assertIn("post_review_session_results_review_result_check", sql)
        self.assertIn("post_review_session_results_backend_delivery_status_check", sql)
        self.assertIn("post_review_session_results_session_analysis_json_check", sql)
        self.assertIn("IF NOT EXISTS", sql)

    def test_schema_drift_applied_via_migration_runner(self) -> None:
        """Migration runner executes 006 SQL and includes it in the applied list."""
        engine = _FakeEngine()

        applied = apply_postgres_storage_migrations(engine)

        self.assertIn("006_post_review_session_results_schema_drift.sql", applied)
        applied_list = list(applied)
        # 006 must come AFTER 001, 002, and 005
        self.assertLess(
            applied_list.index("001_post_review_tables.sql"),
            applied_list.index("006_post_review_session_results_schema_drift.sql"),
        )
        self.assertLess(
            applied_list.index("002_postgresql_policy_control_plane_tables.sql"),
            applied_list.index("006_post_review_session_results_schema_drift.sql"),
        )
        self.assertLess(
            applied_list.index("005_post_review_runs_schema_drift.sql"),
            applied_list.index("006_post_review_session_results_schema_drift.sql"),
        )

    def test_schema_drift_sql_rolled_back_on_failure(self) -> None:
        """A failure in 006 triggers rollback and does not commit."""
        class _FailOn006Cursor(_FakeCursor):
            def execute(self, sql: str) -> None:
                super().execute(sql)
                if "ADD COLUMN IF NOT EXISTS evidence_summary" in sql:
                    raise RuntimeError("session column error")

        class _FailOn006RawConnection(_FakeRawConnection):
            def __init__(self) -> None:
                super().__init__()
                self.cursor_obj = _FailOn006Cursor()

        class _FailOn006Engine(_FakeEngine):
            def __init__(self) -> None:
                super().__init__()
                self.raw_connection_obj = _FailOn006RawConnection()

        engine = _FailOn006Engine()

        with self.assertRaisesRegex(RuntimeError, "session column error"):
            apply_postgres_storage_migrations(engine)

        self.assertTrue(engine.raw_connection_obj.rolled_back)
        self.assertFalse(engine.raw_connection_obj.committed)
