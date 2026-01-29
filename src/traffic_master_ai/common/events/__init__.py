"""
Common Event Definitions.

Shared SemanticEvent types and DEF_* event types used by both
Attack and Defense domains.
"""

from traffic_master_ai.attack.a0_poc.events import KNOWN_EVENT_TYPES, SemanticEvent

# Defense-specific event types (placeholder for PoC-1+)
DEF_EVENT_TYPES = frozenset({
    # Signal events
    "DEF_SIGNAL_ANOMALY",
    "DEF_SIGNAL_RATE_LIMIT",
    "DEF_SIGNAL_PATTERN_MATCH",
    # Action events
    "DEF_ACTION_THROTTLE",
    "DEF_ACTION_BLOCK",
    "DEF_ACTION_CAPTCHA",
    "DEF_ACTION_TERMINATE",
})

__all__ = [
    "SemanticEvent",
    "KNOWN_EVENT_TYPES",
    "DEF_EVENT_TYPES",
]
