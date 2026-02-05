"""Observability package for Defense PoC-0.

Provides logging, metrics, and audit trail functionality.
"""

from .schema import DecisionLogEntry, log_entry_from_step_result

__all__ = [
    "DecisionLogEntry",
    "log_entry_from_step_result",
]
