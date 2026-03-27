"""Write-focused PostgreSQL storage contracts for Backoffice Copilot."""

from .connection import build_postgres_engine, build_postgres_engine_from_env, get_postgres_url_from_env
from .repository import PkConflictPolicy, PostReviewWriteRepository, PostgresPostReviewWriteRepository
from .validators import (
    ALLOWED_BACKEND_DELIVERY_STATUSES,
    ALLOWED_REVIEW_RESULTS,
    ALLOWED_RUN_STATUSES,
    StorageValidationError,
    serialize_run_record,
    serialize_session_result_record,
    validate_run_record,
    validate_session_analysis_json,
    validate_session_result_record,
    validate_summary_text_json,
)

__all__ = [
    "ALLOWED_BACKEND_DELIVERY_STATUSES",
    "ALLOWED_REVIEW_RESULTS",
    "ALLOWED_RUN_STATUSES",
    "PkConflictPolicy",
    "PostReviewWriteRepository",
    "PostgresPostReviewWriteRepository",
    "StorageValidationError",
    "build_postgres_engine",
    "build_postgres_engine_from_env",
    "get_postgres_url_from_env",
    "serialize_run_record",
    "serialize_session_result_record",
    "validate_run_record",
    "validate_session_analysis_json",
    "validate_session_result_record",
    "validate_summary_text_json",
]
