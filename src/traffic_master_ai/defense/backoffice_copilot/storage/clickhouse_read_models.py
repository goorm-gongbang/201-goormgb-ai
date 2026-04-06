"""Read-model DTOs and validators for ClickHouse session rollup / candidate reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .validators import StorageValidationError


@dataclass(slots=True, frozen=True)
class ClickHouseSessionRollupQuery:
    """Minimal query contract for `defense_session_rollups`.

    This contract stays window-centric because current `match_id` stability is still weak.
    """

    window_start_ms: int
    window_end_ms: int
    session_ids: tuple[str, ...] = field(default_factory=tuple)
    limit: int | None = None


@dataclass(slots=True, frozen=True)
class ClickHousePostReviewCandidateQuery:
    """Minimal query contract for `defense_post_review_candidates_v1`."""

    window_start_ms: int
    window_end_ms: int
    session_ids: tuple[str, ...] = field(default_factory=tuple)
    limit: int | None = None


@dataclass(slots=True, frozen=True)
class ClickHouseMatchRollupQuery:
    """Minimal query contract for `defense_match_rollups` operational summaries."""

    window_start_ms: int
    window_end_ms: int
    match_ids: tuple[str, ...] = field(default_factory=tuple)
    limit: int | None = None


@dataclass(slots=True, frozen=True)
class ClickHouseSessionRollupRow:
    """Task 3 minimum row contract for `defense_session_rollups`."""

    window_start_ms: int
    window_end_ms: int
    session_id: str
    first_ts_ms: int
    last_ts_ms: int
    event_count: int
    latest_flow_state: str | None = None
    latest_action: str | None = None
    latest_risk_tier: str | None = None
    latest_reason_code: str | None = None
    latest_policy_version: str | None = None
    throttle_action_count: int = 0
    block_action_count: int = 0
    challenge_issue_count: int = 0
    challenge_verified_count: int = 0


@dataclass(slots=True, frozen=True)
class ClickHouseMatchRollupRow:
    """Task 3 minimum row contract for `defense_match_rollups`."""

    window_start_ms: int
    window_end_ms: int
    match_id: str | None = None
    session_count: int = 0
    event_count: int = 0
    block_action_count: int = 0
    throttle_action_count: int = 0
    challenge_issue_count: int = 0
    challenge_verified_count: int = 0
    latest_policy_version: str | None = None


@dataclass(slots=True, frozen=True)
class ClickHousePostReviewCandidateRow:
    """Task 3 minimum row contract for `defense_post_review_candidates_v1`."""

    window_start_ms: int
    window_end_ms: int
    session_id: str
    first_ts_ms: int
    last_ts_ms: int
    latest_action: str | None = None
    latest_risk_tier: str | None = None
    latest_reason_code: str | None = None
    latest_policy_version: str | None = None
    block_action_count: int = 0
    throttle_action_count: int = 0
    challenge_issue_count: int = 0
    challenge_verified_count: int = 0
    candidate_reason: str = ""


@dataclass(slots=True, frozen=True)
class BackofficeClickHouseReadModelInput:
    """Minimal Backoffice input surface sourced only from read models."""

    session_rollups: tuple[ClickHouseSessionRollupRow, ...] = field(default_factory=tuple)
    candidate_rows: tuple[ClickHousePostReviewCandidateRow, ...] = field(default_factory=tuple)


def validate_clickhouse_session_rollup_query(
    query: ClickHouseSessionRollupQuery,
) -> ClickHouseSessionRollupQuery:
    """Validate a windowed session-rollup read query."""

    _ensure_window(query.window_start_ms, query.window_end_ms)
    _ensure_session_ids(query.session_ids)
    _ensure_limit(query.limit)
    return query


def validate_clickhouse_post_review_candidate_query(
    query: ClickHousePostReviewCandidateQuery,
) -> ClickHousePostReviewCandidateQuery:
    """Validate a windowed candidate-view read query."""

    _ensure_window(query.window_start_ms, query.window_end_ms)
    _ensure_session_ids(query.session_ids)
    _ensure_limit(query.limit)
    return query


def validate_clickhouse_match_rollup_query(
    query: ClickHouseMatchRollupQuery,
) -> ClickHouseMatchRollupQuery:
    """Validate a windowed match-rollup read query."""

    _ensure_window(query.window_start_ms, query.window_end_ms)
    _ensure_match_ids(query.match_ids)
    _ensure_limit(query.limit)
    return query


def parse_clickhouse_session_rollup_row(
    row: Mapping[str, object],
) -> ClickHouseSessionRollupRow:
    """Parse one ClickHouse session-rollup row into the fixed DTO."""

    parsed = ClickHouseSessionRollupRow(
        window_start_ms=_ensure_int(row.get("window_start_ms"), "window_start_ms"),
        window_end_ms=_ensure_int(row.get("window_end_ms"), "window_end_ms"),
        session_id=_ensure_required_text(row.get("session_id"), "session_id"),
        first_ts_ms=_ensure_int(row.get("first_ts_ms"), "first_ts_ms"),
        last_ts_ms=_ensure_int(row.get("last_ts_ms"), "last_ts_ms"),
        event_count=_ensure_non_negative_int(row.get("event_count"), "event_count"),
        latest_flow_state=_ensure_nullable_text(row.get("latest_flow_state"), "latest_flow_state"),
        latest_action=_ensure_nullable_text(row.get("latest_action"), "latest_action"),
        latest_risk_tier=_ensure_nullable_text(
            row.get("latest_risk_tier"),
            "latest_risk_tier",
        ),
        latest_reason_code=_ensure_nullable_text(
            row.get("latest_reason_code"),
            "latest_reason_code",
        ),
        latest_policy_version=_ensure_nullable_text(
            row.get("latest_policy_version"),
            "latest_policy_version",
        ),
        throttle_action_count=_ensure_non_negative_int(
            row.get("throttle_action_count"),
            "throttle_action_count",
        ),
        block_action_count=_ensure_non_negative_int(
            row.get("block_action_count"),
            "block_action_count",
        ),
        challenge_issue_count=_ensure_non_negative_int(
            row.get("challenge_issue_count"),
            "challenge_issue_count",
        ),
        challenge_verified_count=_ensure_non_negative_int(
            row.get("challenge_verified_count"),
            "challenge_verified_count",
        ),
    )
    if parsed.first_ts_ms > parsed.last_ts_ms:
        raise StorageValidationError("first_ts_ms must be less than or equal to last_ts_ms.")
    return parsed


def parse_clickhouse_match_rollup_row(
    row: Mapping[str, object],
) -> ClickHouseMatchRollupRow:
    """Parse one ClickHouse match-rollup row into the fixed DTO."""

    return ClickHouseMatchRollupRow(
        window_start_ms=_ensure_int(row.get("window_start_ms"), "window_start_ms"),
        window_end_ms=_ensure_int(row.get("window_end_ms"), "window_end_ms"),
        match_id=_ensure_nullable_text(row.get("match_id"), "match_id"),
        session_count=_ensure_non_negative_int(row.get("session_count"), "session_count"),
        event_count=_ensure_non_negative_int(row.get("event_count"), "event_count"),
        block_action_count=_ensure_non_negative_int(
            row.get("block_action_count"),
            "block_action_count",
        ),
        throttle_action_count=_ensure_non_negative_int(
            row.get("throttle_action_count"),
            "throttle_action_count",
        ),
        challenge_issue_count=_ensure_non_negative_int(
            row.get("challenge_issue_count"),
            "challenge_issue_count",
        ),
        challenge_verified_count=_ensure_non_negative_int(
            row.get("challenge_verified_count"),
            "challenge_verified_count",
        ),
        latest_policy_version=_ensure_nullable_text(
            row.get("latest_policy_version"),
            "latest_policy_version",
        ),
    )


def parse_clickhouse_post_review_candidate_row(
    row: Mapping[str, object],
) -> ClickHousePostReviewCandidateRow:
    """Parse one candidate-view row into the fixed DTO."""

    parsed = ClickHousePostReviewCandidateRow(
        window_start_ms=_ensure_int(row.get("window_start_ms"), "window_start_ms"),
        window_end_ms=_ensure_int(row.get("window_end_ms"), "window_end_ms"),
        session_id=_ensure_required_text(row.get("session_id"), "session_id"),
        first_ts_ms=_ensure_int(row.get("first_ts_ms"), "first_ts_ms"),
        last_ts_ms=_ensure_int(row.get("last_ts_ms"), "last_ts_ms"),
        latest_action=_ensure_nullable_text(row.get("latest_action"), "latest_action"),
        latest_risk_tier=_ensure_nullable_text(
            row.get("latest_risk_tier"),
            "latest_risk_tier",
        ),
        latest_reason_code=_ensure_nullable_text(
            row.get("latest_reason_code"),
            "latest_reason_code",
        ),
        latest_policy_version=_ensure_nullable_text(
            row.get("latest_policy_version"),
            "latest_policy_version",
        ),
        block_action_count=_ensure_non_negative_int(
            row.get("block_action_count"),
            "block_action_count",
        ),
        throttle_action_count=_ensure_non_negative_int(
            row.get("throttle_action_count"),
            "throttle_action_count",
        ),
        challenge_issue_count=_ensure_non_negative_int(
            row.get("challenge_issue_count"),
            "challenge_issue_count",
        ),
        challenge_verified_count=_ensure_non_negative_int(
            row.get("challenge_verified_count"),
            "challenge_verified_count",
        ),
        candidate_reason=_ensure_required_text(row.get("candidate_reason"), "candidate_reason"),
    )
    if parsed.first_ts_ms > parsed.last_ts_ms:
        raise StorageValidationError("first_ts_ms must be less than or equal to last_ts_ms.")
    return parsed


def serialize_clickhouse_session_rollup_query(
    query: ClickHouseSessionRollupQuery,
) -> dict[str, object]:
    """Validate and serialize one session-rollup query."""

    validated = validate_clickhouse_session_rollup_query(query)
    return {
        "window_start_ms": validated.window_start_ms,
        "window_end_ms": validated.window_end_ms,
        "session_ids": validated.session_ids,
        "limit": validated.limit,
    }


def serialize_clickhouse_match_rollup_query(
    query: ClickHouseMatchRollupQuery,
) -> dict[str, object]:
    """Validate and serialize one match-rollup query."""

    validated = validate_clickhouse_match_rollup_query(query)
    return {
        "window_start_ms": validated.window_start_ms,
        "window_end_ms": validated.window_end_ms,
        "match_ids": validated.match_ids,
        "limit": validated.limit,
    }


def serialize_clickhouse_post_review_candidate_query(
    query: ClickHousePostReviewCandidateQuery,
) -> dict[str, object]:
    """Validate and serialize one candidate-view query."""

    validated = validate_clickhouse_post_review_candidate_query(query)
    return {
        "window_start_ms": validated.window_start_ms,
        "window_end_ms": validated.window_end_ms,
        "session_ids": validated.session_ids,
        "limit": validated.limit,
    }


def parse_clickhouse_session_rollup_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[ClickHouseSessionRollupRow, ...]:
    """Parse a batch of session-rollup rows."""

    return tuple(parse_clickhouse_session_rollup_row(row) for row in rows)


def parse_clickhouse_match_rollup_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[ClickHouseMatchRollupRow, ...]:
    """Parse a batch of match-rollup rows."""

    return tuple(parse_clickhouse_match_rollup_row(row) for row in rows)


def parse_clickhouse_post_review_candidate_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[ClickHousePostReviewCandidateRow, ...]:
    """Parse a batch of candidate-view rows."""

    return tuple(parse_clickhouse_post_review_candidate_row(row) for row in rows)


def _ensure_window(window_start_ms: object, window_end_ms: object) -> None:
    start = _ensure_int(window_start_ms, "window_start_ms")
    end = _ensure_int(window_end_ms, "window_end_ms")
    if start > end:
        raise StorageValidationError("window_start_ms must be less than or equal to window_end_ms.")


def _ensure_session_ids(session_ids: Sequence[str]) -> tuple[str, ...]:
    validated: list[str] = []
    for index, value in enumerate(session_ids):
        validated.append(_ensure_required_text(value, f"session_ids[{index}]"))
    return tuple(validated)


def _ensure_match_ids(match_ids: Sequence[str]) -> tuple[str, ...]:
    validated: list[str] = []
    for index, value in enumerate(match_ids):
        validated.append(_ensure_required_text(value, f"match_ids[{index}]"))
    return tuple(validated)


def _ensure_limit(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StorageValidationError("limit must be a non-negative int or None.")
    return value


def _ensure_int(value: object, field_name: str) -> int:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("-"):
            numeric = stripped[1:]
        else:
            numeric = stripped
        if numeric.isdigit():
            return int(stripped)
    if not isinstance(value, int) or isinstance(value, bool):
        raise StorageValidationError(f"{field_name} must be an int.")
    return value


def _ensure_non_negative_int(value: object, field_name: str) -> int:
    validated = _ensure_int(value, field_name)
    if validated < 0:
        raise StorageValidationError(f"{field_name} must be non-negative.")
    return validated


def _ensure_required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise StorageValidationError(f"{field_name} must be a non-empty string.")
    return value


def _ensure_nullable_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_required_text(value, field_name)
