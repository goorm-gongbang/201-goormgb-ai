"""Restricted decision_audit fallback helpers for Task 5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from ..core.models import DefenseAuditEventRow
from ..ingest.loader import parse_defense_audit_event_row

type DecisionAuditRawRow = DefenseAuditEventRow | Mapping[str, object]
type DecisionAuditRowProvider = Callable[[str, int, int, int], Sequence[DecisionAuditRawRow]]

DEFAULT_RAW_FALLBACK_LIMIT = 50


@dataclass(slots=True, frozen=True)
class RawFallbackQuery:
    """Restricted raw fallback query boundary."""

    session_id: str
    window_start_ms: int
    window_end_ms: int
    limit: int = DEFAULT_RAW_FALLBACK_LIMIT

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ValueError("session_id is required for raw fallback.")
        if self.window_start_ms > self.window_end_ms:
            raise ValueError("window_start_ms must be <= window_end_ms.")
        if self.limit <= 0:
            raise ValueError("limit must be positive.")


def fetch_limited_decision_audit_rows(
    query: RawFallbackQuery,
    row_provider: DecisionAuditRowProvider | None,
) -> tuple[DefenseAuditEventRow, ...]:
    """Fetch only session-scoped, time-window-limited raw fallback rows."""

    if row_provider is None:
        return ()

    candidate_rows = row_provider(
        query.session_id,
        query.window_start_ms,
        query.window_end_ms,
        query.limit,
    )
    rows: list[DefenseAuditEventRow] = []
    for candidate in candidate_rows:
        row = _normalize_row(candidate)
        if row.session_id != query.session_id:
            continue
        if row.ts_ms < query.window_start_ms or row.ts_ms > query.window_end_ms:
            continue
        rows.append(row)
        if len(rows) >= query.limit:
            break
    return tuple(rows)


def _normalize_row(candidate: DecisionAuditRawRow) -> DefenseAuditEventRow:
    if isinstance(candidate, DefenseAuditEventRow):
        return candidate
    return parse_defense_audit_event_row(candidate)


__all__ = [
    "DEFAULT_RAW_FALLBACK_LIMIT",
    "DecisionAuditRawRow",
    "DecisionAuditRowProvider",
    "RawFallbackQuery",
    "fetch_limited_decision_audit_rows",
]
