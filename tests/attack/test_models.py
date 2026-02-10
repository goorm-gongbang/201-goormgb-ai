"""Unit tests for data models."""

import pytest

from traffic_master_ai.attack.a0_poc import (
    DecisionLog,
    PolicySnapshot,
    SemanticEvent,
    State,
    StateSnapshot,
    TERMINAL_REASONS,
    TerminalReason,
    TransitionResult,
)


class TestState:
    """Tests for State enum."""

    def test_state_enum_values(self) -> None:
        """Verify all state enum values match spec."""
        assert State.S0.value == "S0"
        assert State.S1.value == "S1"
        assert State.S2.value == "S2"
        assert State.S3.value == "S3"
        assert State.S4.value == "S4"
        assert State.S5.value == "S5"
        assert State.S6.value == "S6"
        assert State.SX.value == "SX"

    def test_is_terminal(self) -> None:
        """Only SX is terminal."""
        assert State.SX.is_terminal()
        for state in State:
            if state != State.SX:
                assert not state.is_terminal()

    def test_is_security(self) -> None:
        """Only S3 is security state."""
        assert State.S3.is_security()
        for state in State:
            if state != State.S3:
                assert not state.is_security()

    def test_can_be_last_non_security(self) -> None:
        """Per spec: last_non_security_state ∈ {S1, S2, S4, S5, S6}."""
        valid_states = {
            State.S1,
            State.S2,
            State.S4,
            State.S5,
            State.S6,
        }
        for state in State:
            if state in valid_states:
                assert state.can_be_last_non_security()
            else:
                assert not state.can_be_last_non_security()

    def test_terminal_reasons(self) -> None:
        """Verify terminal reasons match spec."""
        assert TERMINAL_REASONS == {"done", "abort", "cooldown", "reset"}


class TestSemanticEvent:
    """Tests for SemanticEvent dataclass."""

    def test_creation_minimal(self) -> None:
        """Create event with minimal fields."""
        event = SemanticEvent(type="ENTRY_ENABLED")
        assert event.type == "ENTRY_ENABLED"
        assert event.stage is None
        assert event.failure_code is None
        assert event.payload == {}

    def test_creation_full(self) -> None:
        """Create event with all fields."""
        event = SemanticEvent(
            type="CHALLENGE_FAILED",
            stage=State.S3,
            failure_code="CAPTCHA_TIMEOUT",
            payload={"attempt": 3},
        )
        assert event.type == "CHALLENGE_FAILED"
        assert event.stage == State.S3
        assert event.failure_code == "CAPTCHA_TIMEOUT"
        assert event.payload == {"attempt": 3}

    def test_immutability(self) -> None:
        """SemanticEvent should be frozen."""
        event = SemanticEvent(type="FLOW_START")
        with pytest.raises((AttributeError, TypeError)):
            event.type = "MODIFIED"  # type: ignore[misc]

    def test_empty_event_type_raises(self) -> None:
        """Empty event_type should raise ValueError."""
        with pytest.raises(ValueError):
            SemanticEvent(type="")


class TestStateSnapshot:
    """Tests for StateSnapshot dataclass."""

    def test_creation(self, initial_state_snapshot: StateSnapshot) -> None:
        """Create state snapshot."""
        assert initial_state_snapshot.current_state == State.S0
        assert initial_state_snapshot.last_non_security_state is None
        assert initial_state_snapshot.budgets == {"retry": 3, "security": 2}
        assert initial_state_snapshot.counters == {}
        assert initial_state_snapshot.elapsed_ms == 0

    def test_mutability(self, initial_state_snapshot: StateSnapshot) -> None:
        """StateSnapshot should be mutable."""
        initial_state_snapshot.current_state = State.S1
        initial_state_snapshot.elapsed_ms = 1000
        assert initial_state_snapshot.current_state == State.S1
        assert initial_state_snapshot.elapsed_ms == 1000

    def test_copy(self, initial_state_snapshot: StateSnapshot) -> None:
        """Copy should create independent snapshot."""
        copy = initial_state_snapshot.copy()
        copy.current_state = State.S5
        copy.budgets["retry"] = 0
        # Original unchanged
        assert initial_state_snapshot.current_state == State.S0
        assert initial_state_snapshot.budgets["retry"] == 3


class TestPolicySnapshot:
    """Tests for PolicySnapshot dataclass."""

    def test_creation(self, default_policy: PolicySnapshot) -> None:
        """Create policy snapshot."""
        assert default_policy.profile_name == "default"
        assert default_policy.rules == {"max_retries": 3, "timeout_ms": 30000}

    def test_immutability(self, default_policy: PolicySnapshot) -> None:
        """PolicySnapshot should be frozen."""
        with pytest.raises(AttributeError):
            default_policy.profile_name = "modified"  # type: ignore[misc]

    def test_get_rule(self, default_policy: PolicySnapshot) -> None:
        """Test get_rule helper."""
        assert default_policy.get_rule("max_retries") == 3
        assert default_policy.get_rule("unknown") is None
        assert default_policy.get_rule("unknown", 99) == 99


class TestTransitionResult:
    """Tests for TransitionResult dataclass."""

    def test_normal_transition(self) -> None:
        """Create normal (non-terminal) transition result."""
        result = TransitionResult(
            next_state=State.S2,
            notes=["Transitioned from S1"],
        )
        assert result.next_state == State.S2
        assert result.terminal_reason is None
        assert not result.is_terminal()

    def test_terminal_transition(self) -> None:
        """Create terminal transition result."""
        result = TransitionResult(
            next_state=State.SX,
            terminal_reason=TerminalReason.DONE,
            notes=["Payment complete"],
        )
        assert result.is_terminal()
        assert result.terminal_reason == TerminalReason.DONE

    def test_terminal_requires_reason(self) -> None:
        """SX transition without terminal_reason should raise."""
        with pytest.raises(ValueError, match="terminal_reason 필수"):
            TransitionResult(next_state=State.SX)

    def test_non_terminal_no_reason(self) -> None:
        """Non-terminal with terminal_reason should raise."""
        with pytest.raises(ValueError, match="terminal_reason은 None"):
            TransitionResult(
                next_state=State.S4,
                terminal_reason=TerminalReason.DONE,
            )

    def test_immutability(self) -> None:
        """TransitionResult should be frozen."""
        result = TransitionResult(next_state=State.S2)
        with pytest.raises(AttributeError):
            result.next_state = State.S3  # type: ignore[misc]


class TestDecisionLog:
    """Tests for DecisionLog dataclass."""

    def test_creation(self, sample_event: SemanticEvent) -> None:
        """Create decision log entry."""
        log = DecisionLog(
            decision_id="test-001",
            timestamp_ms=1706500000000,
            current_state=State.S1,
            event=sample_event,
            next_state=State.S2,
            policy_profile="default",
            budgets={"retry": 3},
            counters={},
            elapsed_ms=500,
        )
        assert log.decision_id == "test-001"
        assert log.current_state == State.S1
        assert log.next_state == State.S2

    def test_to_dict(self, sample_event: SemanticEvent) -> None:
        """Test serialization schema."""
        log = DecisionLog(
            decision_id="test-002",
            timestamp_ms=1706500000000,
            current_state=State.S1,
            event=sample_event,
            next_state=State.S2,
            policy_profile="default",
            budgets={"retry": 2},
            counters={"attempts": 1},
            elapsed_ms=1000,
            notes=["Test note"],
        )
        d = log.to_dict()
        assert d["decision_id"] == "test-002"
        assert d["current_state"] == "S1"
        assert d["next_state"] == "S2"
        assert d["event"]["event_type"] == "ENTRY_ENABLED" or d["event"].get("type") == "ENTRY_ENABLED"
        assert d["notes"] == ["Test note"]
