"""Scenario runner for Defense PoC-0 Acceptance Testing.

Executes scenarios using real D0-1 (Core) and D0-2 (Brain) components.
Runner performs execution only; pass/fail judgment is in result data.
"""

from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..actions import Actuator
from ..brain import ActionPlanner, EvidenceState, RiskController, SignalAggregator
from ..core import DefenseTier, FlowState
from ..core.models import Context
from ..observability.schema import DecisionLogEntry
from ..orchestrator.engine import transition
from ..policy import PolicyLoader
from ..policy.snapshot import PolicySnapshot
from .schema import Scenario, ScenarioStep, StepResult

if TYPE_CHECKING:
    from ..observability.logger import DecisionLogger


class ScenarioRunner:
    """Executes acceptance test scenarios against the PoC-0 engine.

    Integrates D0-1 (Core transition) and D0-2 (Brain layer) components
    to run complete scenarios and collect results.

    Does not throw exceptions for mismatches; results are recorded in StepResult.
    """

    def __init__(self, logger: Optional["DecisionLogger"] = None) -> None:
        """Initialize runner with all required components.

        Args:
            logger: Optional DecisionLogger for audit trail.
                   If None, no logging is performed (backward compatible).
        """
        # D0-2 Brain components
        self._aggregator = SignalAggregator()
        self._risk = RiskController()
        self._planner = ActionPlanner()
        self._actuator = Actuator()

        # Optional logger for audit trail
        self._logger = logger

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
                seq=seq,
                step=step,
                flow_state=flow_state,
                tier=tier,
                context=context,
                evidence=evidence,
            )
            results.append(result)

            # Log the step result (after all results are computed)
            self._log_step(
                trace_id=scenario.id,
                seq=seq + 1,  # 1-based for human readability
                step=step,
                result=result,
                evidence=evidence,
            )

            # Update state for next step
            flow_state = result.to_state
            tier = result.to_tier
            # Context is updated in-place via _apply_mutations
            # Evidence is returned from _execute_step

        return results

    def _log_step(
        self,
        trace_id: str,
        seq: int,
        step: ScenarioStep,
        result: StepResult,
        evidence: EvidenceState,
    ) -> None:
        """Log a step result to the audit trail.

        Fail-safe: Any logging error is caught and printed.
        Logging must never interrupt defense logic.

        Args:
            trace_id: Scenario ID for correlation.
            seq: Step sequence (1-based).
            step: The step that was executed.
            result: The result of step execution.
            evidence: Current evidence state.
        """
        if self._logger is None:
            return

        try:
            entry = DecisionLogEntry(
                ts=datetime.now(),
                trace_id=trace_id,
                seq=seq,
                event=DecisionLogEntry.create_event_dict(
                    event_type=step.input_event.type,
                    event_id=step.input_event.event_id,
                    source=step.input_event.source.value,
                    payload_summary=step.input_event.payload if step.input_event.payload else None,
                ),
                state_transition=DecisionLogEntry.create_state_transition(
                    from_state=result.from_state.value,
                    to_state=result.to_state.value,
                ),
                tier_transition=DecisionLogEntry.create_tier_transition(
                    from_tier=result.from_tier.value,
                    to_tier=result.to_tier.value,
                ),
                evidence_snapshot=DecisionLogEntry.create_evidence_snapshot(
                    last_signal_ts=getattr(evidence, "last_signal_ts", None),
                    challenge_fail_count=getattr(evidence, "challenge_fail_count", 0),
                    seat_taken_streak=getattr(evidence, "seat_taken_streak", 0),
                    token_mismatch_detected=getattr(evidence, "token_mismatch_detected", False),
                    signal_history=list(evidence.signal_history) if hasattr(evidence, "signal_history") else [],
                ),
                decision=DecisionLogEntry.create_decision(
                    planned_actions=result.planned_actions,
                    terminal_reason=result.terminal_reason.value if result.terminal_reason else None,
                    failure_code=result.failure_code.value if result.failure_code else None,
                ),
            )
            self._logger.log(entry)
        except Exception as e:
            print(f"[ScenarioRunner] logging failed: {e}")

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

        Args:
            seq: Step sequence number.
            step: The step to execute.
            flow_state: Current flow state.
            tier: Current defense tier.
            context: Current context (mutable).
            evidence: Current evidence state.

        Returns:
            Tuple of (StepResult, updated EvidenceState).
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
