"""Semantic Event definitions for Event Dictionary v1.0."""

from traffic_master_ai.common.models.events import SemanticEvent as CommonSemanticEvent, EventType

# Alias for backward compatibility
SemanticEvent = CommonSemanticEvent

# Known semantic event types from Spec v1.0
KNOWN_EVENT_TYPES = frozenset([e.value for e in EventType])
