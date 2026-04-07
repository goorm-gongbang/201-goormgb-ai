"""ClickHouse read-model repository skeletons for Backoffice Copilot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .clickhouse_connection import (
    DEFAULT_CLICKHOUSE_CANDIDATE_VIEW,
    DEFAULT_CLICKHOUSE_MATCH_ROLLUP_TABLE,
    DEFAULT_CLICKHOUSE_SESSION_ROLLUP_TABLE,
    ClickHouseReadModelConfig,
    ClickHouseSelectClient,
)
from .clickhouse_read_models import (
    BackofficeClickHouseReadModelInput,
    ClickHouseMatchRollupQuery,
    ClickHouseMatchRollupRow,
    ClickHousePostReviewCandidateQuery,
    ClickHousePostReviewCandidateRow,
    ClickHouseSessionRollupQuery,
    ClickHouseSessionRollupRow,
    parse_clickhouse_match_rollup_rows,
    parse_clickhouse_post_review_candidate_rows,
    parse_clickhouse_session_rollup_rows,
    serialize_clickhouse_match_rollup_query,
    serialize_clickhouse_post_review_candidate_query,
    serialize_clickhouse_session_rollup_query,
)

_SESSION_ROLLUP_COLUMNS = (
    "window_start_ms",
    "window_end_ms",
    "session_id",
    "first_ts_ms",
    "last_ts_ms",
    "event_count",
    "latest_flow_state",
    "latest_action",
    "latest_risk_tier",
    "latest_reason_code",
    "latest_policy_version",
    "throttle_action_count",
    "block_action_count",
    "challenge_issue_count",
    "challenge_verified_count",
)

_CANDIDATE_COLUMNS = (
    "window_start_ms",
    "window_end_ms",
    "session_id",
    "first_ts_ms",
    "last_ts_ms",
    "latest_action",
    "latest_risk_tier",
    "latest_reason_code",
    "latest_policy_version",
    "block_action_count",
    "throttle_action_count",
    "challenge_issue_count",
    "challenge_verified_count",
    "candidate_reason",
)

_MATCH_ROLLUP_COLUMNS = (
    "window_start_ms",
    "window_end_ms",
    "match_id",
    "session_count",
    "event_count",
    "block_action_count",
    "throttle_action_count",
    "challenge_issue_count",
    "challenge_verified_count",
    "latest_policy_version",
)


class ClickHouseSessionRollupReadRepository(Protocol):
    """Read-focused contract for session-rollup access only."""

    def read_rollups(
        self,
        query: ClickHouseSessionRollupQuery,
    ) -> tuple[ClickHouseSessionRollupRow, ...]:
        """Load windowed session-rollup rows for Backoffice input."""


class ClickHousePostReviewCandidateReadRepository(Protocol):
    """Read-focused contract for candidate-view access only."""

    def read_candidates(
        self,
        query: ClickHousePostReviewCandidateQuery,
    ) -> tuple[ClickHousePostReviewCandidateRow, ...]:
        """Load windowed candidate-view rows for Backoffice input."""


class ClickHouseMatchRollupReadRepository(Protocol):
    """Read-focused contract for match-rollup access only."""

    def read_match_rollups(
        self,
        query: ClickHouseMatchRollupQuery,
    ) -> tuple[ClickHouseMatchRollupRow, ...]:
        """Load windowed match-rollup rows for ops summaries."""


@dataclass(slots=True)
class ClickHouseSessionRollupReaderRepository:
    """Thin repository that only issues session-rollup reads.

    Explicit gaps kept for later tasks:
    - actual ClickHouse driver/result cursor integration
    - rollup materialization or MV creation
    - candidate scoring / final review logic
    - raw-fact fallback or match reconstruction
    """

    client: ClickHouseSelectClient
    config: ClickHouseReadModelConfig = field(default_factory=ClickHouseReadModelConfig)

    def read_rollups(
        self,
        query: ClickHouseSessionRollupQuery,
    ) -> tuple[ClickHouseSessionRollupRow, ...]:
        params = serialize_clickhouse_session_rollup_query(query)
        rows = self.client.query(self.select_sql_for(query), params)
        return parse_clickhouse_session_rollup_rows(rows)

    def select_sql_for(self, query: ClickHouseSessionRollupQuery) -> str:
        sql = (
            f"SELECT {', '.join(_SESSION_ROLLUP_COLUMNS)} "
            f"FROM {self.config.session_rollup_table} "
            "WHERE window_start_ms = :window_start_ms "
            "AND window_end_ms = :window_end_ms"
        )
        if query.session_ids:
            sql += " AND session_id IN :session_ids"
        sql += " ORDER BY first_ts_ms ASC, session_id ASC"
        if query.limit is not None:
            sql += " LIMIT :limit"
        return sql


@dataclass(slots=True)
class ClickHousePostReviewCandidateReaderRepository:
    """Thin repository that only issues candidate-view reads."""

    client: ClickHouseSelectClient
    config: ClickHouseReadModelConfig = field(default_factory=ClickHouseReadModelConfig)

    def read_candidates(
        self,
        query: ClickHousePostReviewCandidateQuery,
    ) -> tuple[ClickHousePostReviewCandidateRow, ...]:
        params = serialize_clickhouse_post_review_candidate_query(query)
        rows = self.client.query(self.select_sql_for(query), params)
        return parse_clickhouse_post_review_candidate_rows(rows)

    def select_sql_for(self, query: ClickHousePostReviewCandidateQuery) -> str:
        sql = (
            f"SELECT {', '.join(_CANDIDATE_COLUMNS)} "
            f"FROM {self.config.candidate_view_name} "
            "WHERE window_start_ms = :window_start_ms "
            "AND window_end_ms = :window_end_ms"
        )
        if query.session_ids:
            sql += " AND session_id IN :session_ids"
        sql += " ORDER BY first_ts_ms ASC, session_id ASC"
        if query.limit is not None:
            sql += " LIMIT :limit"
        return sql


@dataclass(slots=True)
class ClickHouseMatchRollupReaderRepository:
    """Thin repository that only issues match-rollup reads."""

    client: ClickHouseSelectClient
    config: ClickHouseReadModelConfig = field(default_factory=ClickHouseReadModelConfig)

    def read_match_rollups(
        self,
        query: ClickHouseMatchRollupQuery,
    ) -> tuple[ClickHouseMatchRollupRow, ...]:
        params = serialize_clickhouse_match_rollup_query(query)
        rows = self.client.query(self.select_sql_for(query), params)
        return parse_clickhouse_match_rollup_rows(rows)

    def select_sql_for(self, query: ClickHouseMatchRollupQuery) -> str:
        sql = (
            f"SELECT {', '.join(_MATCH_ROLLUP_COLUMNS)} "
            f"FROM {self.config.match_rollup_table} "
            "WHERE window_start_ms = :window_start_ms "
            "AND window_end_ms = :window_end_ms"
        )
        if query.match_ids:
            sql += " AND match_id IN :match_ids"
        sql += " ORDER BY match_id ASC"
        if query.limit is not None:
            sql += " LIMIT :limit"
        return sql


def load_backoffice_clickhouse_read_model_input(
    *,
    window_start_ms: int,
    window_end_ms: int,
    session_rollup_repository: ClickHouseSessionRollupReadRepository,
    candidate_repository: ClickHousePostReviewCandidateReadRepository,
    limit: int | None = None,
) -> BackofficeClickHouseReadModelInput:
    """Load the minimal Backoffice input bundle from read models only."""

    session_rollups = session_rollup_repository.read_rollups(
        ClickHouseSessionRollupQuery(
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            limit=limit,
        )
    )
    candidate_rows = candidate_repository.read_candidates(
        ClickHousePostReviewCandidateQuery(
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            limit=limit,
        )
    )
    return BackofficeClickHouseReadModelInput(
        session_rollups=session_rollups,
        candidate_rows=candidate_rows,
    )


def build_clickhouse_session_rollup_reader_repository(
    client: ClickHouseSelectClient,
    *,
    table_name: str = DEFAULT_CLICKHOUSE_SESSION_ROLLUP_TABLE,
) -> ClickHouseSessionRollupReaderRepository:
    """Build the session-rollup reader skeleton."""

    return ClickHouseSessionRollupReaderRepository(
        client=client,
        config=ClickHouseReadModelConfig(session_rollup_table=table_name),
    )


def build_clickhouse_post_review_candidate_reader_repository(
    client: ClickHouseSelectClient,
    *,
    view_name: str = DEFAULT_CLICKHOUSE_CANDIDATE_VIEW,
) -> ClickHousePostReviewCandidateReaderRepository:
    """Build the candidate-view reader skeleton."""

    return ClickHousePostReviewCandidateReaderRepository(
        client=client,
        config=ClickHouseReadModelConfig(candidate_view_name=view_name),
    )


def build_clickhouse_match_rollup_reader_repository(
    client: ClickHouseSelectClient,
    *,
    table_name: str = DEFAULT_CLICKHOUSE_MATCH_ROLLUP_TABLE,
) -> ClickHouseMatchRollupReaderRepository:
    """Build the match-rollup reader."""

    return ClickHouseMatchRollupReaderRepository(
        client=client,
        config=ClickHouseReadModelConfig(match_rollup_table=table_name),
    )
