from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from ..storage_env import load_postgres_storage_config_from_env

DATABASE_URL = load_postgres_storage_config_from_env(required=False).url

# Create engine only if URL is provided
engine = create_engine(DATABASE_URL) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    if not SessionLocal:
        return None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
