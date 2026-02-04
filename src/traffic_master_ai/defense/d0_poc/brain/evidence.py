"""Signal Aggregator for Defense PoC-0 Brain layer.

Collects and maintains cumulative evidence from event streams
for Risk Engine to make decisions.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Deque

from ..signals import (
    SIGNAL_TOKEN_MISMATCH,
    STAGE_3_CHALLENGE_FAILED,
    STAGE_3_CHALLENGE_PASSED,
    STAGE_5_HOLD_FAILED,
    STAGE_5_SEAT_SELECTED,
    STAGE_5_SEAT_TAKEN,
)
from ..signals.events import Event


def _create_signal_history() -> Deque[str]:
    """Factory function to create signal_history deque with maxlen=10."""
    return deque(maxlen=10)


@dataclass
class EvidenceState:
    """Cumulative evidence state managed by SignalAggregator.

    Attributes:
        last_signal_ts: Timestamp (ms) of last signal received.
        challenge_fail_count: Cumulative challenge failure count.
        seat_taken_streak: Consecutive S5 seat-taken / hold-failed count.
        signal_history: Ring buffer of last 10 signal types.
        token_mismatch_detected: Whether token mismatch has been detected.
    """

    last_signal_ts: int = 0
    challenge_fail_count: int = 0
    seat_taken_streak: int = 0
    signal_history: Deque[str] = field(default_factory=_create_signal_history)
    token_mismatch_detected: bool = False

    def copy(self) -> "EvidenceState":
        """Create a shallow copy of this state with a new deque instance."""
        new_history: Deque[str] = deque(self.signal_history, maxlen=10)
        return EvidenceState(
            last_signal_ts=self.last_signal_ts,
            challenge_fail_count=self.challenge_fail_count,
            seat_taken_streak=self.seat_taken_streak,
            signal_history=new_history,
            token_mismatch_detected=self.token_mismatch_detected,
        )


class SignalAggregator:
    """Aggregates events into cumulative evidence for Risk Engine.

    Processes event streams and updates EvidenceState according to
    Failure Matrix rules (F-1, F-3).
    """

    # S5 failure events that increase streak
    _S5_FAILURE_EVENTS = frozenset({STAGE_5_SEAT_TAKEN, STAGE_5_HOLD_FAILED})

    # S5 events that break the streak (success events)
    _S5_SUCCESS_EVENTS = frozenset({STAGE_5_SEAT_SELECTED})

    # SIGNAL_* prefix for history tracking
    _SIGNAL_PREFIX = "SIGNAL_"

    def process_event(self, state: EvidenceState, event: Event) -> EvidenceState:
        """Process an event and return updated EvidenceState.

        This method is pure: it does not mutate the input state.

        Args:
            state: Current evidence state.
            event: Event to process.

        Returns:
            New EvidenceState with updates applied.
        """
        # Create a copy to avoid mutating input
        new_state = state.copy()
        new_state.last_signal_ts = event.ts_ms

        event_type = event.type

        # F-1: Challenge failure tracking
        if event_type == STAGE_3_CHALLENGE_FAILED:
            new_state.challenge_fail_count += 1

        elif event_type == STAGE_3_CHALLENGE_PASSED:
            # Reset challenge fail count on success
            new_state.challenge_fail_count = 0

        # F-3: S5 seat-taken streak tracking
        elif event_type in self._S5_FAILURE_EVENTS:
            new_state.seat_taken_streak += 1

        elif event_type in self._S5_SUCCESS_EVENTS:
            # Break the streak on success
            new_state.seat_taken_streak = 0

        # Token mismatch detection
        if event_type == SIGNAL_TOKEN_MISMATCH:
            new_state.token_mismatch_detected = True

        # Track SIGNAL_* events in history (Ring Buffer)
        if event_type.startswith(self._SIGNAL_PREFIX):
            new_state.signal_history.append(event_type)

        return new_state


__all__ = ["EvidenceState", "SignalAggregator"]
