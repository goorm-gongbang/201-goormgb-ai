"""PostgreSQL storage migration command for Backoffice Copilot storage."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from .connection import build_postgres_engine_from_env

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
else:
    Engine = Any

_SQL_DIR = Path(__file__).resolve().parent / "sql"
_POLICY_CONTROL_PLANE_MIGRATION_FILE = "002_postgresql_policy_control_plane_tables.sql"
_POSTGRES_MIGRATION_FILES = (
    _POLICY_CONTROL_PLANE_MIGRATION_FILE,
)


def apply_postgres_storage_migrations(
    engine: Engine | None = None,
    *,
    migration_files: Sequence[str] = _POSTGRES_MIGRATION_FILES,
) -> tuple[str, ...]:
    owns_engine = engine is None
    pg_engine = engine if engine is not None else build_postgres_engine_from_env()
    applied: list[str] = []
    try:
        raw_connection = pg_engine.raw_connection()
        try:
            cursor = raw_connection.cursor()
            try:
                for file_name in migration_files:
                    cursor.execute(_read_migration_sql(file_name))
                    applied.append(file_name)
                raw_connection.commit()
            except Exception:
                raw_connection.rollback()
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


def run_storage_migration() -> None:
    applied = apply_postgres_storage_migrations()
    for file_name in applied:
        print(f"applied {file_name}")
