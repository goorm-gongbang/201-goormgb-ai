"""
Common State Definitions.

S0~SX states shared between Attack and Defense domains.
"""

from traffic_master_ai.attack.a0_poc.states import TERMINAL_REASONS, State

__all__ = [
    "State",
    "TERMINAL_REASONS",
]
