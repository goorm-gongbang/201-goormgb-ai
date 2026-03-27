"""SessionAnalysis assembly for Task 5."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..core.models import SessionAnalysis, SessionSummary
from ..core.state import AnalysisInput
from ..ingest.interpreter import InterpretedAuditEvent, interpret_analysis_input
from ..storage.validators import validate_session_analysis_json
from .fallback import (
    DEFAULT_RAW_FALLBACK_LIMIT,
    DecisionAuditRowProvider,
    RawFallbackQuery,
    fetch_limited_decision_audit_rows,
)

_UNKNOWN_FIELDS = frozenset({"", "UNKNOWN"})


def build_session_analysis_list(
    candidate_sessions: tuple[SessionSummary, ...] | list[SessionSummary],
    analysis_input: AnalysisInput,
    *,
    window_start_ms: int,
    window_end_ms: int,
    raw_fallback_provider: DecisionAuditRowProvider | None = None,
    max_workers: int = 4,
    raw_fallback_limit: int = DEFAULT_RAW_FALLBACK_LIMIT,
) -> tuple[SessionAnalysis, ...]:
    """Build storage-compatible SessionAnalysis objects in candidate order."""

    candidate_list = list(candidate_sessions)
    if not candidate_list:
        return ()

    grouped_events = _group_interpreted_events(analysis_input)
    if max_workers <= 1 or len(candidate_list) == 1:
        return tuple(
            _build_one_session_analysis(
                summary,
                grouped_events.get(summary.session_id, ()),
                analysis_input=analysis_input,
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
                raw_fallback_provider=raw_fallback_provider,
                raw_fallback_limit=raw_fallback_limit,
            )
            for summary in candidate_list
        )

    analyses: list[SessionAnalysis | None] = [None] * len(candidate_list)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(candidate_list))) as executor:
        futures = {
            executor.submit(
                _build_one_session_analysis,
                summary,
                grouped_events.get(summary.session_id, ()),
                analysis_input=analysis_input,
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
                raw_fallback_provider=raw_fallback_provider,
                raw_fallback_limit=raw_fallback_limit,
            ): index
            for index, summary in enumerate(candidate_list)
        }
        for future, index in futures.items():
            analyses[index] = future.result()
    return tuple(analysis for analysis in analyses if analysis is not None)


def _group_interpreted_events(
    analysis_input: AnalysisInput,
) -> dict[str, tuple[InterpretedAuditEvent, ...]]:
    grouped: dict[str, list[InterpretedAuditEvent]] = {}
    for interpreted in interpret_analysis_input(analysis_input):
        session_id = interpreted.row.session_id
        if not session_id:
            continue
        grouped.setdefault(session_id, []).append(interpreted)
    return {session_id: tuple(events) for session_id, events in grouped.items()}


def _build_one_session_analysis(
    summary: SessionSummary,
    interpreted_events: tuple[InterpretedAuditEvent, ...],
    *,
    analysis_input: AnalysisInput,
    window_start_ms: int,
    window_end_ms: int,
    raw_fallback_provider: DecisionAuditRowProvider | None,
    raw_fallback_limit: int,
) -> SessionAnalysis:
    timeline_summary = _build_timeline_summary(summary, interpreted_events, ())
    suspicious_signals = _build_suspicious_signals(summary, interpreted_events, ())
    needs_raw_fallback = _should_trigger_raw_fallback(
        summary=summary,
        suspicious_signals=suspicious_signals,
    )

    fallback_events: tuple[InterpretedAuditEvent, ...] = ()
    fallback_error = False
    if needs_raw_fallback and analysis_input.raw_audit_available:
        try:
            fallback_rows = fetch_limited_decision_audit_rows(
                RawFallbackQuery(
                    session_id=summary.session_id,
                    window_start_ms=window_start_ms,
                    window_end_ms=window_end_ms,
                    limit=raw_fallback_limit,
                ),
                raw_fallback_provider,
            )
        except Exception:
            fallback_rows = ()
            fallback_error = True
        fallback_events = tuple(
            interpreted
            for interpreted in interpret_analysis_input(
                AnalysisInput(defense_audit_events=fallback_rows, raw_audit_available=False)
            )
            if interpreted.row.session_id == summary.session_id
        )
        if fallback_events:
            timeline_summary = _build_timeline_summary(summary, interpreted_events, fallback_events)
            suspicious_signals = _build_suspicious_signals(summary, interpreted_events, fallback_events)
            needs_raw_fallback = _should_trigger_raw_fallback(
                summary=summary,
                suspicious_signals=suspicious_signals,
            )

    if needs_raw_fallback:
        if not analysis_input.raw_audit_available:
            timeline_summary = _append_unique(
                timeline_summary,
                "Additional raw context is unavailable because limited decision_audit fallback is disabled.",
            )
        elif raw_fallback_provider is None:
            timeline_summary = _append_unique(
                timeline_summary,
                "Additional raw context is still required within the limited decision_audit window.",
            )
        elif fallback_error:
            timeline_summary = _append_unique(
                timeline_summary,
                "Limited decision_audit fallback failed within the requested session window.",
            )
        elif not fallback_events:
            timeline_summary = _append_unique(
                timeline_summary,
                "Limited decision_audit fallback returned no additional rows for this session window.",
            )

    resolved_flow_state = _resolve_summary_field(
        summary.latest_flow_state,
        fallback_events,
        field_name="latest_flow_state",
    )
    resolved_action = _resolve_summary_field(
        summary.latest_action,
        fallback_events,
        field_name="latest_action",
    )
    resolved_tier = _resolve_summary_field(
        summary.latest_tier,
        fallback_events,
        field_name="latest_tier",
    )
    resolved_terminal_outcome = _resolve_summary_field(
        summary.terminal_outcome,
        fallback_events,
        field_name="terminal_outcome",
    )

    analysis = SessionAnalysis(
        session_id=summary.session_id,
        latest_flow_state=resolved_flow_state,
        latest_action=resolved_action,
        latest_tier=resolved_tier,
        terminal_outcome=resolved_terminal_outcome,
        seen_t1=summary.seen_t1,
        seen_t2=summary.seen_t2,
        vqa_fail_count=summary.vqa_fail_count,
        throttle_event_count=summary.throttle_event_count,
        suspicious_signals=list(suspicious_signals),
        timeline_summary=list(timeline_summary),
        needs_raw_fallback=needs_raw_fallback,
    )
    validate_session_analysis_json(analysis)
    return analysis


def _should_trigger_raw_fallback(
    *,
    summary: SessionSummary,
    suspicious_signals: tuple[str, ...],
) -> bool:
    return (
        summary.latest_flow_state in _UNKNOWN_FIELDS
        or summary.latest_action in _UNKNOWN_FIELDS
        or summary.latest_tier in _UNKNOWN_FIELDS
        or summary.terminal_outcome in _UNKNOWN_FIELDS
        or not suspicious_signals
    )


def _build_timeline_summary(
    summary: SessionSummary,
    interpreted_events: tuple[InterpretedAuditEvent, ...],
    fallback_events: tuple[InterpretedAuditEvent, ...],
) -> tuple[str, ...]:
    items: list[str] = []

    if summary.seen_t2:
        items.append("Session reached T2 during evaluation.")
    elif summary.seen_t1:
        items.append("Session reached T1 during evaluation.")

    if summary.throttle_event_count > 0:
        items.append(f"Throttle was applied {summary.throttle_event_count} time(s).")
    if summary.vqa_fail_count > 0:
        items.append(f"S3 challenge failures were observed {summary.vqa_fail_count} time(s).")

    latest_reason = _latest_terminal_reason(interpreted_events, fallback_events)
    if latest_reason is not None:
        items.append(f"Terminal reason recorded as {latest_reason}.")
    elif summary.terminal_outcome not in _UNKNOWN_FIELDS:
        items.append(f"Terminal outcome remained {summary.terminal_outcome}.")

    return _dedupe(items)


def _build_suspicious_signals(
    summary: SessionSummary,
    interpreted_events: tuple[InterpretedAuditEvent, ...],
    fallback_events: tuple[InterpretedAuditEvent, ...],
) -> tuple[str, ...]:
    items: list[str] = []

    if summary.seen_t2:
        items.append("Reached T2 during session")
    if summary.vqa_fail_count > 0:
        items.append("VQA failure observed")
    if summary.throttle_event_count > 0:
        items.append("Throttle applied during session")
    if summary.vqa_fail_count == 0 and _has_vqa_fail_signal(fallback_events):
        items.append("VQA failure observed")
    if summary.throttle_event_count == 0 and _has_event_type(
        fallback_events,
        "DEF_THROTTLE_APPLIED",
    ):
        items.append("Throttle applied during session")
    if summary.latest_action == "THROTTLE":
        items.append("Latest action remained THROTTLE")

    latest_reason = _latest_terminal_reason(interpreted_events, fallback_events)
    if latest_reason is not None:
        items.append(f"Terminal reason observed: {latest_reason}")

    return _dedupe(items)


def _resolve_summary_field(
    primary_value: str,
    fallback_events: tuple[InterpretedAuditEvent, ...],
    *,
    field_name: str,
) -> str:
    if primary_value not in _UNKNOWN_FIELDS:
        return primary_value

    for event in reversed(fallback_events):
        fallback_value = getattr(event.semantics, field_name)
        if fallback_value and fallback_value not in _UNKNOWN_FIELDS:
            return fallback_value
    return primary_value


def _latest_terminal_reason(
    interpreted_events: tuple[InterpretedAuditEvent, ...],
    fallback_events: tuple[InterpretedAuditEvent, ...],
) -> str | None:
    for event in reversed(interpreted_events + fallback_events):
        reason = event.semantics.terminal_reason
        if reason:
            return reason
    return None


def _has_vqa_fail_signal(events: tuple[InterpretedAuditEvent, ...]) -> bool:
    return any(
        event.row.event_type == "S3_CHALLENGE_RESULT"
        and (
            event.semantics.reason_code is not None
            or event.semantics.terminal_reason is not None
        )
        for event in events
    )


def _has_event_type(events: tuple[InterpretedAuditEvent, ...], event_type: str) -> bool:
    return any(event.row.event_type == event_type for event in events)


def _append_unique(items: tuple[str, ...], item: str) -> tuple[str, ...]:
    if item in items:
        return items
    return items + (item,)


def _dedupe(items: list[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return tuple(deduped)


__all__ = ["build_session_analysis_list"]
