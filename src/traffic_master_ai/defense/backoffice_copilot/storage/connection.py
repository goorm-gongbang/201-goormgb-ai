"""Minimal PostgreSQL connection entry points for Backoffice Copilot storage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...storage_env import load_postgres_storage_config_from_env

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
else:
    Engine = Any


def get_postgres_url_from_env() -> str:
    """Return the configured PostgreSQL URL or raise when missing."""

    return load_postgres_storage_config_from_env(required=True).url or ""


def build_postgres_engine(pg_url: str) -> Engine:
    """Build a SQLAlchemy engine for PostgreSQL write operations."""

    try:
        from sqlalchemy import create_engine
    except ImportError as exc:
        raise RuntimeError(
            "sqlalchemy is required to build Backoffice Copilot PostgreSQL storage engine."
        ) from exc

    return create_engine(pg_url, future=True, pool_pre_ping=True)


def build_postgres_engine_from_env() -> Engine:
    """Build a PostgreSQL engine using the shared TM_PG_URL convention."""

    return build_postgres_engine(get_postgres_url_from_env())
