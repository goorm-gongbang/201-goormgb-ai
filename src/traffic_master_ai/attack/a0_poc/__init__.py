"""
Attack PoC-0 - Pure State Machine Engine.

This package contains the core state machine implementation for A0-1.
"""

from traffic_master_ai.attack.a0_poc.events import KNOWN_EVENT_TYPES, SemanticEvent
from traffic_master_ai.attack.a0_poc.logger import DecisionLogger
from traffic_master_ai.attack.a0_poc.orchestrator import run_events
from traffic_master_ai.attack.a0_poc.snapshots import PolicySnapshot, StateSnapshot
from traffic_master_ai.attack.a0_poc.states import TERMINAL_REASONS, State, TerminalReason
from traffic_master_ai.attack.a0_poc.store import StateStore
from traffic_master_ai.attack.a0_poc.transition import (
    DecisionLog,
    ExecutionResult,
    TransitionResult,
    transition,
)

__all__ = [
    # States
    "State",
    "TerminalReason",
    "TERMINAL_REASONS",
    # Events
    "SemanticEvent",
    "KNOWN_EVENT_TYPES",
    # Snapshots
    "StateSnapshot",
    "PolicySnapshot",
    # Store
    "StateStore",
    # Transition
    "transition",
    "TransitionResult",
    "ExecutionResult",
    "DecisionLog",
    # Orchestrator
    "run_events",
    # Logger
    "DecisionLogger",
]

