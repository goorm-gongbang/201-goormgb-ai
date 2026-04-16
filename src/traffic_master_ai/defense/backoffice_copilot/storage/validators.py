"""Column-level validators for Backoffice Copilot PostgreSQL writes."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Mapping, Sequence

from ..core.models import PostReviewRunRecord, PostReviewSessionResultRecord, SessionAnalysis

ALLOWED_RUN_STATUSES = frozenset({"SUCCESS", "PARTIAL_SUCCESS", "FAILED"})
ALLOWED_REVIEW_RESULTS = frozenset({"NORMAL", "SUSPICIOUS"})
ALLOWED_BACKEND_DELIVERY_STATUSES = frozenset({"PENDING", "SENT", "FAILED"})

_SESSION_ANALYSIS_REQUIRED_FIELDS = (
    "session_id",
    "latest_flow_state",
    "latest_action",
    "latest_tier",
    "terminal_outcome",
    "seen_t1",
    "seen_t2",
    "vqa_fail_count",
    "throttle_event_count",
    "suspicious_signals",
    "timeline_summary",
    "needs_raw_fallback",
)


class StorageValidationError(ValueError):
    """Raised when a record is incompatible with the fixed storage contract."""


def _ensure_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise StorageValidationError(f"{field_name} must be a non-empty string.")
    return value


def _ensure_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise StorageValidationError(f"{field_name} must be an int.")
    return value


def _ensure_datetime(value: object, field_name: str) -> datetime:
    """Require a non-None datetime — used in serializers where the DB column is NOT NULL."""
    if not isinstance(value, datetime):
        raise StorageValidationError(
            f"{field_name} must be a datetime before persistence (got {type(value).__name__!r}). "
            "The DB column is NOT NULL — set created_at/updated_at before calling serialize."
        )
    return value


def _ensure_datetime_or_none(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise StorageValidationError(f"{field_name} must be a datetime or None.")
    return value


def _ensure_allowed(value: str, field_name: str, allowed: frozenset[str]) -> str:
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise StorageValidationError(f"{field_name} must be one of {{{allowed_values}}}.")
    return value


def validate_summary_text_json(summary_text_json: Sequence[object]) -> list[str]:
    """Validate the run-level summary JSON payload."""

    if len(summary_text_json) != 3:
        raise StorageValidationError("summary_text_json must contain exactly 3 items.")

    validated_items: list[str] = []
    for index, item in enumerate(summary_text_json):
        if not isinstance(item, str) or not item:
            raise StorageValidationError(f"summary_text_json[{index}] must be a non-empty string.")
        validated_items.append(item)
    return validated_items


def validate_session_analysis_json(
    session_analysis_json: SessionAnalysis | Mapping[str, object],
) -> dict[str, object]:
    """Validate the minimal SessionAnalysis-compatible JSON payload."""

    if isinstance(session_analysis_json, SessionAnalysis):
        payload = asdict(session_analysis_json)
    else:
        payload = dict(session_analysis_json)

    missing_fields = [
        field_name for field_name in _SESSION_ANALYSIS_REQUIRED_FIELDS if field_name not in payload
    ]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise StorageValidationError(f"session_analysis_json is missing required fields: {missing}.")

    _ensure_str(payload["session_id"], "session_analysis_json.session_id")
    _ensure_str(payload["latest_flow_state"], "session_analysis_json.latest_flow_state")
    _ensure_str(payload["latest_action"], "session_analysis_json.latest_action")
    _ensure_str(payload["latest_tier"], "session_analysis_json.latest_tier")
    _ensure_str(payload["terminal_outcome"], "session_analysis_json.terminal_outcome")

    for field_name in ("seen_t1", "seen_t2", "needs_raw_fallback"):
        if not isinstance(payload[field_name], bool):
            raise StorageValidationError(f"session_analysis_json.{field_name} must be a bool.")

    for field_name in ("vqa_fail_count", "throttle_event_count"):
        _ensure_int(payload[field_name], f"session_analysis_json.{field_name}")

    for field_name in ("suspicious_signals", "timeline_summary"):
        value = payload[field_name]
        if not isinstance(value, list):
            raise StorageValidationError(f"session_analysis_json.{field_name} must be a list.")
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise StorageValidationError(
                    f"session_analysis_json.{field_name}[{index}] must be a string."
                )

    return payload


def validate_run_record(record: PostReviewRunRecord) -> PostReviewRunRecord:
    """Validate a run-level record before persistence."""

    _ensure_str(record.match_id, "match_id")
    _ensure_int(record.window_start_ms, "window_start_ms")
    _ensure_int(record.window_end_ms, "window_end_ms")
    _ensure_int(record.candidate_count, "candidate_count")
    _ensure_int(record.suspicious_count, "suspicious_count")
    if record.candidate_count < record.suspicious_count:
        raise StorageValidationError("candidate_count must be greater than or equal to suspicious_count.")
    _ensure_allowed(record.status, "status", ALLOWED_RUN_STATUSES)
    validate_summary_text_json(record.summary_text_json)
    _ensure_datetime_or_none(record.created_at, "created_at")
    _ensure_datetime_or_none(record.updated_at, "updated_at")
    return record


def validate_session_result_record(
    record: PostReviewSessionResultRecord,
) -> PostReviewSessionResultRecord:
    """Validate a session-level result record before persistence."""

    _ensure_str(record.match_id, "match_id")
    _ensure_str(record.session_id, "session_id")
    _ensure_allowed(record.review_result, "review_result", ALLOWED_REVIEW_RESULTS)
    _ensure_str(record.evidence_summary, "evidence_summary")
    _ensure_allowed(
        record.backend_delivery_status,
        "backend_delivery_status",
        ALLOWED_BACKEND_DELIVERY_STATUSES,
    )
    validate_session_analysis_json(record.session_analysis_json)
    _ensure_datetime_or_none(record.created_at, "created_at")
    _ensure_datetime_or_none(record.updated_at, "updated_at")
    return record


def serialize_run_record(record: PostReviewRunRecord) -> dict[str, object]:
    """Validate and convert a run record into SQL parameter payload.

    JSONB columns (summary_text_json) are serialized to JSON strings so that
    psycopg / psycopg2 binds them as ``text`` and PostgreSQL casts to ``jsonb``.
    Passing a raw Python list would cause psycopg to infer ``text[]`` (PostgreSQL
    array), which raises DatatypeMismatch against a ``jsonb`` column.
    """

    validate_run_record(record)
    return {
        "match_id": record.match_id,
        "window_start_ms": record.window_start_ms,
        "window_end_ms": record.window_end_ms,
        "candidate_count": record.candidate_count,
        "suspicious_count": record.suspicious_count,
        "summary_text_json": json.dumps(list(record.summary_text_json), ensure_ascii=False),
        "status": record.status,
        "created_at": _ensure_datetime(record.created_at, "created_at"),
        "updated_at": _ensure_datetime(record.updated_at, "updated_at"),
    }


def serialize_session_result_record(record: PostReviewSessionResultRecord) -> dict[str, object]:
    """Validate and convert a session result record into SQL parameter payload.

    JSONB columns (session_analysis_json) are serialized to JSON strings for the
    same reason as serialize_run_record: psycopg infers ``text`` from a JSON string,
    while a Python dict might be adapted differently depending on driver version or
    registered adapters. Explicit json.dumps makes the binding driver-independent.
    """

    validate_session_result_record(record)
    return {
        "match_id": record.match_id,
        "session_id": record.session_id,
        "review_result": record.review_result,
        "evidence_summary": record.evidence_summary,
        "session_analysis_json": json.dumps(
            validate_session_analysis_json(record.session_analysis_json),
            ensure_ascii=False,
        ),
        "backend_delivery_status": record.backend_delivery_status,
        "created_at": _ensure_datetime(record.created_at, "created_at"),
        "updated_at": _ensure_datetime(record.updated_at, "updated_at"),
    }
