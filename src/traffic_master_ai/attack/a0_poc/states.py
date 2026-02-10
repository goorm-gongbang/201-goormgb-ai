"""State definitions for State Machine Spec v1.0."""

from traffic_master_ai.common.models.states import FlowState, TerminalReason

# Aliases for backward compatibility
State = FlowState

# Terminal reason literals as defined in spec
TERMINAL_REASONS = frozenset({"DONE", "ABORT", "COOLDOWN", "RESET"})

