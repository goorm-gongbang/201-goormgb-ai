"""ClickHouse DDL migration command for Backoffice Copilot read models.

Executes CREATE OR REPLACE VIEW statements from 004_clickhouse_read_models.sql
so that ClickHouse VIEWs can be updated on every ArgoCD PreSync — not just on
the first container initialisation (which is what /docker-entrypoint-initdb.d
covers and which does NOT re-run when a PVC already exists).

DDL targets (in execution order):
  1. defense_session_rollups            — CRITICAL: fixes 5-min→10-min window
  2. defense_match_rollups              — independent 5-min aggregate, full DDL sync
  3. defense_post_review_candidates_v1  — inherits window from defense_session_rollups

Idempotency: all statements use CREATE OR REPLACE VIEW, safe to re-run on
every sync.

Required env:
  TM_CLICKHOUSE_URL — e.g. http://user:pass@clickhouse.data.svc.cluster.local:8123/ai_defense

Not required (and ignored by this command):
  TM_PG_URL, TM_REDIS_URL, TM_ROLLOUT_SALT, TM_POLICY_*, TM_PROJECTION_*,
  TM_POLICY_OPTIMIZER_*, S3/AWS, AUTH_GUARD_URL, INTERNAL_API_KEY
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Sequence

from .clickhouse_connection import execute_clickhouse_ddl
from ...storage_env import load_clickhouse_storage_config_from_env

_SQL_DIR = Path(__file__).resolve().parent / "sql"
_CLICKHOUSE_DDL_FILE = "004_clickhouse_read_models.sql"
_DDL_TIMEOUT_SECONDS = 30.0
_LOGGER = logging.getLogger(__name__)


def _read_ddl_sql() -> str:
    path = _SQL_DIR / _CLICKHOUSE_DDL_FILE
    if not path.is_file():
        raise RuntimeError(
            f"ClickHouse DDL SQL file is missing: {_CLICKHOUSE_DDL_FILE} "
            f"(expected at {path})"
        )
    return path.read_text(encoding="utf-8")


def _parse_ddl_statements(sql_text: str) -> tuple[str, ...]:
    """Split SQL text into individual DDL statements.

    Splits on semicolons and filters out segments that contain no real SQL
    (empty, or containing only comment lines starting with '--').
    Comment lines within a statement are preserved so ClickHouse handles them.

    Limitation: semicolon-based splitting is unsafe if SQL contains semicolons
    inside string literals or dollar-quoted blocks.  This is acceptable for the
    controlled 004_clickhouse_read_models.sql file (pure VIEW definitions with no
    embedded string literals), but would need a proper SQL tokeniser for general
    use.  A DDL-keyword guard below ensures any future misparse produces a loud
    failure rather than a silent malformed query.
    """
    _DDL_KEYWORDS = frozenset({"CREATE", "DROP", "ALTER", "TRUNCATE", "RENAME"})
    statements: list[str] = []
    for raw_segment in sql_text.split(";"):
        segment = raw_segment.strip()
        if not segment:
            continue
        non_comment_lines = [
            line
            for line in segment.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        if not non_comment_lines:
            continue
        first_token = non_comment_lines[0].strip().split()[0].upper()
        if first_token not in _DDL_KEYWORDS:
            raise RuntimeError(
                f"Unexpected SQL token after semicolon split "
                f"(first_token={first_token!r}). "
                "This likely means a semicolon inside a string literal was "
                "split incorrectly. Review 004_clickhouse_read_models.sql "
                "for embedded semicolons."
            )
        statements.append(segment)
    return tuple(statements)


def apply_clickhouse_ddl_migrations(
    clickhouse_url: str | None = None,
    *,
    dry_run: bool = False,
    ddl_timeout_seconds: float = _DDL_TIMEOUT_SECONDS,
) -> tuple[str, ...]:
    """Apply ClickHouse DDL migrations from 004_clickhouse_read_models.sql.

    Returns a tuple of the statement strings that were planned (dry_run=True)
    or actually executed (dry_run=False).

    Raises RuntimeError / ValueError on any failure; callers should catch and
    exit 1.
    """
    mode = "dry_run" if dry_run else "apply"
    sql_text = _read_ddl_sql()
    statements = _parse_ddl_statements(sql_text)

    _LOGGER.info(
        "clickhouse_ddl_migration_start mode=%s file=%s statement_count=%s",
        mode,
        _CLICKHOUSE_DDL_FILE,
        len(statements),
    )

    if dry_run:
        for index, stmt in enumerate(statements, start=1):
            preview = _stmt_preview(stmt)
            _LOGGER.info(
                "clickhouse_ddl_migration_plan index=%s preview=%r",
                index,
                preview,
            )
        _LOGGER.info(
            "clickhouse_ddl_migration_complete mode=dry_run planned_count=%s",
            len(statements),
        )
        return statements

    url = clickhouse_url
    if url is None:
        config = load_clickhouse_storage_config_from_env()
        url = config.url
    if not url:
        raise ValueError(
            "TM_CLICKHOUSE_URL must be set to apply ClickHouse DDL migrations."
        )

    applied: list[str] = []
    for index, stmt in enumerate(statements, start=1):
        preview = _stmt_preview(stmt)
        _LOGGER.info(
            "clickhouse_ddl_migration_apply_start index=%s preview=%r",
            index,
            preview,
        )
        try:
            execute_clickhouse_ddl(
                url=url,
                statement=stmt,
                timeout_seconds=ddl_timeout_seconds,
            )
        except Exception:
            _LOGGER.exception(
                "clickhouse_ddl_migration_apply_failed index=%s preview=%r",
                index,
                preview,
            )
            raise
        applied.append(stmt)
        _LOGGER.info(
            "clickhouse_ddl_migration_apply_complete index=%s preview=%r",
            index,
            preview,
        )

    _LOGGER.info(
        "clickhouse_ddl_migration_complete mode=apply applied_count=%s",
        len(applied),
    )
    return tuple(applied)


def run_clickhouse_migrate(argv: Sequence[str] | None = None) -> None:
    """Entry point for tm-ai-clickhouse-migrate console script."""
    parser = argparse.ArgumentParser(
        prog="tm-ai-clickhouse-migrate",
        description=(
            "Apply ClickHouse DDL migrations (CREATE OR REPLACE VIEW) for "
            "AI Defense read models. Reads TM_CLICKHOUSE_URL from env."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Parse and plan DDL statements without connecting to ClickHouse. "
            "Exits 0 on success."
        ),
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    started = time.monotonic()
    mode = "dry_run" if args.dry_run else "apply"

    try:
        applied = apply_clickhouse_ddl_migrations(dry_run=args.dry_run)
    except Exception as exc:
        summary = _build_migrate_summary(
            mode=mode,
            status="failed",
            statement_count=0,
            error_count=1,
            started_at_monotonic=started,
            error=f"{type(exc).__name__}: {exc}",
        )
        _log_migrate_summary(summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1) from exc

    action = "planned" if args.dry_run else "applied"
    for index, stmt in enumerate(applied, start=1):
        print(f"{action} [{index}] {_stmt_preview(stmt)}...")

    summary = _build_migrate_summary(
        mode=mode,
        status="dry_run" if args.dry_run else "success",
        statement_count=len(applied),
        error_count=0,
        started_at_monotonic=started,
    )
    _log_migrate_summary(summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _stmt_preview(stmt: str, max_len: int = 80) -> str:
    """Return a single-line preview of a statement for logging."""
    return " ".join(stmt.split())[:max_len]


def _build_migrate_summary(
    *,
    mode: str,
    status: str,
    statement_count: int,
    error_count: int,
    started_at_monotonic: float,
    error: str | None = None,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "command": "tm-ai-clickhouse-migrate",
        "mode": mode,
        "status": status,
        "target": "clickhouse_ddl",
        "input_count": statement_count,
        "output_count": statement_count if status != "failed" else 0,
        "skipped_count": 0,
        "error_count": error_count,
        "duration_ms": max(int((time.monotonic() - started_at_monotonic) * 1000), 0),
        "dry_run": mode == "dry_run",
    }
    if error is not None:
        summary["error"] = error
    return summary


def _log_migrate_summary(summary: dict[str, object]) -> None:
    _LOGGER.info(
        "clickhouse_migrate_summary mode=%s status=%s target=%s input_count=%s "
        "output_count=%s skipped_count=%s error_count=%s duration_ms=%s dry_run=%s",
        summary["mode"],
        summary["status"],
        summary["target"],
        summary["input_count"],
        summary["output_count"],
        summary["skipped_count"],
        summary["error_count"],
        summary["duration_ms"],
        summary["dry_run"],
    )
