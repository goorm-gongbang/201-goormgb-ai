"""Event primitives for Defense PoC-0."""

from dataclasses import dataclass, field
from typing import Any, Dict

from ..core import EventSource


@dataclass(slots=True)
class Event:
    """Canonical event shape used by the PoC-0 engine."""

    event_id: str
    ts_ms: int
    type: str
    source: EventSource
    session_id: str
    payload: Dict[str, Any] = field(default_factory=dict)


__all__ = ["Event"]
