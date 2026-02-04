"""
Attack PoC-0 - Pure State Machine Engine.

This package contains the core state machine implementation for A0-1.
"""

from traffic_master_ai.attack.a0_poc.event_registry import (
    EVENT_VALID_STATES,
    EventSource,
    EventType,
    get_valid_states,
    is_valid_in_state,
)
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
from traffic_master_ai.attack.a0_poc.validator import (
    EventValidator,
    ValidationError,
    ValidationResult,
)
from traffic_master_ai.attack.a0_poc.policy_loader import (
    InvalidProfileSchemaError,
    PolicyProfile,
    PolicyProfileLoader,
    ProfileNotFoundError,
)
from traffic_master_ai.attack.a0_poc.runtime import BudgetManager, TimeboxManager
from traffic_master_ai.attack.a0_poc.failure import (
    FailureCode,
    FailureMatrix,
    FailurePolicy,
)
from traffic_master_ai.attack.a0_poc.roi import ROILogger, EvidenceLog
from traffic_master_ai.attack.a0_poc.scenario_models import (
    Scenario,
    ScenarioEvent,
    ScenarioAssertion,
    ScenarioAcceptance,
)
from traffic_master_ai.attack.a0_poc.scenario_loader import ScenarioLoader
from traffic_master_ai.attack.a0_poc.scenario_runner import ScenarioRunner

__all__ = [
    # States
    "State",
    "TerminalReason",
    "TERMINAL_REASONS",
    # Events
    "SemanticEvent",
    "KNOWN_EVENT_TYPES",
    # Event Registry (A0-2-T1)
    "EventType",
    "EventSource",
    "EVENT_VALID_STATES",
    "get_valid_states",
    "is_valid_in_state",
    # Validator (A0-2-T2)
    "EventValidator",
    "ValidationResult",
    "ValidationError",
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
    # Policy Loader (A0-2-T3)
    "PolicyProfile",
    "PolicyProfileLoader",
    "ProfileNotFoundError",
    "InvalidProfileSchemaError",
    # Runtime (A0-2-T4)
    "BudgetManager",
    "TimeboxManager",
    # Failure & ROI (A0-3)
    "FailureCode",
    "FailureMatrix",
    "FailurePolicy",
    "ROILogger",
    "EvidenceLog",
    # Scenario (A0-4)
    "Scenario",
    "ScenarioEvent",
    "ScenarioAssertion",
    "ScenarioAcceptance",
    "ScenarioLoader",
    "ScenarioRunner",
]

