"""Unit tests for StateStore - A0-1-T3."""

import pytest

from traffic_master_ai.attack.a0_poc import State, StateSnapshot, StateStore


class TestStateStoreInitialization:
    """Tests for StateStore initialization."""

    def test_default_initialization(self) -> None:
        """Create StateStore with defaults."""
        store = StateStore()
        assert store.current_state == State.S0_INIT
        assert store.last_non_security_state is None
        assert store.elapsed_ms == 0
        assert store.get_budget("any") == 0
        assert store.get_counter("any") == 0

    def test_custom_initial_state(self) -> None:
        """Create StateStore with custom initial state."""
        store = StateStore(initial_state=State.S2_QUEUE_ENTRY)
        assert store.current_state == State.S2_QUEUE_ENTRY

    def test_initial_budgets(self) -> None:
        """Create StateStore with initial budgets."""
        store = StateStore(budgets={"retry": 3, "security": 2})
        assert store.get_budget("retry") == 3
        assert store.get_budget("security") == 2

    def test_initial_counters(self) -> None:
        """Create StateStore with initial counters."""
        store = StateStore(counters={"attempts": 5})
        assert store.get_counter("attempts") == 5


class TestStateStoreStateManagement:
    """Tests for state management."""

    def test_set_state(self) -> None:
        """Set and get current state."""
        store = StateStore()
        store.set_state(State.S1_PRE_ENTRY)
        assert store.current_state == State.S1_PRE_ENTRY

    def test_last_non_security_state(self) -> None:
        """Set and get last non-security state."""
        store = StateStore()
        assert store.last_non_security_state is None
        
        store.set_last_non_security_state(State.S2_QUEUE_ENTRY)
        assert store.last_non_security_state == State.S2_QUEUE_ENTRY
        
        store.set_last_non_security_state(None)
        assert store.last_non_security_state is None


class TestStateStoreBudgetManagement:
    """Tests for budget management - core T3 requirement."""

    def test_get_budget_default(self) -> None:
        """Get budget with default value."""
        store = StateStore()
        assert store.get_budget("unknown") == 0
        assert store.get_budget("unknown", default=10) == 10

    def test_set_budget(self) -> None:
        """Set budget value."""
        store = StateStore()
        store.set_budget("retry", 5)
        assert store.get_budget("retry") == 5

    def test_increment_budget(self) -> None:
        """Increment budget value."""
        store = StateStore(budgets={"retry": 3})
        
        # Increment existing
        new_val = store.increment_budget("retry")
        assert new_val == 4
        assert store.get_budget("retry") == 4
        
        # Increment by amount
        new_val = store.increment_budget("retry", 2)
        assert new_val == 6

    def test_increment_budget_new_key(self) -> None:
        """Increment creates key if not exists."""
        store = StateStore()
        new_val = store.increment_budget("new_key", 5)
        assert new_val == 5
        assert store.get_budget("new_key") == 5

    def test_decrement_budget(self) -> None:
        """Decrement budget value - T3 DoD requirement."""
        store = StateStore(budgets={"retry": 3})
        
        # Decrement
        new_val = store.decrement_budget("retry")
        assert new_val == 2
        assert store.get_budget("retry") == 2
        
        # Decrement by amount
        new_val = store.decrement_budget("retry", 2)
        assert new_val == 0

    def test_decrement_budget_allows_negative(self) -> None:
        """Decrement does NOT prevent negative (caller should check)."""
        store = StateStore(budgets={"retry": 1})
        new_val = store.decrement_budget("retry", 5)
        assert new_val == -4
        assert store.get_budget("retry") == -4

    def test_reset_budget(self) -> None:
        """Reset single budget - T3 DoD requirement."""
        store = StateStore(budgets={"retry": 3, "security": 2})
        
        store.reset_budget("retry")
        assert store.get_budget("retry") == 0
        assert store.get_budget("security") == 2  # unchanged
        
        store.reset_budget("security", 10)
        assert store.get_budget("security") == 10

    def test_reset_all_budgets(self) -> None:
        """Reset all budgets."""
        store = StateStore(budgets={"retry": 3, "security": 2})
        
        store.reset_all_budgets()
        assert store.get_budget("retry") == 0
        assert store.get_budget("security") == 0
        
        # Reset with initial values
        store.reset_all_budgets({"retry": 5})
        assert store.get_budget("retry") == 5


class TestStateStoreCounterManagement:
    """Tests for counter management."""

    def test_counter_operations(self) -> None:
        """Basic counter operations."""
        store = StateStore()
        
        # Increment
        store.increment_counter("attempts")
        assert store.get_counter("attempts") == 1
        
        store.increment_counter("attempts", 4)
        assert store.get_counter("attempts") == 5
        
        # Decrement
        store.decrement_counter("attempts", 2)
        assert store.get_counter("attempts") == 3
        
        # Reset
        store.reset_counter("attempts")
        assert store.get_counter("attempts") == 0

    def test_reset_all_counters(self) -> None:
        """Reset all counters."""
        store = StateStore(counters={"a": 1, "b": 2})
        store.reset_all_counters()
        assert store.get_counter("a") == 0
        assert store.get_counter("b") == 0


class TestStateStoreElapsedTime:
    """Tests for elapsed time management - T3 DoD requirement."""

    def test_initial_elapsed_ms(self) -> None:
        """Elapsed starts at 0."""
        store = StateStore()
        assert store.elapsed_ms == 0

    def test_add_elapsed_ms(self) -> None:
        """Add elapsed time - accumulation test."""
        store = StateStore()
        
        new_total = store.add_elapsed_ms(100)
        assert new_total == 100
        assert store.elapsed_ms == 100
        
        new_total = store.add_elapsed_ms(250)
        assert new_total == 350
        assert store.elapsed_ms == 350

    def test_add_elapsed_ms_negative_raises(self) -> None:
        """Negative delta should raise ValueError."""
        store = StateStore()
        with pytest.raises(ValueError, match="음수"):
            store.add_elapsed_ms(-10)

    def test_reset_elapsed_ms(self) -> None:
        """Reset elapsed time."""
        store = StateStore()
        store.add_elapsed_ms(1000)
        store.reset_elapsed_ms()
        assert store.elapsed_ms == 0


class TestStateStoreSnapshotOperations:
    """Tests for snapshot operations - T3 DoD requirement."""

    def test_get_snapshot_returns_copy(self) -> None:
        """get_snapshot returns a copy, not reference."""
        store = StateStore(
            initial_state=State.S1_PRE_ENTRY,
            budgets={"retry": 3},
        )
        
        snapshot = store.get_snapshot()
        
        # Verify values
        assert snapshot.current_state == State.S1_PRE_ENTRY
        assert snapshot.budgets["retry"] == 3
        
        # Modify snapshot should NOT affect store
        snapshot.current_state = State.S5_SEAT
        snapshot.budgets["retry"] = 0
        
        assert store.current_state == State.S1_PRE_ENTRY
        assert store.get_budget("retry") == 3

    def test_copy_store(self) -> None:
        """Copy StateStore creates independent copy."""
        store = StateStore(
            initial_state=State.S2_QUEUE_ENTRY,
            budgets={"retry": 3},
            counters={"attempts": 5},
        )
        store.add_elapsed_ms(500)
        
        copy = store.copy()
        
        # Verify copy has same values
        assert copy.current_state == State.S2_QUEUE_ENTRY
        assert copy.get_budget("retry") == 3
        assert copy.get_counter("attempts") == 5
        assert copy.elapsed_ms == 500
        
        # Modify copy should NOT affect original
        copy.set_state(State.S5_SEAT)
        copy.decrement_budget("retry")
        
        assert store.current_state == State.S2_QUEUE_ENTRY
        assert store.get_budget("retry") == 3

    def test_from_snapshot(self) -> None:
        """Create StateStore from existing snapshot."""
        snapshot = StateSnapshot(
            current_state=State.S4_SECTION,
            last_non_security_state=State.S2_QUEUE_ENTRY,
            budgets={"retry": 2},
            counters={"selections": 3},
            elapsed_ms=1500,
        )
        
        store = StateStore.from_snapshot(snapshot)
        
        assert store.current_state == State.S4_SECTION
        assert store.last_non_security_state == State.S2_QUEUE_ENTRY
        assert store.get_budget("retry") == 2
        assert store.get_counter("selections") == 3
        assert store.elapsed_ms == 1500
        
        # Original snapshot should be unaffected
        store.set_state(State.S5_SEAT)
        assert snapshot.current_state == State.S4_SECTION


class TestStateStoreRepr:
    """Tests for string representation."""

    def test_repr(self) -> None:
        """String representation for debugging."""
        store = StateStore(budgets={"retry": 3})
        store.add_elapsed_ms(100)
        
        repr_str = repr(store)
        assert "StateStore" in repr_str
        assert "S0" in repr_str
        assert "100" in repr_str
        assert "retry" in repr_str
