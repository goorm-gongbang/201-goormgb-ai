"""Minimal PostgreSQL connection entry points for Backoffice Copilot storage."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
else:
    Engine = Any


def get_postgres_url_from_env() -> str:
    """Return the configured PostgreSQL URL or raise when missing."""

    pg_url = os.getenv("TM_PG_URL", "").strip()
    if not pg_url:
        raise ValueError("TM_PG_URL must be set to use Backoffice Copilot PostgreSQL storage.")
    return pg_url


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
