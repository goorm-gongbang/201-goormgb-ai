"""
Attack ↔ Defense Interface Contracts.

This module defines the contracts for communication between
Attack and Defense domains.

PoC-0: Schema definitions only, no implementation.
"""

from dataclasses import dataclass, field
from typing import Any

from traffic_master_ai.attack.a0_poc.states import State


@dataclass(frozen=True, slots=True)
class AttackSignal:
    """
    Signal sent from Attack domain to Defense.
    
    This is a placeholder schema for PoC-0.
    Actual signal emission is implemented in PoC-1+.
    """
    
    signal_id: str
    timestamp_ms: int
    current_state: State
    event_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DefenseDirective:
    """
    Directive sent from Defense domain to Attack.
    
    This is a placeholder schema for PoC-0.
    Actual directive handling is implemented in PoC-1+.
    """
    
    directive_id: str
    action: str  # e.g., "THROTTLE", "BLOCK", "CAPTCHA", "TERMINATE"
    priority: int = 0
    params: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "AttackSignal",
    "DefenseDirective",
]
