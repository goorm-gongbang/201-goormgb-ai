"""Policy snapshot for Defense PoC-0."""

from dataclasses import dataclass


@dataclass(slots=True)
class PolicySnapshot:
    """Immutable policy parameters used by the pure transition function."""

    max_retry_per_state: int = 3
    challenge_fail_threshold: int = 3
    seat_taken_streak_threshold: int = 7


__all__ = ["PolicySnapshot"]
