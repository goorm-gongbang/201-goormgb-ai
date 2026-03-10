"""Offline rollout/canary/rollback executor utilities."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping

_CANARY_DURATION_SECONDS = 120
_EVALUATION_WINDOW_SECONDS = 60
_DEDUP_DUPLICATE_RATE_ROLLBACK_PP = 2.0


@dataclass(slots=True, frozen=True)
class RolloutState:
    """Policy rollout state model."""

    stage: str
    base_policy_version: str
    candidate_policy_version: str | None
    ratio: float
    updated_at_ms: int
    stage_duration_seconds: int = 0
    evaluation_window_seconds: int = _EVALUATION_WINDOW_SECONDS
    canary_duration_seconds: int = _CANARY_DURATION_SECONDS
    expand_step_index: int | None = None
    stage_started_at_ms: int = 0
    canary_completed_at_ms: int | None = None
    rollout_finished_at_ms: int | None = None


class RolloutExecutor:
    """Canary -> expand -> rollback helper."""

    _EXPAND_STEPS: tuple[tuple[float, int], ...] = (
        (0.20, 180),
        (0.50, 240),
        (1.00, 300),
    )

    def start_canary(
        self,
        *,
        base_policy_version: str,
        candidate_policy_version: str,
        ratio: float = 0.05,
        duration_seconds: int = _CANARY_DURATION_SECONDS,
        evaluation_window_seconds: int = _EVALUATION_WINDOW_SECONDS,
    ) -> RolloutState:
        now_ms = _now_ms()
        return RolloutState(
            stage="CANARY",
            base_policy_version=base_policy_version,
            candidate_policy_version=candidate_policy_version,
            ratio=ratio,
            updated_at_ms=now_ms,
            stage_duration_seconds=duration_seconds,
            evaluation_window_seconds=evaluation_window_seconds,
            canary_duration_seconds=duration_seconds,
            stage_started_at_ms=now_ms,
        )

    def expand(self, state: RolloutState, step_index: int) -> RolloutState:
        """Advance rollout to one of the predefined expand stages."""
        if step_index < 0 or step_index >= len(self._EXPAND_STEPS):
            raise ValueError("invalid expand step index")
        ratio, duration = self._EXPAND_STEPS[step_index]
        now_ms = _now_ms()
        if ratio >= 1.0:
            promoted_version = state.candidate_policy_version or state.base_policy_version
            return RolloutState(
                stage="FULL",
                base_policy_version=promoted_version,
                candidate_policy_version=None,
                ratio=0.0,
                updated_at_ms=now_ms,
                stage_duration_seconds=duration,
                evaluation_window_seconds=state.evaluation_window_seconds,
                canary_duration_seconds=state.canary_duration_seconds,
                expand_step_index=step_index,
                stage_started_at_ms=now_ms,
                canary_completed_at_ms=state.canary_completed_at_ms or now_ms,
                rollout_finished_at_ms=now_ms,
            )
        return RolloutState(
            stage="EXPAND",
            base_policy_version=state.base_policy_version,
            candidate_policy_version=state.candidate_policy_version,
            ratio=ratio,
            updated_at_ms=now_ms,
            stage_duration_seconds=duration,
            evaluation_window_seconds=state.evaluation_window_seconds,
            canary_duration_seconds=state.canary_duration_seconds,
            expand_step_index=step_index,
            stage_started_at_ms=now_ms,
            canary_completed_at_ms=state.canary_completed_at_ms or now_ms,
            rollout_finished_at_ms=now_ms if ratio >= 1.0 else None,
        )

    def rollback(self, state: RolloutState) -> RolloutState:
        """Rollback to base policy immediately."""
        now_ms = _now_ms()
        return RolloutState(
            stage="ROLLED_BACK",
            base_policy_version=state.base_policy_version,
            candidate_policy_version=None,
            ratio=0.0,
            updated_at_ms=now_ms,
            stage_duration_seconds=0,
            evaluation_window_seconds=state.evaluation_window_seconds,
            canary_duration_seconds=state.canary_duration_seconds,
            expand_step_index=state.expand_step_index,
            stage_started_at_ms=now_ms,
            canary_completed_at_ms=state.canary_completed_at_ms,
            rollout_finished_at_ms=now_ms,
        )

    def should_rollback(self, deltas: Mapping[str, float]) -> tuple[bool, list[str]]:
        """Evaluate default rollback guardrails."""
        reasons: list[str] = []
        if deltas.get("s3_temp_lock_rate_pp", 0.0) > 0.5:
            reasons.append("s3_temp_lock_rate increases > +0.5%p")
        if deltas.get("block_rate_pp", 0.0) > 0.3:
            reasons.append("block_rate increases > +0.3%p")
        if deltas.get("avg_throttle_delay_ms", 0.0) > 100:
            reasons.append("avg_throttle_delay_ms increases > +100ms")
        if deltas.get("s3_fail_rate_pp", 0.0) > 1.0:
            reasons.append("s3_fail_rate increases > +1.0%p")
        if deltas.get("dedup_duplicate_rate_pp", 0.0) > _DEDUP_DUPLICATE_RATE_ROLLBACK_PP:
            reasons.append("dedup_duplicate_rate spikes > +2.0%p")
        if deltas.get("internal_error_rate_pp", 0.0) > 0.2:
            reasons.append("internal_error spikes")
        return (len(reasons) > 0, reasons)



def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["RolloutExecutor", "RolloutState"]
