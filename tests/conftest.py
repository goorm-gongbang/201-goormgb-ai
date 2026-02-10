"""Pytest configuration and shared fixtures."""

import pytest

from traffic_master_ai.attack.a0_poc import (
    PolicySnapshot,
    SemanticEvent,
    State,
    StateSnapshot,
)


@pytest.fixture
def initial_state_snapshot() -> StateSnapshot:
    """Create a basic initial state snapshot."""
    return StateSnapshot(
        current_state=State.S0,
        last_non_security_state=None,
        budgets={"retry": 3, "security": 2},
        counters={},
        elapsed_ms=0,
    )


@pytest.fixture
def default_policy() -> PolicySnapshot:
    """Create a default policy snapshot."""
    return PolicySnapshot(
        profile_name="default",
        rules={"max_retries": 3, "timeout_ms": 30000},
    )


@pytest.fixture
def sample_event() -> SemanticEvent:
    """Create a sample semantic event."""
    return SemanticEvent(
        type="ENTRY_ENABLED",
        stage=State.S1,
        payload={"source": "test"},
    )
