"""Session-level aggregation helpers for Backoffice Copilot."""

from .candidates import (
    CandidateSelectionResult,
    build_candidate_selection,
    is_candidate_session,
    summarize_sessions,
)
from .fallback import DecisionAuditRowProvider, RawFallbackQuery, fetch_limited_decision_audit_rows
from .session_analysis import build_session_analysis_list

__all__ = [
    "CandidateSelectionResult",
    "DecisionAuditRowProvider",
    "RawFallbackQuery",
    "build_candidate_selection",
    "build_session_analysis_list",
    "fetch_limited_decision_audit_rows",
    "is_candidate_session",
    "summarize_sessions",
]
