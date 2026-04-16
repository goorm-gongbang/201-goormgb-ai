from __future__ import annotations

import re
import unittest
from datetime import UTC, datetime
from pathlib import Path

from traffic_master_ai.defense.backoffice_copilot.core.models import (
    PostReviewRunRecord,
    PostReviewSessionResultRecord,
    SessionAnalysis,
)
from traffic_master_ai.defense.backoffice_copilot.storage.repository import PkConflictPolicy
from traffic_master_ai.defense.backoffice_copilot.storage.validators import (
    ALLOWED_BACKEND_DELIVERY_STATUSES,
    ALLOWED_REVIEW_RESULTS,
    ALLOWED_RUN_STATUSES,
    StorageValidationError,
    serialize_run_record,
    serialize_session_result_record,
    validate_session_analysis_json,
    validate_summary_text_json,
)


def _session_analysis() -> SessionAnalysis:
    return SessionAnalysis(
        session_id="sess-1",
        latest_flow_state="F4M",
        latest_action="THROTTLE",
        latest_tier="T2",
        terminal_outcome="NOT_BLOCKED",
        seen_t1=True,
        seen_t2=True,
        vqa_fail_count=1,
        throttle_event_count=1,
        suspicious_signals=["Reached T2 during session"],
        timeline_summary=["Session reached T2 during evaluation."],
        needs_raw_fallback=False,
    )


def _run_record() -> PostReviewRunRecord:
    now = datetime(2026, 3, 27, 1, 0, 0, tzinfo=UTC)
    return PostReviewRunRecord(
        match_id="match-1",
        window_start_ms=100,
        window_end_ms=200,
        candidate_count=1,
        suspicious_count=1,
        summary_text_json=[
            "Window reviewed 1 candidate session.",
            "1 session remained suspicious after review.",
            "Summary stayed independent from DB write orchestration.",
        ],
        status="SUCCESS",
        created_at=now,
        updated_at=now,
    )


def _session_record() -> PostReviewSessionResultRecord:
    now = datetime(2026, 3, 27, 1, 0, 0, tzinfo=UTC)
    return PostReviewSessionResultRecord(
        match_id="match-1",
        session_id="sess-1",
        review_result="SUSPICIOUS",
        evidence_summary="Observed repeated T2 throttle activity.",
        session_analysis_json=_session_analysis(),
        backend_delivery_status="PENDING",
        created_at=now,
        updated_at=now,
    )


class BackofficeCopilotStorageTests(unittest.TestCase):
    def test_task_2_sql_contract_keeps_exactly_two_tables(self) -> None:
        sql_path = Path(
            "src/traffic_master_ai/defense/backoffice_copilot/storage/sql/001_post_review_tables.sql"
        )
        sql_text = sql_path.read_text(encoding="utf-8")

        create_tables = re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", sql_text)
        self.assertEqual(create_tables, ["post_review_runs", "post_review_session_results"])
        self.assertEqual(sql_text.count("CREATE TABLE IF NOT EXISTS"), 2)
        self.assertIn("CHECK (status IN ('SUCCESS', 'PARTIAL_SUCCESS', 'FAILED'))", sql_text)
        self.assertIn("CHECK (review_result IN ('NORMAL', 'SUSPICIOUS'))", sql_text)
        self.assertIn("CHECK (backend_delivery_status IN ('PENDING', 'SENT', 'FAILED'))", sql_text)

    def test_allowed_value_sets_match_documented_contract(self) -> None:
        self.assertEqual(ALLOWED_RUN_STATUSES, frozenset({"SUCCESS", "PARTIAL_SUCCESS", "FAILED"}))
        self.assertEqual(ALLOWED_REVIEW_RESULTS, frozenset({"NORMAL", "SUSPICIOUS"}))
        self.assertEqual(ALLOWED_BACKEND_DELIVERY_STATUSES, frozenset({"PENDING", "SENT", "FAILED"}))
        self.assertEqual(PkConflictPolicy.FAIL_FAST.value, "fail_fast")
        self.assertEqual(PkConflictPolicy.UPSERT.value, "upsert")

    def test_validators_accept_storage_compatible_json_payloads(self) -> None:
        validated_summary = validate_summary_text_json(_run_record().summary_text_json)
        validated_session_analysis = validate_session_analysis_json(_session_analysis())
        serialized_run = serialize_run_record(_run_record())
        serialized_session = serialize_session_result_record(_session_record())

        self.assertEqual(len(validated_summary), 3)
        self.assertEqual(validated_session_analysis["session_id"], "sess-1")
        self.assertEqual(serialized_run["status"], "SUCCESS")
        self.assertEqual(serialized_session["review_result"], "SUSPICIOUS")
        self.assertEqual(serialized_session["backend_delivery_status"], "PENDING")

    def test_validators_reject_invalid_summary_and_session_analysis_shapes(self) -> None:
        with self.assertRaises(StorageValidationError):
            validate_summary_text_json(["only", "two"])

        with self.assertRaises(StorageValidationError):
            validate_session_analysis_json(
                {
                    "session_id": "sess-1",
                    "latest_flow_state": "F4M",
                    "latest_action": "THROTTLE",
                    "latest_tier": "T2",
                    "terminal_outcome": "NOT_BLOCKED",
                    "seen_t1": True,
                    "seen_t2": True,
                    "vqa_fail_count": 1,
                    "throttle_event_count": 1,
                    "suspicious_signals": ["Reached T2 during session"],
                    "timeline_summary": "not-a-list",
                    "needs_raw_fallback": False,
                }
            )

        invalid_session_record = _session_record()
        invalid_session_record.backend_delivery_status = ""
        with self.assertRaises(StorageValidationError):
            serialize_session_result_record(invalid_session_record)


def _extract_insert_columns(insert_sql: str) -> frozenset[str]:
    """Parse column names from INSERT INTO table (...) VALUES block."""
    match = re.search(r"INSERT INTO \w+ \(\n(.*?)\) VALUES", insert_sql, re.DOTALL)
    assert match is not None, f"Could not parse INSERT SQL columns: {insert_sql[:80]}"
    return frozenset(
        col.strip().rstrip(",")
        for col in match.group(1).splitlines()
        if col.strip()
    )


class SaveContractTests(unittest.TestCase):
    """Verify that the serializers, INSERT SQL, and DDL stay in sync.

    These tests break intentionally if a new column is added to the code
    but not wired into the SQL (or vice versa), preventing schema drift
    from silently returning.
    """

    def test_serialize_run_record_keys_match_insert_sql_columns(self) -> None:
        """serialize_run_record() output keys must exactly equal _INSERT_RUN_SQL column list."""
        from traffic_master_ai.defense.backoffice_copilot.storage.repository import (
            _INSERT_RUN_SQL,
        )

        params = serialize_run_record(_run_record())
        sql_columns = _extract_insert_columns(_INSERT_RUN_SQL)

        self.assertEqual(frozenset(params.keys()), sql_columns)

    def test_serialize_session_result_record_keys_match_insert_sql_columns(self) -> None:
        """serialize_session_result_record() output keys must exactly equal _INSERT_SESSION_RESULT_SQL column list."""
        from traffic_master_ai.defense.backoffice_copilot.storage.repository import (
            _INSERT_SESSION_RESULT_SQL,
        )

        params = serialize_session_result_record(_session_record())
        sql_columns = _extract_insert_columns(_INSERT_SESSION_RESULT_SQL)

        self.assertEqual(frozenset(params.keys()), sql_columns)

    def test_run_record_insert_and_upsert_sql_have_identical_column_lists(self) -> None:
        """INSERT and UPSERT SQL for post_review_runs must address the same columns."""
        from traffic_master_ai.defense.backoffice_copilot.storage.repository import (
            _INSERT_RUN_SQL,
            _UPSERT_RUN_SQL,
        )

        self.assertEqual(
            _extract_insert_columns(_INSERT_RUN_SQL),
            _extract_insert_columns(_UPSERT_RUN_SQL),
        )

    def test_session_result_insert_and_upsert_sql_have_identical_column_lists(self) -> None:
        """INSERT and UPSERT SQL for post_review_session_results must address the same columns."""
        from traffic_master_ai.defense.backoffice_copilot.storage.repository import (
            _INSERT_SESSION_RESULT_SQL,
            _UPSERT_SESSION_RESULT_SQL,
        )

        self.assertEqual(
            _extract_insert_columns(_INSERT_SESSION_RESULT_SQL),
            _extract_insert_columns(_UPSERT_SESSION_RESULT_SQL),
        )

    def test_save_bundle_executes_both_run_and_session_in_one_transaction(self) -> None:
        """save_bundle() must open exactly one transaction and execute both the run and session writes."""
        from unittest.mock import patch
        from traffic_master_ai.defense.backoffice_copilot.storage.repository import (
            PostgresPostReviewWriteRepository,
            PkConflictPolicy,
        )

        execute_calls: list[frozenset[str]] = []

        def _fake_execute(_self_repo: object, _connection: object, _sql_text: str, params: dict) -> None:
            execute_calls.append(frozenset(params.keys()))

        class _FakeTxn:
            def __enter__(self) -> object:
                return object()

            def __exit__(self, *_: object) -> bool:
                return False

        class _FakeEngine:
            begin_count = 0

            def begin(self) -> _FakeTxn:
                self.__class__.begin_count += 1
                return _FakeTxn()

        engine = _FakeEngine()
        repo = PostgresPostReviewWriteRepository(engine=engine, conflict_policy=PkConflictPolicy.UPSERT)

        with patch.object(PostgresPostReviewWriteRepository, "_execute", _fake_execute):
            repo.save_bundle(_run_record(), [_session_record()])

        # Exactly one transaction opened — both writes share the same BEGIN/COMMIT
        self.assertEqual(_FakeEngine.begin_count, 1)
        # Two _execute calls: one for the run row, one for the session row
        self.assertEqual(len(execute_calls), 2)
        # First call carries run record params, second carries session result params
        run_params, session_params = execute_calls
        self.assertIn("candidate_count", run_params)
        self.assertIn("summary_text_json", run_params)
        self.assertIn("session_analysis_json", session_params)
        self.assertIn("backend_delivery_status", session_params)


def _extract_create_table_columns(sql: str, table_name: str) -> frozenset[str]:
    """Extract column names from CREATE TABLE block in DDL SQL."""
    import re

    # Match the CREATE TABLE block for the given table
    pattern = rf"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?{re.escape(table_name)}\s*\(\n(.*?)(?:\n\);|\n\s+CONSTRAINT|\n\s+PRIMARY KEY \()"
    if match is None:
        # Try without IF NOT EXISTS
        pattern = rf"CREATE TABLE {re.escape(table_name)} \(\n(.*?)(?:\n\);|\n    CONSTRAINT|\n    PRIMARY KEY \()"
        match = re.search(pattern, sql, re.DOTALL)
    assert match is not None, f"Could not find CREATE TABLE block for {table_name}"

    col_names: set[str] = set()
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        # First token is the column name
        token = stripped.split()[0]
        if token.upper() in ("CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN"):
            continue
        col_names.add(token)
    return frozenset(col_names)


class DdlContractAlignmentTests(unittest.TestCase):
    """Regression-prevention tests that ensure 001 DDL, 007 rebuild DDL,
    INSERT SQL, and serializer output all define the same column sets.

    If a new column is added to one place but not another, one of these
    tests will break before any data reaches the database.
    """

    _SQL_DIR = Path(
        "src/traffic_master_ai/defense/backoffice_copilot/storage/sql"
    )

    def _read_sql(self, filename: str) -> str:
        return (self._SQL_DIR / filename).read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # 001 DDL vs serializer contract
    # ------------------------------------------------------------------

    def test_001_ddl_post_review_runs_columns_match_serializer_output(self) -> None:
        """Columns in 001_post_review_tables.sql must equal serialize_run_record() keys."""
        from traffic_master_ai.defense.backoffice_copilot.storage.repository import (
            _INSERT_RUN_SQL,
        )

        sql_001 = self._read_sql("001_post_review_tables.sql")
        ddl_columns = _extract_create_table_columns(sql_001, "post_review_runs")
        insert_columns = _extract_insert_columns(_INSERT_RUN_SQL)
        serializer_keys = frozenset(serialize_run_record(_run_record()).keys())

        self.assertEqual(
            ddl_columns,
            insert_columns,
            "001 DDL post_review_runs columns differ from _INSERT_RUN_SQL columns",
        )
        self.assertEqual(
            insert_columns,
            serializer_keys,
            "serialize_run_record() keys differ from _INSERT_RUN_SQL columns",
        )

    def test_001_ddl_post_review_session_results_columns_match_serializer_output(self) -> None:
        """Columns in 001_post_review_tables.sql must equal serialize_session_result_record() keys."""
        from traffic_master_ai.defense.backoffice_copilot.storage.repository import (
            _INSERT_SESSION_RESULT_SQL,
        )

        sql_001 = self._read_sql("001_post_review_tables.sql")
        ddl_columns = _extract_create_table_columns(sql_001, "post_review_session_results")
        insert_columns = _extract_insert_columns(_INSERT_SESSION_RESULT_SQL)
        serializer_keys = frozenset(serialize_session_result_record(_session_record()).keys())

        self.assertEqual(
            ddl_columns,
            insert_columns,
            "001 DDL post_review_session_results columns differ from _INSERT_SESSION_RESULT_SQL",
        )
        self.assertEqual(
            insert_columns,
            serializer_keys,
            "serialize_session_result_record() keys differ from _INSERT_SESSION_RESULT_SQL",
        )

    # ------------------------------------------------------------------
    # 007 rebuild DDL vs 001 DDL (must be identical for both tables)
    # ------------------------------------------------------------------

    def test_007_rebuild_ddl_post_review_runs_matches_001(self) -> None:
        """007 rebuild must create post_review_runs with the same columns as 001."""
        sql_001 = self._read_sql("001_post_review_tables.sql")
        sql_007 = self._read_sql("007_post_review_tables_rebuild.sql")

        cols_001 = _extract_create_table_columns(sql_001, "post_review_runs")
        cols_007 = _extract_create_table_columns(sql_007, "post_review_runs")

        self.assertEqual(
            cols_001,
            cols_007,
            "007 rebuild post_review_runs columns diverge from 001 DDL — update both together",
        )

    def test_007_rebuild_ddl_post_review_session_results_matches_001(self) -> None:
        """007 rebuild must create post_review_session_results with the same columns as 001."""
        sql_001 = self._read_sql("001_post_review_tables.sql")
        sql_007 = self._read_sql("007_post_review_tables_rebuild.sql")

        cols_001 = _extract_create_table_columns(sql_001, "post_review_session_results")
        cols_007 = _extract_create_table_columns(sql_007, "post_review_session_results")

        self.assertEqual(
            cols_001,
            cols_007,
            "007 rebuild post_review_session_results columns diverge from 001 DDL — update both",
        )

    # ------------------------------------------------------------------
    # Guard: old bootstrap column names must not sneak back in
    # ------------------------------------------------------------------

    def test_old_schema_column_names_absent_from_insert_sql_and_serializers(self) -> None:
        """Column names from the old bootstrap schema must not appear in current INSERT SQL
        or serializer output. This catches regressions where someone accidentally
        re-introduces the old design."""
        from traffic_master_ai.defense.backoffice_copilot.storage.repository import (
            _INSERT_RUN_SQL,
            _INSERT_SESSION_RESULT_SQL,
            _UPSERT_RUN_SQL,
            _UPSERT_SESSION_RESULT_SQL,
        )

        old_column_names = {
            "final_label",        # was review_result in old bootstrap
            "decision_summary_json",  # was session_analysis_json
            "evidence_json",      # was evidence_summary (different type too)
            "post_review_run_id", # surrogate FK; new schema has no FK
            "completed_at",       # was updated_at
        }
        all_sql = "\n".join([
            _INSERT_RUN_SQL,
            _UPSERT_RUN_SQL,
            _INSERT_SESSION_RESULT_SQL,
            _UPSERT_SESSION_RESULT_SQL,
        ])
        all_keys = set(serialize_run_record(_run_record()).keys()) | set(
            serialize_session_result_record(_session_record()).keys()
        )

        for bad_col in old_column_names:
            with self.subTest(bad_col=bad_col):
                self.assertNotIn(
                    bad_col,
                    all_sql,
                    f"Old bootstrap column '{bad_col}' found in INSERT/UPSERT SQL",
                )
                self.assertNotIn(
                    bad_col,
                    all_keys,
                    f"Old bootstrap column '{bad_col}' found in serializer output",
                )

    def test_upsert_conflict_targets_match_pk_definitions_in_007_ddl(self) -> None:
        """ON CONFLICT targets in repository.py must match PKs defined in 007 rebuild DDL."""
        from traffic_master_ai.defense.backoffice_copilot.storage.repository import (
            _UPSERT_RUN_SQL,
            _UPSERT_SESSION_RESULT_SQL,
        )

        # run upsert must conflict on match_id (TEXT PK, not surrogate BIGSERIAL)
        self.assertIn("ON CONFLICT (match_id)", _UPSERT_RUN_SQL)
        # session result upsert must conflict on composite (match_id, session_id)
        self.assertIn("ON CONFLICT (match_id, session_id)", _UPSERT_SESSION_RESULT_SQL)

        # Verify 007 DDL defines these exact PKs
        sql_007 = self._read_sql("007_post_review_tables_rebuild.sql")
        self.assertIn("match_id TEXT PRIMARY KEY", sql_007)
        self.assertIn("PRIMARY KEY (match_id, session_id)", sql_007)


if __name__ == "__main__":
    unittest.main()
