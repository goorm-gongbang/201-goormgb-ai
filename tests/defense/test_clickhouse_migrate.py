"""Tests for tm-ai-clickhouse-migrate command.

Verification scope:
  - --dry-run: parses statements, no HTTP, exits 0
  - SQL statement parsing from 004_clickhouse_read_models.sql
  - DDL target list: 3 views in correct order
  - CREATE OR REPLACE VIEW (not IF NOT EXISTS) — idempotency contract
  - 10-min window (600000ms) in defense_session_rollups — regression prevention
  - Summary JSON shape and field contract
  - Exit code: 0 on success/dry-run, 1 on failure
  - Fake HTTP server: DDL statements reach ClickHouse with correct auth
  - TM_CLICKHOUSE_URL missing → exit 1, summary status=failed
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Sequence
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from traffic_master_ai.defense.backoffice_copilot.storage.clickhouse_migrate import (
    _parse_ddl_statements,
    apply_clickhouse_ddl_migrations,
    run_clickhouse_migrate,
)

_SQL_DIR = Path(__file__).resolve().parents[2] / "src" / "traffic_master_ai" / "defense" / "backoffice_copilot" / "storage" / "sql"
_DDL_FILE = _SQL_DIR / "004_clickhouse_read_models.sql"

# ---------------------------------------------------------------------------
# Fake HTTP server
# ---------------------------------------------------------------------------

class _RecordingDdlHandler(BaseHTTPRequestHandler):
    """Records every DDL POST request for assertion; always responds 200."""

    requests: list[dict[str, object]] = []
    response_status: int = 200

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8")
        parsed = urlsplit(self.path)
        self.__class__.requests.append(
            {
                "path": parsed.path,
                "query": parse_qs(parsed.query, keep_blank_values=True),
                "body": body,
                "authorization": self.headers.get("Authorization"),
            }
        )
        self.send_response(self.__class__.response_status)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:  # pragma: no cover
        return


def _start_fake_server(handler_cls: type) -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


# ---------------------------------------------------------------------------
# SQL parsing tests
# ---------------------------------------------------------------------------

class ParseDdlStatementsTests(unittest.TestCase):
    def test_three_view_statements_parsed(self) -> None:
        sql = _DDL_FILE.read_text(encoding="utf-8")
        stmts = _parse_ddl_statements(sql)
        self.assertEqual(len(stmts), 3, f"Expected 3 statements, got {len(stmts)}: {[s[:60] for s in stmts]}")

    def test_all_statements_use_create_or_replace_view(self) -> None:
        """Idempotency contract: every statement is CREATE OR REPLACE VIEW."""
        sql = _DDL_FILE.read_text(encoding="utf-8")
        stmts = _parse_ddl_statements(sql)
        for stmt in stmts:
            flat = " ".join(stmt.split()).upper()
            self.assertIn(
                "CREATE OR REPLACE VIEW",
                flat,
                f"Statement does not use CREATE OR REPLACE VIEW: {stmt[:80]}",
            )
        # Regression: must NOT use IF NOT EXISTS (that form blocks VIEW updates)
        for stmt in stmts:
            flat = " ".join(stmt.split()).upper()
            self.assertNotIn(
                "CREATE VIEW IF NOT EXISTS",
                flat,
                f"Statement uses CREATE VIEW IF NOT EXISTS (cannot update existing VIEW): {stmt[:80]}",
            )

    def test_view_names_in_order(self) -> None:
        """The three views appear in the canonical execution order."""
        sql = _DDL_FILE.read_text(encoding="utf-8")
        stmts = _parse_ddl_statements(sql)
        names = [" ".join(s.split()) for s in stmts]
        self.assertIn("defense_session_rollups", names[0])
        self.assertIn("defense_match_rollups", names[1])
        self.assertIn("defense_post_review_candidates_v1", names[2])

    def test_comment_only_segment_excluded(self) -> None:
        sql = "-- just a comment\n\nCREATE OR REPLACE VIEW foo AS SELECT 1;\n-- trailing comment\n"
        stmts = _parse_ddl_statements(sql)
        self.assertEqual(len(stmts), 1)
        self.assertIn("CREATE OR REPLACE VIEW foo", stmts[0])

    def test_empty_segment_excluded(self) -> None:
        sql = "CREATE OR REPLACE VIEW a AS SELECT 1;\n\n\n;"
        stmts = _parse_ddl_statements(sql)
        self.assertEqual(len(stmts), 1)


# ---------------------------------------------------------------------------
# 10-minute window regression prevention
# ---------------------------------------------------------------------------

class SessionRollupWindowRegressionTests(unittest.TestCase):
    """Prevent re-introduction of the 5-min/10-min window mismatch.

    defense_session_rollups must use WITH 600000 AS window_ms (10 min) to
    match DEFAULT_POST_REVIEW_WINDOW_SECONDS = 600 in runner.py.  A window of
    300000 (5 min) causes structural candidate_count=0 / status=no_input on
    every Post-Review run.
    """

    def test_session_rollup_uses_600000ms_window(self) -> None:
        sql = _DDL_FILE.read_text(encoding="utf-8")
        stmts = _parse_ddl_statements(sql)
        # Match the statement that *creates* defense_session_rollups (not the one that SELECTs from it)
        session_stmt = next(
            (s for s in stmts if "CREATE OR REPLACE VIEW defense_session_rollups" in s.replace("\n", " ")),
            None,
        )
        self.assertIsNotNone(session_stmt, "defense_session_rollups statement not found")
        assert session_stmt is not None
        self.assertIn(
            "600000",
            session_stmt,
            "defense_session_rollups must use WITH 600000 AS window_ms (10-min window). "
            "300000 (5-min) causes structural no_input in Post-Review.",
        )
        self.assertNotIn(
            "300000",
            session_stmt,
            "defense_session_rollups must not use 300000 (5-min window). "
            "This causes exact-match misses in Post-Review.",
        )

    def test_match_rollup_uses_300000ms_window(self) -> None:
        """defense_match_rollups keeps its independent 5-min window."""
        sql = _DDL_FILE.read_text(encoding="utf-8")
        stmts = _parse_ddl_statements(sql)
        match_stmt = next(
            (s for s in stmts if "defense_match_rollups" in s and "defense_session_rollups" not in s and "defense_post_review" not in s),
            None,
        )
        self.assertIsNotNone(match_stmt, "defense_match_rollups statement not found")
        assert match_stmt is not None
        self.assertIn(
            "300000",
            match_stmt,
            "defense_match_rollups must use 300000ms (5-min) — independent aggregate.",
        )

    def test_post_review_window_constant_aligns_with_session_rollup_view(self) -> None:
        """Runner DEFAULT_POST_REVIEW_WINDOW_SECONDS must equal 600000ms VIEW window."""
        from traffic_master_ai.defense.backoffice_copilot.runner import (
            DEFAULT_POST_REVIEW_WINDOW_SECONDS,
        )

        SESSION_ROLLUP_VIEW_WINDOW_MS = 600_000
        self.assertEqual(
            DEFAULT_POST_REVIEW_WINDOW_SECONDS * 1000,
            SESSION_ROLLUP_VIEW_WINDOW_MS,
            "Post-Review window must equal the ClickHouse defense_session_rollups VIEW window "
            "(600,000ms). Mismatch causes structural no_input on every run.",
        )


# ---------------------------------------------------------------------------
# apply_clickhouse_ddl_migrations — dry-run
# ---------------------------------------------------------------------------

class ApplyDdlDryRunTests(unittest.TestCase):
    def test_dry_run_returns_statements_without_connecting(self) -> None:
        """dry_run=True must return statements and never open a network connection."""
        stmts = apply_clickhouse_ddl_migrations(dry_run=True)
        self.assertEqual(len(stmts), 3)

    def test_dry_run_does_not_require_env(self) -> None:
        """dry_run=True must not read TM_CLICKHOUSE_URL."""
        with patch.dict("os.environ", {}, clear=False):
            env = {"TM_CLICKHOUSE_URL": ""}
            with patch.dict("os.environ", env):
                stmts = apply_clickhouse_ddl_migrations(dry_run=True)
        self.assertEqual(len(stmts), 3)

    def test_dry_run_fails_if_sql_file_missing(self) -> None:
        """Missing SQL file must raise RuntimeError even in dry-run."""
        with patch(
            "traffic_master_ai.defense.backoffice_copilot.storage.clickhouse_migrate._read_ddl_sql",
            side_effect=RuntimeError("file missing"),
        ):
            with self.assertRaises(RuntimeError):
                apply_clickhouse_ddl_migrations(dry_run=True)


# ---------------------------------------------------------------------------
# apply_clickhouse_ddl_migrations — apply via fake HTTP server
# ---------------------------------------------------------------------------

class ApplyDdlHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingDdlHandler.requests = []
        _RecordingDdlHandler.response_status = 200
        self._server, self._port = _start_fake_server(_RecordingDdlHandler)

    def tearDown(self) -> None:
        self._server.shutdown()

    def _url(self, *, user: str = "default", password: str = "secret") -> str:
        return f"http://{user}:{password}@127.0.0.1:{self._port}/ai_defense"

    def test_apply_sends_three_ddl_requests(self) -> None:
        apply_clickhouse_ddl_migrations(clickhouse_url=self._url())
        self.assertEqual(len(_RecordingDdlHandler.requests), 3)

    def test_apply_sends_auth_header(self) -> None:
        import base64

        apply_clickhouse_ddl_migrations(clickhouse_url=self._url(user="u", password="p"))
        expected = "Basic " + base64.b64encode(b"u:p").decode()
        for req in _RecordingDdlHandler.requests:
            self.assertEqual(req["authorization"], expected)

    def test_apply_sends_database_param(self) -> None:
        apply_clickhouse_ddl_migrations(clickhouse_url=self._url())
        for req in _RecordingDdlHandler.requests:
            query = req["query"]
            self.assertIn("database", query)
            self.assertEqual(query["database"], ["ai_defense"])

    def test_apply_sends_query_param_with_create_or_replace(self) -> None:
        apply_clickhouse_ddl_migrations(clickhouse_url=self._url())
        for req in _RecordingDdlHandler.requests:
            query_param = req["query"].get("query", [""])[0].upper()
            self.assertIn("CREATE OR REPLACE VIEW", query_param)

    def test_apply_fails_on_http_error(self) -> None:
        _RecordingDdlHandler.response_status = 500
        with self.assertRaises(RuntimeError):
            apply_clickhouse_ddl_migrations(clickhouse_url=self._url())

    def test_apply_missing_url_raises_value_error(self) -> None:
        with patch.dict("os.environ", {"TM_CLICKHOUSE_URL": ""}):
            with self.assertRaises(ValueError, msg="must raise ValueError when TM_CLICKHOUSE_URL unset"):
                apply_clickhouse_ddl_migrations()


# ---------------------------------------------------------------------------
# run_clickhouse_migrate (CLI entry point) — summary JSON and exit codes
# ---------------------------------------------------------------------------

class RunClickhouseMigrateCLITests(unittest.TestCase):
    def _capture_stdout_and_run(self, argv: Sequence[str]) -> tuple[int, list[str]]:
        """Run run_clickhouse_migrate and capture printed lines."""
        import builtins

        original = builtins.print
        lines: list[str] = []

        def capturing_print(*args: object, **kwargs: object) -> None:
            text = " ".join(str(a) for a in args)
            lines.append(text)
            original(*args, **kwargs)

        with patch("builtins.print", side_effect=capturing_print):
            try:
                run_clickhouse_migrate(list(argv))
                exit_code = 0
            except SystemExit as exc:
                exit_code = int(exc.code) if exc.code is not None else 0
        return exit_code, lines

    def test_dry_run_exits_zero(self) -> None:
        exit_code, _ = self._capture_stdout_and_run(["--dry-run"])
        self.assertEqual(exit_code, 0)

    def test_dry_run_last_line_is_json_summary(self) -> None:
        _, lines = self._capture_stdout_and_run(["--dry-run"])
        last = lines[-1]
        summary = json.loads(last)
        self.assertEqual(summary["command"], "tm-ai-clickhouse-migrate")
        self.assertEqual(summary["status"], "dry_run")
        self.assertEqual(summary["target"], "clickhouse_ddl")
        self.assertEqual(summary["mode"], "dry_run")
        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["error_count"], 0)
        self.assertEqual(summary["input_count"], 3)
        self.assertEqual(summary["output_count"], 3)
        self.assertIn("duration_ms", summary)
        self.assertGreaterEqual(summary["duration_ms"], 0)

    def test_dry_run_summary_fields_complete(self) -> None:
        _, lines = self._capture_stdout_and_run(["--dry-run"])
        summary = json.loads(lines[-1])
        required_fields = {
            "command", "mode", "status", "target",
            "input_count", "output_count", "skipped_count",
            "error_count", "duration_ms", "dry_run",
        }
        for field in required_fields:
            self.assertIn(field, summary, f"Summary missing field: {field}")

    def test_failed_exits_one_and_has_error_field(self) -> None:
        with patch(
            "traffic_master_ai.defense.backoffice_copilot.storage.clickhouse_migrate._read_ddl_sql",
            side_effect=RuntimeError("simulated failure"),
        ):
            exit_code, lines = self._capture_stdout_and_run(["--dry-run"])
        self.assertEqual(exit_code, 1)
        summary = json.loads(lines[-1])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["error_count"], 1)
        self.assertIn("error", summary)
        self.assertIn("RuntimeError", summary["error"])

    def test_missing_url_exits_one_on_apply(self) -> None:
        """apply (no --dry-run) with no TM_CLICKHOUSE_URL must exit 1."""
        with patch.dict("os.environ", {"TM_CLICKHOUSE_URL": ""}):
            exit_code, lines = self._capture_stdout_and_run([])
        self.assertEqual(exit_code, 1)
        summary = json.loads(lines[-1])
        self.assertEqual(summary["status"], "failed")

    def test_apply_success_via_fake_server(self) -> None:
        _RecordingDdlHandler.requests = []
        _RecordingDdlHandler.response_status = 200
        server, port = _start_fake_server(_RecordingDdlHandler)
        try:
            url = f"http://user:pass@127.0.0.1:{port}/ai_defense"
            with patch.dict("os.environ", {"TM_CLICKHOUSE_URL": url}):
                exit_code, lines = self._capture_stdout_and_run([])
        finally:
            server.shutdown()

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(_RecordingDdlHandler.requests), 3)
        summary = json.loads(lines[-1])
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["input_count"], 3)
        self.assertEqual(summary["output_count"], 3)
        self.assertFalse(summary["dry_run"])


# ---------------------------------------------------------------------------
# execute_clickhouse_ddl (helper in clickhouse_connection)
# ---------------------------------------------------------------------------

class ExecuteClickhouseDdlTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingDdlHandler.requests = []
        _RecordingDdlHandler.response_status = 200
        self._server, self._port = _start_fake_server(_RecordingDdlHandler)

    def tearDown(self) -> None:
        self._server.shutdown()

    def test_ddl_reaches_server(self) -> None:
        from traffic_master_ai.defense.backoffice_copilot.storage.clickhouse_connection import (
            execute_clickhouse_ddl,
        )

        url = f"http://u:p@127.0.0.1:{self._port}/db"
        stmt = "CREATE OR REPLACE VIEW v AS SELECT 1"
        execute_clickhouse_ddl(url=url, statement=stmt)
        self.assertEqual(len(_RecordingDdlHandler.requests), 1)
        req = _RecordingDdlHandler.requests[0]
        self.assertIn("CREATE OR REPLACE VIEW v AS SELECT 1", req["query"]["query"][0])

    def test_ddl_raises_on_4xx(self) -> None:
        from traffic_master_ai.defense.backoffice_copilot.storage.clickhouse_connection import (
            execute_clickhouse_ddl,
        )

        _RecordingDdlHandler.response_status = 400
        url = f"http://u:p@127.0.0.1:{self._port}/db"
        with self.assertRaises(RuntimeError):
            execute_clickhouse_ddl(url=url, statement="CREATE OR REPLACE VIEW v AS SELECT 1")

    def test_ddl_raises_on_5xx(self) -> None:
        from traffic_master_ai.defense.backoffice_copilot.storage.clickhouse_connection import (
            execute_clickhouse_ddl,
        )

        _RecordingDdlHandler.response_status = 500
        url = f"http://u:p@127.0.0.1:{self._port}/db"
        with self.assertRaises(RuntimeError):
            execute_clickhouse_ddl(url=url, statement="CREATE OR REPLACE VIEW v AS SELECT 1")
