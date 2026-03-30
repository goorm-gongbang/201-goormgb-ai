"""Suspicious-only backend payload helpers for Task 8."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Callable, Mapping

from ..core.issues import PipelineIssue
from ..core.models import (
    BackendCandidate,
    BackendRequest,
    BackendResponse,
    PostReviewSessionResultRecord,
)

type BackendRequestAdapter = Callable[[BackendRequest], object]


class BackendAdapterError(ValueError):
    """Raised when a backend adapter response violates the fixed contract."""


@dataclass(slots=True, frozen=True)
class BackendDeliveryResult:
    """Backend delivery side effects plus traceable warnings."""

    backend_request: BackendRequest | None
    backend_response: BackendResponse | None
    session_rows: tuple[PostReviewSessionResultRecord, ...]
    warnings: tuple[PipelineIssue, ...]


def build_backend_request(
    *,
    match_id: str,
    window_start_ms: int,
    window_end_ms: int,
    session_rows: tuple[PostReviewSessionResultRecord, ...] | list[PostReviewSessionResultRecord],
) -> BackendRequest | None:
    """Build a suspicious-only backend payload from persisted session rows."""

    suspicious_rows = [row for row in session_rows if row.review_result == "SUSPICIOUS"]
    if not suspicious_rows:
        return None

    return BackendRequest(
        match_id=match_id,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        suspicious_count=len(suspicious_rows),
        candidates=[
            BackendCandidate(
                session_id=row.session_id,
                review_result=row.review_result,
                reason_summary=row.evidence_summary,
            )
            for row in suspicious_rows
        ],
    )


def deliver_backend_request(
    *,
    backend_request: BackendRequest | None,
    session_rows: tuple[PostReviewSessionResultRecord, ...] | list[PostReviewSessionResultRecord],
    backend_adapter: BackendRequestAdapter | None = None,
    now: datetime | None = None,
) -> BackendDeliveryResult:
    """Call the backend adapter boundary and reflect delivery status on session rows."""

    rows = tuple(session_rows)
    if backend_request is None:
        return BackendDeliveryResult(
            backend_request=None,
            backend_response=None,
            session_rows=rows,
            warnings=(),
        )

    if backend_adapter is None:
        updated_rows = _update_suspicious_delivery_status(rows, "FAILED", now=now)
        return BackendDeliveryResult(
            backend_request=backend_request,
            backend_response=None,
            session_rows=updated_rows,
            warnings=(
                PipelineIssue(
                    code="backend_delivery_failed",
                    message="Backend delivery was skipped because no adapter was configured.",
                    context={
                        "match_id": backend_request.match_id,
                        "fallback_reason": "adapter_missing",
                    },
                ),
            ),
        )

    try:
        raw_response = backend_adapter(backend_request)
        backend_response = parse_backend_response(
            raw_response,
            expected_match_id=backend_request.match_id,
        )
    except Exception as exc:
        updated_rows = _update_suspicious_delivery_status(rows, "FAILED", now=now)
        return BackendDeliveryResult(
            backend_request=backend_request,
            backend_response=None,
            session_rows=updated_rows,
            warnings=(
                PipelineIssue(
                    code="backend_delivery_failed",
                    message="Backend adapter call failed and suspicious session rows were marked FAILED.",
                    context={
                        "match_id": backend_request.match_id,
                        "failure_reason": _classify_backend_failure(exc),
                    },
                ),
            ),
        )

    delivery_status = _resolve_delivery_status(backend_request, backend_response)
    updated_rows = _update_suspicious_delivery_status(rows, delivery_status, now=now)
    warnings: tuple[PipelineIssue, ...] = ()
    if delivery_status == "FAILED":
        warnings = (
            PipelineIssue(
                code="backend_delivery_failed",
                message="Backend adapter returned a non-accepting response and suspicious session rows were marked FAILED.",
                context={
                    "match_id": backend_request.match_id,
                    "accepted_count": backend_response.accepted_count,
                    "rejected_count": backend_response.rejected_count,
                    "status": backend_response.status,
                },
            ),
        )
    return BackendDeliveryResult(
        backend_request=backend_request,
        backend_response=backend_response,
        session_rows=updated_rows,
        warnings=warnings,
    )


def parse_backend_response(
    raw_response: object,
    *,
    expected_match_id: str,
) -> BackendResponse:
    """Parse backend adapter output into the fixed DTO."""

    if isinstance(raw_response, BackendResponse):
        response = raw_response
    elif isinstance(raw_response, str):
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise BackendAdapterError("Backend response text must be valid JSON.") from exc
        response = parse_backend_response(parsed, expected_match_id=expected_match_id)
    elif isinstance(raw_response, Mapping):
        try:
            response = BackendResponse(
                match_id=str(raw_response["match_id"]),
                accepted_count=int(raw_response["accepted_count"]),
                rejected_count=int(raw_response["rejected_count"]),
                status=str(raw_response["status"]),
                received_at=str(raw_response["received_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BackendAdapterError("Backend response mapping is missing required fields.") from exc
    else:
        raise BackendAdapterError("Backend response must be a mapping, JSON string, or BackendResponse.")

    if response.match_id != expected_match_id:
        raise BackendAdapterError("Backend response match_id must match the request match_id.")
    if response.accepted_count < 0 or response.rejected_count < 0:
        raise BackendAdapterError("Backend response counts must be non-negative.")
    if not response.status:
        raise BackendAdapterError("Backend response status must be non-empty.")
    if not response.received_at:
        raise BackendAdapterError("Backend response received_at must be non-empty.")
    return response


def _resolve_delivery_status(
    backend_request: BackendRequest,
    backend_response: BackendResponse,
) -> str:
    if (
        backend_response.accepted_count == backend_request.suspicious_count
        and backend_response.rejected_count == 0
    ):
        return "SENT"
    return "FAILED"


def _update_suspicious_delivery_status(
    session_rows: tuple[PostReviewSessionResultRecord, ...],
    backend_delivery_status: str,
    *,
    now: datetime | None = None,
) -> tuple[PostReviewSessionResultRecord, ...]:
    timestamp = now or datetime.now(UTC)
    updated_rows: list[PostReviewSessionResultRecord] = []
    for row in session_rows:
        if row.review_result != "SUSPICIOUS":
            updated_rows.append(row)
            continue
        updated_rows.append(
            replace(
                row,
                backend_delivery_status=backend_delivery_status,
                updated_at=timestamp,
            )
        )
    return tuple(updated_rows)


def _classify_backend_failure(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "adapter_timeout"
    if isinstance(exc, BackendAdapterError):
        return f"response_validation_failed:{exc}"
    return f"adapter_error:{type(exc).__name__}"


__all__ = [
    "BackendAdapterError",
    "BackendDeliveryResult",
    "BackendRequestAdapter",
    "build_backend_request",
    "deliver_backend_request",
]
