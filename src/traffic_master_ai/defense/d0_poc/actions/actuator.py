"""Actuator for Defense PoC-0 Actions layer.

Executes planned actions and generates DEF_* events.
This component only creates events; actual side-effects are out of scope.
"""

import uuid
from typing import List

from ..brain.planner import PlannedAction
from ..core.models import Context
from ..core.states import EventSource
from ..signals.events import Event
from ..signals.registry import (
    DEF_BLOCKED,
    DEF_CHALLENGE_FORCED,
    DEF_SANDBOXED,
    DEF_THROTTLED,
)


# PoC-0 Fixed Parameters: THROTTLE duration mapping
_THROTTLE_DURATION_MS = {
    "light": 200,
    "strong": 2000,
}


class Actuator:
    """Executes planned defense actions and generates DEF_* events.

    Transforms PlannedAction objects into concrete Event objects that can
    be dispatched to the event bus. Does not perform actual side-effects.
    """

    def execute_plans(
        self,
        plans: List[PlannedAction],
        context: Context,
        trigger_event: Event,
    ) -> List[Event]:
        """Execute planned actions and generate DEF_* events.

        This method is pure in terms of external side-effects:
        it only creates Event objects based on plans.

        Args:
            plans: List of planned actions to execute.
            context: Current context for conditional execution checks.
            trigger_event: The event that triggered this execution
                (used for session_id, ts_ms).

        Returns:
            List of generated DEF_* Event objects.
        """
        events: List[Event] = []

        for plan in plans:
            event = self._execute_single_plan(plan, context, trigger_event)
            if event is not None:
                events.append(event)

        return events

    def _execute_single_plan(
        self,
        plan: PlannedAction,
        context: Context,
        trigger_event: Event,
    ) -> Event | None:
        """Execute a single plan and return the corresponding DEF_* event.

        Args:
            plan: The planned action to execute.
            context: Current context for conditional checks.
            trigger_event: The triggering event.

        Returns:
            DEF_* Event if action was executed, None if skipped.
        """
        action_type = plan.action_type

        if action_type == "THROTTLE":
            return self._create_throttle_event(plan, trigger_event)

        if action_type == "BLOCK":
            return self._create_block_event(plan, trigger_event)

        if action_type == "CHALLENGE":
            return self._create_challenge_event(plan, trigger_event)

        if action_type == "SANDBOX":
            return self._create_sandbox_event(plan, context, trigger_event)

        # Unsupported action types (HONEY, etc.) - skip for PoC-0
        return None

    def _create_throttle_event(
        self, plan: PlannedAction, trigger_event: Event
    ) -> Event:
        """Create DEF_THROTTLED event from THROTTLE plan.

        Args:
            plan: THROTTLE action plan.
            trigger_event: The triggering event.

        Returns:
            DEF_THROTTLED Event.
        """
        strength = plan.params.get("strength", "light")
        duration_ms = _THROTTLE_DURATION_MS.get(strength, 200)

        return Event(
            event_id=f"def-{uuid.uuid4().hex[:8]}",
            ts_ms=trigger_event.ts_ms,
            type=DEF_THROTTLED,
            source=EventSource.DEFENSE,
            session_id=trigger_event.session_id,
            payload={
                "duration_ms": duration_ms,
                "strength": strength,
            },
        )

    def _create_block_event(
        self, plan: PlannedAction, trigger_event: Event
    ) -> Event:
        """Create DEF_BLOCKED event from BLOCK plan.

        Args:
            plan: BLOCK action plan.
            trigger_event: The triggering event.

        Returns:
            DEF_BLOCKED Event.
        """
        reason = plan.params.get("reason", "tier_t3")

        return Event(
            event_id=f"def-{uuid.uuid4().hex[:8]}",
            ts_ms=trigger_event.ts_ms,
            type=DEF_BLOCKED,
            source=EventSource.DEFENSE,
            session_id=trigger_event.session_id,
            payload={"reason": reason},
        )

    def _create_challenge_event(
        self, plan: PlannedAction, trigger_event: Event
    ) -> Event:
        """Create DEF_CHALLENGE_FORCED event from CHALLENGE plan.

        Args:
            plan: CHALLENGE action plan.
            trigger_event: The triggering event.

        Returns:
            DEF_CHALLENGE_FORCED Event.
        """
        difficulty = plan.params.get("difficulty", "medium")

        return Event(
            event_id=f"def-{uuid.uuid4().hex[:8]}",
            ts_ms=trigger_event.ts_ms,
            type=DEF_CHALLENGE_FORCED,
            source=EventSource.DEFENSE,
            session_id=trigger_event.session_id,
            payload={"difficulty": difficulty},
        )

    def _create_sandbox_event(
        self,
        plan: PlannedAction,
        context: Context,
        trigger_event: Event,
    ) -> Event | None:
        """Create DEF_SANDBOXED event from SANDBOX plan.

        Only creates event if not already sandboxed (context.is_sandboxed == False).
        Release is handled separately by Orchestrator/Driver.

        Args:
            plan: SANDBOX action plan.
            context: Current context for sandboxed state check.
            trigger_event: The triggering event.

        Returns:
            DEF_SANDBOXED Event if not already sandboxed, None otherwise.
        """
        # Only sandbox if not already sandboxed
        if context.is_sandboxed:
            return None

        return Event(
            event_id=f"def-{uuid.uuid4().hex[:8]}",
            ts_ms=trigger_event.ts_ms,
            type=DEF_SANDBOXED,
            source=EventSource.DEFENSE,
            session_id=trigger_event.session_id,
            payload={},
        )


__all__ = ["Actuator"]
