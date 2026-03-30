"""Write-only repository for Backoffice Copilot PostgreSQL persistence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, Sequence

from ..core.models import PostReviewRunRecord, PostReviewSessionResultRecord
from .validators import serialize_run_record, serialize_session_result_record

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection, Engine
else:
    Connection = Any
    Engine = Any

_INSERT_RUN_SQL = """
INSERT INTO post_review_runs (
    match_id,
    window_start_ms,
    window_end_ms,
    candidate_count,
    suspicious_count,
    summary_text_json,
    status,
    created_at,
    updated_at
) VALUES (
    :match_id,
    :window_start_ms,
    :window_end_ms,
    :candidate_count,
    :suspicious_count,
    :summary_text_json,
    :status,
    :created_at,
    :updated_at
)
"""

_UPSERT_RUN_SQL = """
INSERT INTO post_review_runs (
    match_id,
    window_start_ms,
    window_end_ms,
    candidate_count,
    suspicious_count,
    summary_text_json,
    status,
    created_at,
    updated_at
) VALUES (
    :match_id,
    :window_start_ms,
    :window_end_ms,
    :candidate_count,
    :suspicious_count,
    :summary_text_json,
    :status,
    :created_at,
    :updated_at
)
ON CONFLICT (match_id) DO UPDATE SET
    window_start_ms = EXCLUDED.window_start_ms,
    window_end_ms = EXCLUDED.window_end_ms,
    candidate_count = EXCLUDED.candidate_count,
    suspicious_count = EXCLUDED.suspicious_count,
    summary_text_json = EXCLUDED.summary_text_json,
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at
"""

_INSERT_SESSION_RESULT_SQL = """
INSERT INTO post_review_session_results (
    match_id,
    session_id,
    review_result,
    evidence_summary,
    session_analysis_json,
    backend_delivery_status,
    created_at,
    updated_at
) VALUES (
    :match_id,
    :session_id,
    :review_result,
    :evidence_summary,
    :session_analysis_json,
    :backend_delivery_status,
    :created_at,
    :updated_at
)
"""

_UPSERT_SESSION_RESULT_SQL = """
INSERT INTO post_review_session_results (
    match_id,
    session_id,
    review_result,
    evidence_summary,
    session_analysis_json,
    backend_delivery_status,
    created_at,
    updated_at
) VALUES (
    :match_id,
    :session_id,
    :review_result,
    :evidence_summary,
    :session_analysis_json,
    :backend_delivery_status,
    :created_at,
    :updated_at
)
ON CONFLICT (match_id, session_id) DO UPDATE SET
    review_result = EXCLUDED.review_result,
    evidence_summary = EXCLUDED.evidence_summary,
    session_analysis_json = EXCLUDED.session_analysis_json,
    backend_delivery_status = EXCLUDED.backend_delivery_status,
    updated_at = EXCLUDED.updated_at
"""


class PkConflictPolicy(str, Enum):
    """Explicit PK conflict policy connection point."""

    FAIL_FAST = "fail_fast"
    UPSERT = "upsert"


class PostReviewWriteRepository(Protocol):
    """Write-focused repository contract for Task 8 persistence."""

    def save_run(self, run_record: PostReviewRunRecord) -> None:
        """Persist one run-level record."""

    def save_session_results(
        self,
        session_records: Sequence[PostReviewSessionResultRecord],
    ) -> None:
        """Persist session-level records."""

    def save_bundle(
        self,
        run_record: PostReviewRunRecord,
        session_records: Sequence[PostReviewSessionResultRecord],
    ) -> None:
        """Persist run and session records in one transaction."""


@dataclass(slots=True)
class PostgresPostReviewWriteRepository:
    """SQLAlchemy Core based PostgreSQL write adapter."""

    engine: Engine
    conflict_policy: PkConflictPolicy

    def save_run(self, run_record: PostReviewRunRecord) -> None:
        with self.engine.begin() as connection:
            self._save_run(connection, run_record)

    def save_session_results(
        self,
        session_records: Sequence[PostReviewSessionResultRecord],
    ) -> None:
        with self.engine.begin() as connection:
            self._save_session_results(connection, session_records)

    def save_bundle(
        self,
        run_record: PostReviewRunRecord,
        session_records: Sequence[PostReviewSessionResultRecord],
    ) -> None:
        with self.engine.begin() as connection:
            self._save_run(connection, run_record)
            self._save_session_results(connection, session_records)

    def _save_run(self, connection: Connection, run_record: PostReviewRunRecord) -> None:
        params = serialize_run_record(run_record)
        self._execute(connection, self._run_sql, params)

    def _save_session_results(
        self,
        connection: Connection,
        session_records: Sequence[PostReviewSessionResultRecord],
    ) -> None:
        for record in session_records:
            params = serialize_session_result_record(record)
            self._execute(connection, self._session_result_sql, params)

    @property
    def _run_sql(self) -> str:
        if self.conflict_policy is PkConflictPolicy.FAIL_FAST:
            return _INSERT_RUN_SQL
        return _UPSERT_RUN_SQL

    @property
    def _session_result_sql(self) -> str:
        if self.conflict_policy is PkConflictPolicy.FAIL_FAST:
            return _INSERT_SESSION_RESULT_SQL
        return _UPSERT_SESSION_RESULT_SQL

    def _execute(
        self,
        connection: Connection,
        sql_text: str,
        params: dict[str, object],
    ) -> None:
        try:
            from sqlalchemy import text
        except ImportError as exc:
            raise RuntimeError(
                "sqlalchemy is required to execute Backoffice Copilot PostgreSQL write queries."
            ) from exc

        connection.execute(text(sql_text), params)
