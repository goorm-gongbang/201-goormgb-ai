"""Unit tests for AssertionEngine."""

import pytest
from traffic_master_ai.attack.a0_poc import (
    ScenarioAssertion,
    ExecutionResult,
    State,
    TerminalReason,
    check_assertion,
)


@pytest.fixture
def mock_result() -> ExecutionResult:
    return ExecutionResult(
        state_path=[State.S0, State.S1, State.S2, State.S4, State.SX],
        terminal_state=State.SX,
        terminal_reason=TerminalReason.DONE,
        handled_events=4,
        total_elapsed_ms=1000,
        final_budgets={"security": 5, "retry": 2},
        final_counters={"page_loads": 3, "api_calls": 10}
    )


def test_state_path_contains(mock_result: ExecutionResult) -> None:
    # Pass 케이스
    assertion = ScenarioAssertion(type="state_path_contains", value="S1")
    passed, msg = check_assertion(assertion, mock_result)
    assert passed is True
    assert "Visited all of" in msg

    # Fail 케이스
    assertion = ScenarioAssertion(type="state_path_contains", value="S5")
    passed, msg = check_assertion(assertion, mock_result)
    assert passed is False
    assert "Did not visit S5" in msg


def test_state_path_equals(mock_result: ExecutionResult) -> None:
    # Pass
    assertion = ScenarioAssertion(type="state_path_equals", value=["S0", "S1", "S2", "S4", "SX"])
    passed, _ = check_assertion(assertion, mock_result)
    assert passed is True

    # Fail (순서 다름)
    assertion = ScenarioAssertion(type="state_path_equals", value=["S0", "S4", "SX"])
    passed, _ = check_assertion(assertion, mock_result)
    assert passed is False


def test_counter_assertions(mock_result: ExecutionResult) -> None:
    # counter_at_least Pass
    assertion = ScenarioAssertion(type="counter_at_least", value=["api_calls", 10])
    passed, _ = check_assertion(assertion, mock_result)
    assert passed is True

    # counter_at_least Fail
    assertion = ScenarioAssertion(type="counter_at_least", value=["api_calls", 11])
    passed, _ = check_assertion(assertion, mock_result)
    assert passed is False

    # counter_equals Pass
    assertion = ScenarioAssertion(type="counter_equals", value=["page_loads", 3])
    passed, _ = check_assertion(assertion, mock_result)
    assert passed is True


def test_budget_assertions(mock_result: ExecutionResult) -> None:
    # budget_remaining_at_most Pass
    assertion = ScenarioAssertion(type="budget_remaining_at_most", value=["retry", 2])
    passed, _ = check_assertion(assertion, mock_result)
    assert passed is True

    # budget_remaining_at_most Fail
    assertion = ScenarioAssertion(type="budget_remaining_at_most", value=["security", 4])
    passed, _ = check_assertion(assertion, mock_result)
    assert passed is False


def test_event_handled_count(mock_result: ExecutionResult) -> None:
    assertion = ScenarioAssertion(type="event_handled_count_at_least", value=4)
    passed, _ = check_assertion(assertion, mock_result)
    assert passed is True

    assertion = ScenarioAssertion(type="event_handled_count_at_least", value=5)
    passed, _ = check_assertion(assertion, mock_result)
    assert passed is False


def test_security_recovery_assertion() -> None:
    # Pass: S3 -> S2 (Recovery)
    res = ExecutionResult(
        state_path=[State.S2, State.S3, State.S2, State.SX],
        terminal_state=State.SX,
        terminal_reason=TerminalReason.DONE,
        handled_events=3,
        total_elapsed_ms=500
    )
    assertion = ScenarioAssertion(type="returned_to_last_non_security_state")
    passed, _ = check_assertion(assertion, res)
    assert passed is True

    # Fail: S3 -> SX (No Recovery)
    res = ExecutionResult(
        state_path=[State.S2, State.S3, State.SX],
        terminal_state=State.SX,
        terminal_reason=TerminalReason.ABORT,
        handled_events=2,
        total_elapsed_ms=500
    )
    passed, msg = check_assertion(assertion, res)
    assert passed is False
    assert "instead of recovery" in msg
