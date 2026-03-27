"""Event classification helpers built on semantic mapping outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..core.models import DefenseAuditEventRow
from ..core.state import AnalysisInput
from .semantic_mapping import EventSemantics, map_event_semantics

type EventUsage = Literal["CORE", "SUPPLEMENTAL", "UNUSED"]

CORE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "DEF_GUARD_SCORED",
        "DEF_PLAN_COMPUTED",
        "DEF_ORCH_EXECUTED",
        "DEF_THROTTLE_APPLIED",
        "DEF_BLOCK_ENFORCED",
        "S3_CHALLENGE_RESULT",
        "TURNSTILE_VERIFIED",
    }
)
SUPPLEMENTAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "DEF_ANALYZER_EVIDENCE_UPDATED",
        "DEF_BLOCK_DECIDED",
        "DEF_INVALID_TRANSITION",
    }
)
UNUSED_EVENT_TYPES: frozenset[str] = frozenset({"S3_CHALLENGE_HALTED"})


@dataclass(slots=True, frozen=True)
class InterpretedAuditEvent:
    """Raw row plus semantic interpretation and usage classification."""

    row: DefenseAuditEventRow
    usage: EventUsage
    semantics: EventSemantics


def interpret_analysis_input(
    analysis_input: AnalysisInput,
) -> tuple[InterpretedAuditEvent, ...]:
    """Interpret all raw rows without changing the analysis input contract."""

    return tuple(interpret_event(row) for row in analysis_input.defense_audit_events)


def interpret_event(row: DefenseAuditEventRow) -> InterpretedAuditEvent:
    """Interpret one raw row into a classified event view."""

    return InterpretedAuditEvent(
        row=row,
        usage=classify_event_type(row.event_type),
        semantics=map_event_semantics(row),
    )


def classify_event_type(event_type: str) -> EventUsage:
    """Classify raw audit events for downstream aggregation stages."""

    if event_type in UNUSED_EVENT_TYPES:
        return "UNUSED"
    if event_type in CORE_EVENT_TYPES:
        return "CORE"
    if event_type in SUPPLEMENTAL_EVENT_TYPES:
        return "SUPPLEMENTAL"
    return "UNUSED"


__all__ = [
    "CORE_EVENT_TYPES",
    "SUPPLEMENTAL_EVENT_TYPES",
    "UNUSED_EVENT_TYPES",
    "EventUsage",
    "InterpretedAuditEvent",
    "classify_event_type",
    "interpret_analysis_input",
    "interpret_event",
]
