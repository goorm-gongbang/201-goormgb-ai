"""Engine harness for Defense PoC-0 testing and trace generation."""

from typing import Any, Dict, List, Optional

from ..core import Context, FlowState
from ..policy.snapshot import PolicySnapshot
from ..signals.events import Event
from .engine import transition


class EngineHarness:
    """Test harness that runs event sequences through the transition engine.

    Maintains state and context across multiple events, producing a decision log
    with trace information for each transition.
    """

    def __init__(self, policy: Optional[PolicySnapshot] = None) -> None:
        """Initialize harness with optional custom policy.

        Args:
            policy: PolicySnapshot to use. If None, uses default PolicySnapshot().
        """
        self._policy = policy or PolicySnapshot()

    def run(self, events: List[Event]) -> Dict[str, Any]:
        """Run a sequence of events through the transition engine.

        Args:
            events: List of Event objects to process in order.

        Returns:
            Decision log containing final_state and trace array.
            Format:
            {
                "final_state": "SX",
                "trace": [
                    {
                        "seq": 1,
                        "event": "FLOW_START",
                        "from": "S0",
                        "to": "S1",
                        "actions": [],
                        "reason": null
                    },
                    ...
                ]
            }
        """
        state = FlowState.S0
        context = Context()
        trace: List[Dict[str, Any]] = []

        for seq, event in enumerate(events, start=1):
            from_state = state

            result = transition(
                state=state,
                event=event,
                context=context,
                policy=self._policy,
            )

            # Apply context mutations (diff)
            for k, v in result.context_mutations.items():
                setattr(context, k, v)

            # Determine reason for trace
            reason: Optional[str] = None
            if result.terminal_reason is not None:
                reason = result.terminal_reason.value
            elif result.failure_code is not None:
                reason = result.failure_code.value

            # Build trace entry
            trace_entry = {
                "seq": seq,
                "event": event.type,
                "from": from_state.value,
                "to": result.next_state.value,
                "actions": [a.type for a in result.actions],
                "reason": reason,
            }
            trace.append(trace_entry)

            # Update state for next iteration
            state = result.next_state

            # Check termination conditions
            if result.terminal_reason is not None:
                break
            if result.next_state == FlowState.SX:
                break

        return {
            "final_state": state.value,
            "trace": trace,
        }


__all__ = ["EngineHarness"]
