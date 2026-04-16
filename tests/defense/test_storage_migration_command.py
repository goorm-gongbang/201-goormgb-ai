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
                "007_post_review_tables_rebuild.sql",
            ),
        )
        # 001: post-review tables
        self.assertIn("CREATE TABLE IF NOT EXISTS post_review_runs", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS post_review_session_results", executed_sql)
        # 002: policy control plane tables
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_versions", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_rollout_state", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_rollout_events", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS policy_optimization_runs", executed_sql)
        # 007: rebuild migration — key DDL landmarks present
        self.assertIn("information_schema.columns", executed_sql)  # old-schema detection query
        self.assertIn("DROP TABLE IF EXISTS post_review_session_results CASCADE", executed_sql)
        # obsolete 005/006 drift patches must NOT be in the applied list
        self.assertNotIn("005_post_review_runs_schema_drift.sql", applied)
        self.assertNotIn("006_post_review_session_results_schema_drift.sql", applied)
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
        self.assertIn("planned 007_post_review_tables_rebuild.sql", stdout.getvalue())
        # obsolete files must not appear in the plan
        self.assertNotIn("005_post_review_runs_schema_drift.sql", stdout.getvalue())
        self.assertNotIn("006_post_review_session_results_schema_drift.sql", stdout.getvalue())
        summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["command"], "tm-ai-storage-migrate")
        self.assertEqual(summary["mode"], "dry_run")
        self.assertEqual(summary["status"], "dry_run")
        self.assertEqual(summary["output_count"], 3)

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


class RebuildMigrationTests(unittest.TestCase):
    """Verify that 007_post_review_tables_rebuild.sql is correct and addresses
    both the old-schema detection path and the no-op path for correct schema."""

    def _get_rebuild_sql(self) -> str:
        from pathlib import Path
        sql_path = (
            Path(__file__).resolve().parents[2]
            / "src/traffic_master_ai/defense/backoffice_copilot/storage/sql"
            / "007_post_review_tables_rebuild.sql"
        )
        return sql_path.read_text(encoding="utf-8")

    def test_rebuild_file_exists_and_is_registered(self) -> None:
        from traffic_master_ai.defense.backoffice_copilot.storage.migration import (
            _POSTGRES_MIGRATION_FILES,
        )
        self.assertIn("007_post_review_tables_rebuild.sql", _POSTGRES_MIGRATION_FILES)
        self.assertGreater(len(self._get_rebuild_sql()), 0)

    def test_rebuild_file_is_third_in_sequence(self) -> None:
        from traffic_master_ai.defense.backoffice_copilot.storage.migration import (
            _POSTGRES_MIGRATION_FILES,
        )
        files = list(_POSTGRES_MIGRATION_FILES)
        self.assertEqual(files.index("001_post_review_tables.sql"), 0)
        self.assertEqual(files.index("002_postgresql_policy_control_plane_tables.sql"), 1)
        self.assertEqual(files.index("007_post_review_tables_rebuild.sql"), 2)

    def test_rebuild_sql_detects_old_schema_via_bigint_id_column(self) -> None:
        sql = self._get_rebuild_sql()
        # Must query information_schema for the old BIGSERIAL id column
        self.assertIn("information_schema.columns", sql)
        self.assertIn("column_name  = 'id'", sql)
        self.assertIn("data_type    = 'bigint'", sql)
        self.assertIn("table_name   = 'post_review_runs'", sql)

    def test_rebuild_sql_drops_session_results_before_runs(self) -> None:
        sql = self._get_rebuild_sql()
        # session_results must be dropped first to release the FK
        sr_drop_pos = sql.index("DROP TABLE IF EXISTS post_review_session_results")
        runs_drop_pos = sql.index("DROP TABLE IF EXISTS post_review_runs")
        self.assertLess(sr_drop_pos, runs_drop_pos)

    def test_rebuild_sql_uses_cascade_on_drop(self) -> None:
        sql = self._get_rebuild_sql()
        self.assertIn("post_review_session_results CASCADE", sql)
        self.assertIn("post_review_runs CASCADE", sql)

    @staticmethod
    def _strip_sql_comments(sql: str) -> str:
        """Return SQL with line-comment lines removed (lines whose first non-space char is --)."""
        return "\n".join(
            line for line in sql.splitlines()
            if line.strip() and not line.strip().startswith("--")
        )

    def test_rebuild_sql_creates_tables_with_correct_final_schema(self) -> None:
        raw_sql = self._get_rebuild_sql()
        # Strip comment lines so that the "old schema documentation" block in the
        # file header does not produce false positives on assertNotIn checks.
        ddl = self._strip_sql_comments(raw_sql)

        # post_review_runs: must use match_id TEXT PRIMARY KEY (not BIGSERIAL)
        self.assertIn("match_id TEXT PRIMARY KEY", ddl)
        self.assertIn("candidate_count INTEGER NOT NULL", ddl)
        self.assertIn("suspicious_count INTEGER NOT NULL", ddl)
        self.assertIn("summary_text_json JSONB NOT NULL", ddl)
        self.assertIn("updated_at TIMESTAMPTZ NOT NULL", ddl)
        # post_review_session_results: composite PK, review_result (not final_label)
        self.assertIn("review_result TEXT NOT NULL", ddl)
        self.assertIn("evidence_summary TEXT NOT NULL", ddl)
        self.assertIn("session_analysis_json JSONB NOT NULL", ddl)
        self.assertIn("backend_delivery_status TEXT NOT NULL", ddl)
        self.assertIn("PRIMARY KEY (match_id, session_id)", ddl)
        # Old column definitions must NOT appear in the DDL (excluding comments)
        self.assertNotIn("final_label TEXT", ddl)
        self.assertNotIn("BIGSERIAL PRIMARY KEY", ddl)
        self.assertNotIn("post_review_run_id BIGINT", ddl)
        self.assertNotIn("decision_summary_json JSONB", ddl)
        self.assertNotIn("evidence_json JSONB", ddl)
        self.assertNotIn("completed_at TIMESTAMPTZ", ddl)

    def test_rebuild_sql_creates_tables_with_if_not_exists_for_idempotency(self) -> None:
        sql = self._get_rebuild_sql()
        # CREATE TABLE IF NOT EXISTS makes the migration safe to re-run on correct schema
        self.assertIn("CREATE TABLE IF NOT EXISTS post_review_runs", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS post_review_session_results", sql)

    def test_rebuild_sql_has_check_constraints_matching_code_contract(self) -> None:
        sql = self._get_rebuild_sql()
        self.assertIn("CHECK (status IN ('SUCCESS', 'PARTIAL_SUCCESS', 'FAILED'))", sql)
        self.assertIn("CHECK (review_result IN ('NORMAL', 'SUSPICIOUS'))", sql)
        self.assertIn("CHECK (backend_delivery_status IN ('PENDING', 'SENT', 'FAILED'))", sql)
        self.assertIn("jsonb_typeof(summary_text_json) = 'array'", sql)
        self.assertIn("jsonb_array_length(summary_text_json) = 3", sql)
        self.assertIn("jsonb_typeof(session_analysis_json) = 'object'", sql)

    def test_rebuild_sql_conflict_targets_match_upsert_sql(self) -> None:
        """The ON CONFLICT targets in repository.py match the PK definitions in 007."""
        sql = self._get_rebuild_sql()
        # repository.py uses ON CONFLICT (match_id) for post_review_runs
        # → match_id must be PRIMARY KEY in the rebuilt table
        self.assertIn("match_id TEXT PRIMARY KEY", sql)
        # repository.py uses ON CONFLICT (match_id, session_id) for session_results
        # → composite PK must exist
        self.assertIn("PRIMARY KEY (match_id, session_id)", sql)

    def test_rebuild_applied_via_migration_runner(self) -> None:
        engine = _FakeEngine()

        applied = apply_postgres_storage_migrations(engine)

        self.assertIn("007_post_review_tables_rebuild.sql", applied)
        applied_list = list(applied)
        self.assertLess(
            applied_list.index("001_post_review_tables.sql"),
            applied_list.index("007_post_review_tables_rebuild.sql"),
        )
        self.assertLess(
            applied_list.index("002_postgresql_policy_control_plane_tables.sql"),
            applied_list.index("007_post_review_tables_rebuild.sql"),
        )

    def test_rebuild_migration_rolled_back_on_failure(self) -> None:
        # 007 SQL contains 'DROP TABLE IF EXISTS post_review_session_results CASCADE'
        # which is unique to that file. Use it as the failure trigger.
        class _FailOn007Cursor(_FakeCursor):
            def execute(self, sql: str) -> None:
                super().execute(sql)
                if "DROP TABLE IF EXISTS post_review_session_results CASCADE" in sql:
                    raise RuntimeError("rebuild error")

        class _FailOn007Connection(_FakeRawConnection):
            def __init__(self) -> None:
                super().__init__()
                self.cursor_obj = _FailOn007Cursor()

        class _FailOn007Engine(_FakeEngine):
            def __init__(self) -> None:
                super().__init__()
                self.raw_connection_obj = _FailOn007Connection()

        engine = _FailOn007Engine()

        with self.assertRaisesRegex(RuntimeError, "rebuild error"):
            apply_postgres_storage_migrations(engine)

        self.assertTrue(engine.raw_connection_obj.rolled_back)
        self.assertFalse(engine.raw_connection_obj.committed)

    def test_obsolete_005_and_006_are_not_in_migration_list(self) -> None:
        """005 and 006 are superseded by 007. They must not appear in the active list."""
        from traffic_master_ai.defense.backoffice_copilot.storage.migration import (
            _POSTGRES_MIGRATION_FILES,
        )
        self.assertNotIn("005_post_review_runs_schema_drift.sql", _POSTGRES_MIGRATION_FILES)
        self.assertNotIn("006_post_review_session_results_schema_drift.sql", _POSTGRES_MIGRATION_FILES)

    def test_007_sql_contains_obsolete_reference_to_replaced_migrations(self) -> None:
        """007 must document that it replaces 005 and 006."""
        sql = self._get_rebuild_sql()
        self.assertIn("005_post_review_runs_schema_drift.sql", sql)
        self.assertIn("006_post_review_session_results_schema_drift.sql", sql)
