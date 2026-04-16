"""PostgreSQL storage migration command for Backoffice Copilot storage."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from .connection import build_postgres_engine_from_env

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
else:
    Engine = Any

_SQL_DIR = Path(__file__).resolve().parent / "sql"
_POST_REVIEW_MIGRATION_FILE = "001_post_review_tables.sql"
_POLICY_CONTROL_PLANE_MIGRATION_FILE = "002_postgresql_policy_control_plane_tables.sql"
_POST_REVIEW_SCHEMA_DRIFT_FILE = "005_post_review_runs_schema_drift.sql"
_SESSION_RESULTS_SCHEMA_DRIFT_FILE = "006_post_review_session_results_schema_drift.sql"
_POSTGRES_MIGRATION_FILES = (
    _POST_REVIEW_MIGRATION_FILE,
    _POLICY_CONTROL_PLANE_MIGRATION_FILE,
    _POST_REVIEW_SCHEMA_DRIFT_FILE,
    _SESSION_RESULTS_SCHEMA_DRIFT_FILE,
)
_LOGGER = logging.getLogger(__name__)


def apply_postgres_storage_migrations(
    engine: Engine | None = None,
    *,
    migration_files: Sequence[str] = _POSTGRES_MIGRATION_FILES,
    dry_run: bool = False,
) -> tuple[str, ...]:
    file_names = tuple(migration_files)
    mode = "dry_run" if dry_run else "apply"
    _LOGGER.info(
        "postgres_storage_migration_start mode=%s files=%s",
        mode,
        ",".join(file_names),
    )
    if dry_run:
        for index, file_name in enumerate(file_names, start=1):
            _read_migration_sql(file_name)
            _LOGGER.info(
                "postgres_storage_migration_plan index=%s file=%s",
                index,
                file_name,
            )
        _LOGGER.info(
            "postgres_storage_migration_complete mode=dry_run planned_count=%s",
            len(file_names),
        )
        return file_names

    owns_engine = engine is None
    pg_engine = engine if engine is not None else build_postgres_engine_from_env()
    applied: list[str] = []
    try:
        raw_connection = pg_engine.raw_connection()
        try:
            cursor = raw_connection.cursor()
            try:
                for index, file_name in enumerate(file_names, start=1):
                    _LOGGER.info(
                        "postgres_storage_migration_apply_start index=%s file=%s",
                        index,
                        file_name,
                    )
                    try:
                        cursor.execute(_read_migration_sql(file_name))
                    except Exception:
                        _LOGGER.exception(
                            "postgres_storage_migration_apply_failed index=%s file=%s",
                            index,
                            file_name,
                        )
                        raise
                    applied.append(file_name)
                    _LOGGER.info(
                        "postgres_storage_migration_apply_complete index=%s file=%s",
                        index,
                        file_name,
                    )
                raw_connection.commit()
                _LOGGER.info(
                    "postgres_storage_migration_complete mode=apply applied_count=%s",
                    len(applied),
                )
            except Exception:
                raw_connection.rollback()
                _LOGGER.info(
                    "postgres_storage_migration_rollback applied_count=%s",
                    len(applied),
                )
                raise
            finally:
                cursor.close()
        finally:
            raw_connection.close()
    finally:
        if owns_engine:
            pg_engine.dispose()
    return tuple(applied)


def _read_migration_sql(file_name: str) -> str:
    sql_path = _SQL_DIR / file_name
    if not sql_path.is_file():
        raise RuntimeError(f"PostgreSQL storage migration SQL file is missing: {file_name}")
    return sql_path.read_text(encoding="utf-8")


def run_storage_migration(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="tm-ai-storage-migrate",
        description="Apply PostgreSQL DDL migrations for AI Defense storage.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the PostgreSQL DDL migration plan without connecting to PostgreSQL.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    started = time.monotonic()
    mode = "dry_run" if args.dry_run else "apply"
    try:
        applied = apply_postgres_storage_migrations(dry_run=args.dry_run)
    except Exception as exc:
        summary = _build_storage_migration_summary(
            mode=mode,
            status="failed",
            file_names=(),
            error_count=1,
            started_at_monotonic=started,
            error=f"{type(exc).__name__}: {exc}",
        )
        _log_storage_migration_summary(summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1) from exc

    action = "planned" if args.dry_run else "applied"
    for file_name in applied:
        print(f"{action} {file_name}")
    summary = _build_storage_migration_summary(
        mode=mode,
        status="dry_run" if args.dry_run else "success",
        file_names=applied,
        error_count=0,
        started_at_monotonic=started,
    )
    _log_storage_migration_summary(summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _build_storage_migration_summary(
    *,
    mode: str,
    status: str,
    file_names: Sequence[str],
    error_count: int,
    started_at_monotonic: float,
    error: str | None = None,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "command": "tm-ai-storage-migrate",
        "mode": mode,
        "status": status,
        "target": "postgres_ddl",
        "input_count": len(file_names),
        "output_count": len(file_names) if status != "failed" else 0,
        "skipped_count": 0,
        "error_count": error_count,
        "duration_ms": max(int((time.monotonic() - started_at_monotonic) * 1000), 0),
        "dry_run": mode == "dry_run",
        "files": tuple(file_names),
    }
    if error is not None:
        summary["error"] = error
    return summary


def _log_storage_migration_summary(summary: dict[str, object]) -> None:
    _LOGGER.info(
        "storage_migration_summary mode=%s status=%s target=%s input_count=%s "
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
