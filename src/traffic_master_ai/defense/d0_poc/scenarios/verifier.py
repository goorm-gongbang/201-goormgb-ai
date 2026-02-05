"""Scenario verifier for Defense PoC-0 Acceptance Testing.

Provides assertion logic to compare actual execution results with expected values
and generates human-readable diff messages.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .schema import StepResult


# Action name normalization mapping
_ACTION_TO_DEF_EVENT = {
    "THROTTLE": "DEF_THROTTLED",
    "BLOCK": "DEF_BLOCKED",
    "CHALLENGE": "DEF_CHALLENGE_FORCED",
    "SANDBOX": "DEF_SANDBOXED",
    "HONEY": "DEF_HONEY",  # Future use
}


@dataclass
class AssertionResult:
    """Result of verifying a single step against expectations.

    Attributes:
        passed: True if all assertions passed.
        step_seq: Step sequence number.
        mismatches: List of mismatch descriptions.
        diff_message: Human-readable diff message (None if passed).
    """

    passed: bool
    step_seq: int
    mismatches: List[str] = field(default_factory=list)
    diff_message: Optional[str] = None


@dataclass
class ScenarioReport:
    """Summary report for a complete scenario run.

    Attributes:
        scenario_id: Scenario identifier.
        scenario_title: Scenario title.
        total_steps: Total number of steps.
        passed_steps: Number of passed steps.
        failed_steps: Number of failed steps.
        results: List of AssertionResult for each step.
    """

    scenario_id: str
    scenario_title: str
    total_steps: int
    passed_steps: int
    failed_steps: int
    results: List[AssertionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Return True if all steps passed."""
        return self.failed_steps == 0


class ScenarioVerifier:
    """Verifies scenario execution results against expected values.

    Compares state, tier, and actions. Generates human-readable diff messages.
    Does not throw exceptions; results are in AssertionResult.
    """

    def verify_step(self, actual: StepResult) -> AssertionResult:
        """Verify a single step result against its expected values.

        Args:
            actual: The StepResult from ScenarioRunner execution.

        Returns:
            AssertionResult with pass/fail status and diff message.
        """
        mismatches: List[str] = []

        # State verification
        if actual.expected_state is not None:
            if actual.to_state != actual.expected_state:
                mismatches.append(
                    f"state: expected {actual.expected_state.value} got {actual.to_state.value}"
                )

        # Tier verification
        if actual.expected_tier is not None:
            if actual.to_tier != actual.expected_tier:
                mismatches.append(
                    f"tier: expected {actual.expected_tier.value} got {actual.to_tier.value}"
                )

        # Action verification (subset check with normalization)
        if actual.expected_actions is not None:
            action_mismatch = self._verify_actions(
                expected_actions=actual.expected_actions,
                actual_planned=actual.planned_actions,
                actual_emitted=actual.emitted_event_types,
            )
            if action_mismatch:
                mismatches.append(action_mismatch)

        # Build result
        passed = len(mismatches) == 0
        diff_message = None

        if not passed:
            diff_message = self._build_diff_message(
                step_seq=actual.seq,
                mismatches=mismatches,
                actual=actual,
            )

        return AssertionResult(
            passed=passed,
            step_seq=actual.seq,
            mismatches=mismatches,
            diff_message=diff_message,
        )

    def verify_scenario(
        self,
        results: List[StepResult],
        scenario_id: str = "UNKNOWN",
        scenario_title: str = "Untitled",
    ) -> ScenarioReport:
        """Verify all step results for a complete scenario.

        Args:
            results: List of StepResult from ScenarioRunner.
            scenario_id: Scenario identifier.
            scenario_title: Scenario title.

        Returns:
            ScenarioReport with summary and per-step results.
        """
        assertion_results: List[AssertionResult] = []
        passed_count = 0
        failed_count = 0

        for result in results:
            assertion = self.verify_step(result)
            assertion_results.append(assertion)
            if assertion.passed:
                passed_count += 1
            else:
                failed_count += 1

        return ScenarioReport(
            scenario_id=scenario_id,
            scenario_title=scenario_title,
            total_steps=len(results),
            passed_steps=passed_count,
            failed_steps=failed_count,
            results=assertion_results,
        )

    def generate_report(self, report: ScenarioReport) -> str:
        """Generate a CLI-friendly report string.

        Args:
            report: ScenarioReport to format.

        Returns:
            Formatted report string for console output.
        """
        lines: List[str] = []

        # Header
        status = "✅ PASSED" if report.passed else "❌ FAILED"
        lines.append(f"{'='*60}")
        lines.append(f"Scenario: {report.scenario_id} - {report.scenario_title}")
        lines.append(f"Status: {status}")
        lines.append(f"Steps: {report.passed_steps}/{report.total_steps} passed")
        lines.append(f"{'='*60}")

        # Per-step summary
        lines.append("")
        lines.append("Step Results:")
        lines.append("-" * 40)

        for result in report.results:
            if result.passed:
                lines.append(f"  Step {result.step_seq}: ✅ PASS")
            else:
                lines.append(f"  Step {result.step_seq}: ❌ FAIL")
                if result.diff_message:
                    # Indent diff message
                    for line in result.diff_message.split("\n"):
                        lines.append(f"    {line}")

        lines.append("-" * 40)
        lines.append("")

        return "\n".join(lines)

    def _verify_actions(
        self,
        expected_actions: List[str],
        actual_planned: List[str],
        actual_emitted: List[str],
    ) -> Optional[str]:
        """Verify that expected actions are a subset of actual actions.

        Normalizes action names (BLOCK -> DEF_BLOCKED) before comparison.
        Uses set-based subset check (order-independent).

        Args:
            expected_actions: Expected action types (e.g., ["BLOCK", "THROTTLE"]).
            actual_planned: Planned action types from ActionPlanner.
            actual_emitted: Emitted event types from Actuator.

        Returns:
            Mismatch description if failed, None if passed.
        """
        # Normalize expected actions to DEF_* format
        normalized_expected = set()
        for action in expected_actions:
            normalized = _ACTION_TO_DEF_EVENT.get(action.upper(), action.upper())
            normalized_expected.add(normalized)

        # Build actual action set from both planned and emitted
        # planned_actions are like "BLOCK", "THROTTLE"
        # emitted_event_types are like "DEF_BLOCKED", "DEF_THROTTLED"
        actual_set = set()

        # Add normalized planned actions
        for action in actual_planned:
            normalized = _ACTION_TO_DEF_EVENT.get(action.upper(), action.upper())
            actual_set.add(normalized)

        # Add emitted events directly (already DEF_*)
        for event_type in actual_emitted:
            actual_set.add(event_type.upper())

        # Subset check: expected ⊆ actual
        missing = normalized_expected - actual_set
        if missing:
            return f"actions: missing {sorted(missing)}"

        return None

    def _build_diff_message(
        self,
        step_seq: int,
        mismatches: List[str],
        actual: StepResult,
    ) -> str:
        """Build a human-readable diff message.

        Args:
            step_seq: Step sequence number.
            mismatches: List of mismatch descriptions.
            actual: The actual StepResult.

        Returns:
            Formatted diff message.
        """
        # Determine reason from actual result
        reason = self._extract_reason(actual)

        # Build message
        parts = [f"❌ Step {step_seq} Failed:"]

        for mismatch in mismatches:
            parts.append(f"  - {mismatch}")

        if reason:
            parts.append(f"  (Reason: {reason})")

        return "\n".join(parts)

    def _extract_reason(self, actual: StepResult) -> Optional[str]:
        """Extract reason string from actual result.

        Uses failure_code, terminal_reason, or emitted events.

        Args:
            actual: The StepResult to extract from.

        Returns:
            Reason string or None.
        """
        if actual.failure_code is not None:
            return actual.failure_code.value

        if actual.terminal_reason is not None:
            return actual.terminal_reason.value

        # Check for DEF_* events
        def_events = [e for e in actual.emitted_event_types if e.startswith("DEF_")]
        if def_events:
            return ", ".join(def_events)

        return None


__all__ = ["AssertionResult", "ScenarioReport", "ScenarioVerifier"]
