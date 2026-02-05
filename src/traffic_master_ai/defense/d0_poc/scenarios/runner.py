"""Scenario runner for Defense PoC-0 Acceptance Testing.

Executes scenarios using real D0-1 (Core) and D0-2 (Brain) components.
Runner performs execution only; pass/fail judgment is in result data.
"""

from dataclasses import replace
from typing import List, Tuple
from typing import List

from ..actions import Actuator
from ..brain import ActionPlanner, EvidenceState, RiskController, SignalAggregator
from ..core import DefenseTier, FlowState
from ..core.models import Context
from ..orchestrator.engine import transition
from ..policy import PolicyLoader
from ..policy.snapshot import PolicySnapshot
from .schema import Scenario, ScenarioStep, StepResult


class ScenarioRunner:
    """Executes acceptance test scenarios against the PoC-0 engine.

    Integrates D0-1 (Core transition) and D0-2 (Brain layer) components
    to run complete scenarios and collect results.

    Does not throw exceptions for mismatches; results are recorded in StepResult.
    """

    def __init__(self) -> None:
        """Initialize runner with all required components."""
        # D0-2 Brain components
        self._aggregator = SignalAggregator()
        self._risk = RiskController()
        self._planner = ActionPlanner()
        self._actuator = Actuator()

        # Load default policy profile
        loader = PolicyLoader()
        self._policy_profile = loader.load_profile("default")

        # Create PolicySnapshot for Core transition
        self._policy_snapshot = PolicySnapshot()

    def run_scenario(self, scenario: Scenario) -> List[StepResult]:
        """Execute a complete scenario and return step results.

        Args:
            scenario: The scenario to execute.

        Returns:
            List of StepResult, one per step.
        """
        # Initialize state
        flow_state = FlowState.S0
        tier = DefenseTier.T0
        context = Context()
        evidence = EvidenceState()

        results: List[StepResult] = []

        for seq, step in enumerate(scenario.steps):
            result, evidence = self._execute_step(
            result = self._execute_step(
                seq=seq,
                step=step,
                flow_state=flow_state,
                tier=tier,
                context=context,
                evidence=evidence,
            )
            results.append(result)

            # Update state for next step
            flow_state = result.to_state
            tier = result.to_tier
            # Context is updated in-place via _apply_mutations
            # Evidence is returned from _execute_step
            # Context and evidence are updated in-place within _execute_step
            # (via _apply_mutations and aggregator.process_event)

        return results

    def _execute_step(
        self,
        seq: int,
        step: ScenarioStep,
        flow_state: FlowState,
        tier: DefenseTier,
        context: Context,
        evidence: EvidenceState,
    ) -> Tuple[StepResult, EvidenceState]:
        """Execute a single step and return the result with updated evidence.
    ) -> StepResult:
        """Execute a single step and return the result.

        Args:
            seq: Step sequence number.
            step: The step to execute.
            flow_state: Current flow state.
            tier: Current defense tier.
            context: Current context (mutable).
            evidence: Current evidence state.

        Returns:
            Tuple of (StepResult, updated EvidenceState).
            StepResult with execution details.
        """
        from_state = flow_state
        from_tier = tier
        input_event = step.input_event

        # Step 1: Core Transition
        trans_result = transition(
            state=flow_state,
            event=input_event,
            context=context,
            policy=self._policy_snapshot,
        )
        flow_state = trans_result.next_state
        self._apply_mutations(context, trans_result.context_mutations)

        # Step 2: Evidence Update → Risk Decision
        evidence = self._aggregator.process_event(evidence, input_event)
        tier, tier_event = self._risk.decide_tier(
            evidence=evidence,
            current_tier=tier,
            current_flow_state=flow_state,
            event=input_event,
        )

        # Step 3: Plan → Actuate
        plans = self._planner.plan_actions(tier, flow_state, evidence)
        planned_actions = [p.action_type for p in plans]

        def_events = self._actuator.execute_plans(
            plans=plans,
            context=context,
            trigger_event=input_event,
        )
        emitted_event_types = [e.type for e in def_events]

        # Step 4: Apply DEF_* events to Core (secondary transitions)
        for def_event in def_events:
            secondary_result = transition(
                state=flow_state,
                event=def_event,
                context=context,
                policy=self._policy_snapshot,
            )
            flow_state = secondary_result.next_state
            self._apply_mutations(context, secondary_result.context_mutations)

        # Step 5: Build StepResult with mismatches
        mismatches = self._compute_mismatches(
            step=step,
            actual_state=flow_state,
            actual_tier=tier,
            actual_actions=planned_actions,
        )

        step_result = StepResult(
        return StepResult(
            seq=seq,
            description=step.description,
            input_event_type=input_event.type,
            from_state=from_state,
            to_state=flow_state,
            from_tier=from_tier,
            to_tier=tier,
            planned_actions=planned_actions,
            emitted_event_types=emitted_event_types,
            terminal_reason=trans_result.terminal_reason,
            failure_code=trans_result.failure_code,
            expected_state=step.expected_state,
            expected_tier=step.expected_tier,
            expected_actions=step.expected_actions,
            mismatches=mismatches,
        )
        return step_result, evidence

    def _apply_mutations(
        self, context: Context, mutations: dict
    ) -> None:
        """Apply context mutations in-place.

        Args:
            context: Context to mutate.
            mutations: Dictionary of field -> value mutations.
        """
        for field, value in mutations.items():
            if hasattr(context, field):
                setattr(context, field, value)

    def _compute_mismatches(
        self,
        step: ScenarioStep,
        actual_state: FlowState,
        actual_tier: DefenseTier,
        actual_actions: List[str],
    ) -> List[str]:
        """Compute list of mismatches between expected and actual.

        Args:
            step: The step with expectations.
            actual_state: Actual flow state after execution.
            actual_tier: Actual tier after execution.
            actual_actions: Actual planned actions.

        Returns:
            List of mismatch description strings.
        """
        mismatches: List[str] = []

        if step.expected_state is not None:
            if actual_state != step.expected_state:
                mismatches.append(
                    f"state: expected {step.expected_state.value} got {actual_state.value}"
                )

        if step.expected_tier is not None:
            if actual_tier != step.expected_tier:
                mismatches.append(
                    f"tier: expected {step.expected_tier.value} got {actual_tier.value}"
                )

        if step.expected_actions is not None:
            expected_set = set(step.expected_actions)
            actual_set = set(actual_actions)
            if expected_set != actual_set:
                missing = expected_set - actual_set
                extra = actual_set - expected_set
                if missing:
                    mismatches.append(f"actions: missing {sorted(missing)}")
                if extra:
                    mismatches.append(f"actions: unexpected {sorted(extra)}")

        return mismatches


__all__ = ["ScenarioRunner"]
