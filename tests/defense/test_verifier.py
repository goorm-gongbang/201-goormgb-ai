"""Unit tests for Scenario Verifier."""

import pytest
from typing import List

from traffic_master_ai.defense.d0_poc.core.states import (
    DefenseTier,
    FailureCode,
    FlowState,
    TerminalReason,
)
from traffic_master_ai.defense.d0_poc.scenarios.schema import StepResult
from traffic_master_ai.defense.d0_poc.scenarios.verifier import (
    AssertionResult,
    ScenarioReport,
    ScenarioVerifier,
)


def make_step_result(
    seq: int = 0,
    from_state: FlowState = FlowState.S0,
    to_state: FlowState = FlowState.S1,
    from_tier: DefenseTier = DefenseTier.T0,
    to_tier: DefenseTier = DefenseTier.T0,
    planned_actions: List[str] | None = None,
    emitted_event_types: List[str] | None = None,
    expected_state: FlowState | None = None,
    expected_tier: DefenseTier | None = None,
    expected_actions: List[str] | None = None,
    terminal_reason: TerminalReason | None = None,
    failure_code: FailureCode | None = None,
) -> StepResult:
    """Factory helper to create StepResult for testing."""
    return StepResult(
        seq=seq,
        description=f"Test step {seq}",
        input_event_type="TEST_EVENT",
        from_state=from_state,
        to_state=to_state,
        from_tier=from_tier,
        to_tier=to_tier,
        planned_actions=planned_actions or [],
        emitted_event_types=emitted_event_types or [],
        terminal_reason=terminal_reason,
        failure_code=failure_code,
        expected_state=expected_state,
        expected_tier=expected_tier,
        expected_actions=expected_actions,
        mismatches=[],
    )


class TestVerifyStep:
    """Test ScenarioVerifier.verify_step method."""

    def test_pass_when_all_match(self) -> None:
        """All expectations match actual values -> passed=True."""
        verifier = ScenarioVerifier()
        result = make_step_result(
            to_state=FlowState.S1,
            to_tier=DefenseTier.T0,
            planned_actions=["BLOCK"],
            emitted_event_types=["DEF_BLOCKED"],
            expected_state=FlowState.S1,
            expected_tier=DefenseTier.T0,
            expected_actions=["BLOCK"],
        )

        assertion = verifier.verify_step(result)

        assert assertion.passed is True
        assert assertion.mismatches == []
        assert assertion.diff_message is None

    def test_fail_when_state_mismatch(self) -> None:
        """Expected S6, actual S5 -> passed=False with diff message."""
        verifier = ScenarioVerifier()
        result = make_step_result(
            seq=5,
            to_state=FlowState.S5,  # Actual
            expected_state=FlowState.S6,  # Expected
        )

        assertion = verifier.verify_step(result)

        assert assertion.passed is False
        assert assertion.step_seq == 5
        assert len(assertion.mismatches) == 1
        assert "state: expected S6 got S5" in assertion.mismatches[0]
        assert assertion.diff_message is not None
        assert "❌ Step 5 Failed:" in assertion.diff_message

    def test_fail_when_tier_mismatch(self) -> None:
        """Expected T3, actual T1 -> passed=False."""
        verifier = ScenarioVerifier()
        result = make_step_result(
            to_tier=DefenseTier.T1,  # Actual
            expected_tier=DefenseTier.T3,  # Expected
        )

        assertion = verifier.verify_step(result)

        assert assertion.passed is False
        assert "tier: expected T3 got T1" in assertion.mismatches[0]

    def test_fail_when_action_missing(self) -> None:
        """Expected BLOCK, actual None -> passed=False."""
        verifier = ScenarioVerifier()
        result = make_step_result(
            planned_actions=[],
            emitted_event_types=[],
            expected_actions=["BLOCK"],
        )

        assertion = verifier.verify_step(result)

        assert assertion.passed is False
        assert any("missing" in m for m in assertion.mismatches)

    def test_pass_when_action_is_subset(self) -> None:
        """Expected ['BLOCK'], actual ['BLOCK', 'LOG'] -> passed=True (subset)."""
        verifier = ScenarioVerifier()
        result = make_step_result(
            planned_actions=["BLOCK"],
            emitted_event_types=["DEF_BLOCKED", "DEF_THROTTLED"],
            expected_actions=["BLOCK"],  # Subset of actual
        )

        assertion = verifier.verify_step(result)

        assert assertion.passed is True

    def test_action_normalization_block_to_def_blocked(self) -> None:
        """'BLOCK' should match 'DEF_BLOCKED' after normalization."""
        verifier = ScenarioVerifier()
        result = make_step_result(
            planned_actions=[],
            emitted_event_types=["DEF_BLOCKED"],
            expected_actions=["BLOCK"],
        )

        assertion = verifier.verify_step(result)

        assert assertion.passed is True

    def test_action_normalization_throttle(self) -> None:
        """'THROTTLE' should match 'DEF_THROTTLED'."""
        verifier = ScenarioVerifier()
        result = make_step_result(
            planned_actions=["THROTTLE"],
            emitted_event_types=["DEF_THROTTLED"],
            expected_actions=["THROTTLE"],
        )

        assertion = verifier.verify_step(result)

        assert assertion.passed is True

    def test_no_action_check_when_expected_is_none(self) -> None:
        """expected_actions=None should skip action verification."""
        verifier = ScenarioVerifier()
        result = make_step_result(
            planned_actions=["BLOCK"],
            emitted_event_types=["DEF_BLOCKED"],
            expected_actions=None,  # No check
        )

        assertion = verifier.verify_step(result)

        # Should pass because we're not checking actions
        assert assertion.passed is True

    def test_diff_message_includes_reason(self) -> None:
        """Diff message should include reason from failure_code."""
        verifier = ScenarioVerifier()
        result = make_step_result(
            seq=3,
            to_state=FlowState.SX,
            expected_state=FlowState.S5,
            failure_code=FailureCode.F_BLOCKED,
        )

        assertion = verifier.verify_step(result)

        assert assertion.passed is False
        assert assertion.diff_message is not None
        assert "F_BLOCKED" in assertion.diff_message


class TestVerifyScenario:
    """Test ScenarioVerifier.verify_scenario method."""

    def test_all_steps_pass(self) -> None:
        """Scenario with all passing steps."""
        verifier = ScenarioVerifier()
        results = [
            make_step_result(seq=0, to_state=FlowState.S1, expected_state=FlowState.S1),
            make_step_result(seq=1, to_state=FlowState.S2, expected_state=FlowState.S2),
        ]

        report = verifier.verify_scenario(results, "SCN-01", "Happy Path")

        assert report.passed is True
        assert report.total_steps == 2
        assert report.passed_steps == 2
        assert report.failed_steps == 0

    def test_mixed_pass_fail(self) -> None:
        """Scenario with some failing steps."""
        verifier = ScenarioVerifier()
        results = [
            make_step_result(seq=0, to_state=FlowState.S1, expected_state=FlowState.S1),
            make_step_result(seq=1, to_state=FlowState.S2, expected_state=FlowState.S3),  # Fail
        ]

        report = verifier.verify_scenario(results, "SCN-02", "Mixed")

        assert report.passed is False
        assert report.passed_steps == 1
        assert report.failed_steps == 1


class TestGenerateReport:
    """Test ScenarioVerifier.generate_report method."""

    def test_report_format_passed(self) -> None:
        """Report for passing scenario should contain PASSED."""
        verifier = ScenarioVerifier()
        results = [
            make_step_result(seq=0, to_state=FlowState.S1, expected_state=FlowState.S1),
        ]
        report = verifier.verify_scenario(results, "SCN-01", "Test")
        output = verifier.generate_report(report)

        assert "✅ PASSED" in output
        assert "SCN-01" in output
        assert "1/1 passed" in output

    def test_report_format_failed(self) -> None:
        """Report for failing scenario should contain FAILED and diff."""
        verifier = ScenarioVerifier()
        results = [
            make_step_result(seq=0, to_state=FlowState.S5, expected_state=FlowState.S6),
        ]
        report = verifier.verify_scenario(results, "SCN-02", "Fail Test")
        output = verifier.generate_report(report)

        assert "❌ FAILED" in output
        assert "0/1 passed" in output
        assert "Step 0: ❌ FAIL" in output
