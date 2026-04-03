"""Guard implementation for D0-MVP.

Ref: annex/guard_spec.yaml
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..core.constants import (
    GUARD_STEP_RISK_EXT_WEIGHT,
    GUARD_STEP_RISK_INT_WEIGHT,
    GUARD_WEIGHT_DWELL,
    GUARD_WEIGHT_LINEARITY,
    GUARD_WEIGHT_LINEAR_PATH,
    GUARD_WEIGHT_TREMOR,
    GUARD_WEIGHT_VELOCITY,
)
from ..core.enums import DefenseTier
from ..core.models import SessionState
from ..events.catalog import S3_PASS, S3_RESULT
from ..events.common import RuntimeEvent
from ..policy.snapshot import PolicySnapshot
from ..state.dedup import DedupChecker
from ..state.session_state import SessionStateManager


@dataclass(slots=True, frozen=True)
class GuardOutput:
    """Guard stage output contract."""

    s_int: float
    s_ext_botlikeness: float
    s_t: float
    r_prev: float
    r_new: float
    tier: DefenseTier
    rule_hits: tuple[str, ...]
    missing_flags: tuple[str, ...]
    is_duplicate: bool
    dedup_key: Optional[str] = None

    def to_state_changes(self, ts_ms: int) -> dict[str, Any]:
        """Serialize guard-owned state fields for Redis write."""
        return {
            "riskScore": self.r_new,
            "defenseTier": self.tier.value,
            "lastStepRisk": self.s_t,
            "lastGuardTsMs": ts_ms,
        }


class Guard:
    """Double-hybrid filter.

    Ref: annex/guard_spec.yaml#math_defs, #internal_score, #risk_accumulation
    """

    def __init__(self, dedup: Optional[DedupChecker] = None) -> None:
        self._dedup = dedup

    def score(
        self,
        *,
        trace_id: str,
        event: RuntimeEvent,
        state: SessionState,
        policy: PolicySnapshot,
        features: Optional[Mapping[str, Any]] = None,
        external_score: Optional[float] = None,
    ) -> GuardOutput:
        """Compute Guard score update for one event.

        Args:
            trace_id: Request trace identifier for dedup key.
            event: Runtime event.
            state: Current session state snapshot.
            policy: Frozen policy snapshot.
            features: Optional feature summary map.
            external_score: Optional external human-likely score [0..1].
        """
        dedup_key: Optional[str] = None
        if self._dedup is not None:
            dedup_key = self._dedup.dedup_key(trace_id, event.event_type, event.ts_ms)
            if self._dedup.check_and_mark(trace_id, event.event_type, event.ts_ms):
                return GuardOutput(
                    s_int=0.0,
                    s_ext_botlikeness=0.0,
                    s_t=0.0,
                    r_prev=state.risk_score,
                    r_new=state.risk_score,
                    tier=state.defense_tier,
                    rule_hits=("DUPLICATE_EVENT_SKIPPED",),
                    missing_flags=(),
                    is_duplicate=True,
                    dedup_key=dedup_key,
                )

        f = dict(features or {})
        if external_score is None:
            if event.external_score is not None:
                external_score = event.external_score
            elif "external_score" in f:
                external_score = _to_float(f.get("external_score"))
            elif "turnstile_score" in f:
                # Legacy fallback for older callers that still send turnstile_score.
                external_score = _to_float(f.get("turnstile_score"))

        rule_hits: list[str] = []
        missing_flags: list[str] = []

        tremor = _resolve_feature(
            f,
            key="tremorStdDev",
            default=3.0,
            missing_flag="MISSING_TREMOR",
            missing_flags=missing_flags,
        )
        linearity = _resolve_feature(
            f,
            key="linearityRatio",
            default=0.5,
            missing_flag="MISSING_LINEARITY",
            missing_flags=missing_flags,
        )
        velocity = _resolve_feature(
            f,
            key="avgVelocity",
            default=775.0,
            missing_flag="MISSING_VELOCITY",
            missing_flags=missing_flags,
        )
        dwell = _resolve_feature(
            f,
            key="dwellTime",
            default=1000.0,
            missing_flag="MISSING_DWELL",
            missing_flags=missing_flags,
        )
        path_ratio = _resolve_feature(
            f,
            key="pathRatio",
            default=1.2,
            missing_flag="MISSING_PATHRATIO",
            missing_flags=missing_flags,
        )

        tremor, tremor_clipped = _clip(tremor, 0.0, 6.0)
        velocity, velocity_clipped = _clip(velocity, 0.0, 4000.0)
        dwell, dwell_clipped = _clip(dwell, 0.0, 2000.0)
        path_ratio, path_ratio_clipped = _clip(path_ratio, 1.0, 3.0)
        linearity, _ = _clip(linearity, 0.0, 1.0)

        if tremor_clipped:
            rule_hits.append("CLIPPED_TREMOR")
        if velocity_clipped:
            rule_hits.append("CLIPPED_VELOCITY")
        if dwell_clipped:
            rule_hits.append("CLIPPED_DWELL")
        if path_ratio_clipped:
            rule_hits.append("CLIPPED_PATHRATIO")

        tremor_bot = 1.0 - normalize(tremor, 0.0, 6.0)
        linearity_bot = linearity
        velocity_bot = is_unnatural_velocity(velocity)
        dwell_bot = 1.0 - normalize(dwell, 0.0, 2000.0)
        linear_path = is_linear_path(linearity, path_ratio)

        if linear_path >= 1.0:
            rule_hits.append("LINEAR_PATH_DETECTED")
        if velocity_bot >= 0.8:
            rule_hits.append("HIGH_VELOCITY_UNNATURAL")

        s_int = clamp(
            GUARD_WEIGHT_TREMOR * tremor_bot
            + GUARD_WEIGHT_LINEARITY * linearity_bot
            + GUARD_WEIGHT_VELOCITY * velocity_bot
            + GUARD_WEIGHT_DWELL * dwell_bot
            + GUARD_WEIGHT_LINEAR_PATH * linear_path,
            0.0,
            1.0,
        )

        ext = _to_float(external_score)
        if ext is None:
            ext = 0.5
            missing_flags.append("MISSING_EXT_SCORE")
        ext = clamp(ext, 0.0, 1.0)
        s_ext_botlikeness = 1.0 - ext

        r_prev = _apply_passive_decay(
            risk_score=state.risk_score,
            last_guard_ts_ms=state.last_guard_ts_ms,
            now_ms=event.ts_ms,
            policy=policy,
            rule_hits=rule_hits,
        )
        s_t = clamp(
            (GUARD_STEP_RISK_EXT_WEIGHT * s_ext_botlikeness)
            + (GUARD_STEP_RISK_INT_WEIGHT * s_int),
            0.0,
            1.0,
        )
        r_new = clamp(
            ((1.0 - policy.ewma_alpha) * r_prev) + (policy.ewma_alpha * s_t),
            0.0,
            1.0,
        )
        if event.event_type == S3_RESULT and event.s3_result == S3_PASS:
            r_new = clamp(r_new * 0.5, 0.0, 1.0)
            rule_hits.append("VERIFICATION_DECAY_APPLIED")
        tier = map_tier(
            r_new,
            policy=policy,
            previous_tier=state.defense_tier,
            in_probation=_in_probation(state, event.ts_ms),
        )

        return GuardOutput(
            s_int=s_int,
            s_ext_botlikeness=s_ext_botlikeness,
            s_t=s_t,
            r_prev=r_prev,
            r_new=r_new,
            tier=tier,
            rule_hits=tuple(rule_hits),
            missing_flags=tuple(missing_flags),
            is_duplicate=False,
            dedup_key=dedup_key,
        )

    def persist(
        self,
        *,
        state_manager: SessionStateManager,
        session_id: str,
        ts_ms: int,
        output: GuardOutput,
    ) -> None:
        """Persist guard-owned session fields.

        Guard writes are non-refreshing by default. TTL refresh is owned by Orchestrator.
        """
        if output.is_duplicate:
            return
        state_manager.update_by_role(
            "guard",
            session_id,
            output.to_state_changes(ts_ms),
            is_allow=False,
        )


def map_tier(
    risk_score: float,
    *,
    policy: PolicySnapshot,
    previous_tier: Optional[DefenseTier],
    in_probation: bool,
) -> DefenseTier:
    """Map risk score to tier using policy thresholds + hysteresis + probation."""
    r = clamp(risk_score, 0.0, 1.0)
    raw = _tier_without_hysteresis(r, policy)
    if previous_tier is None or raw == previous_tier:
        return raw
    if _tier_rank(raw) > _tier_rank(previous_tier):
        return raw
    if in_probation:
        return previous_tier
    cutoff = _downgrade_cutoff(previous_tier, policy)
    if cutoff is None:
        return raw
    if r <= cutoff:
        return raw
    return previous_tier


def clamp(v: float, lo: float, hi: float) -> float:
    """Ref: annex/guard_spec.yaml#math_defs.normalize.clamp"""
    return max(lo, min(v, hi))


def normalize(x: float, min_value: float, max_value: float) -> float:
    """Ref: annex/guard_spec.yaml#math_defs.normalize"""
    if max_value <= min_value:
        return 0.0
    return clamp((x - min_value) / (max_value - min_value), 0.0, 1.0)


def is_unnatural_velocity(v: float) -> float:
    """Ref: annex/guard_spec.yaml#math_defs.is_unnatural_velocity"""
    v_low = 50.0
    v_high = 1500.0
    if v <= v_low:
        return 0.0
    if v >= v_high:
        return 1.0
    return (v - v_low) / (v_high - v_low)


def is_linear_path(linearity_ratio: float, path_ratio: float) -> float:
    """Ref: annex/guard_spec.yaml#math_defs.is_linear_path"""
    return 1.0 if linearity_ratio >= 0.92 and path_ratio <= 1.10 else 0.0


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        num = float(value)
        if num != num:
            return None
        if num in (float("inf"), float("-inf")):
            return None
        return num
    except (TypeError, ValueError):
        return None


def _resolve_feature(
    features: Mapping[str, Any],
    *,
    key: str,
    default: float,
    missing_flag: str,
    missing_flags: list[str],
) -> float:
    value = _to_float(features.get(key))
    if value is None:
        missing_flags.append(missing_flag)
        return default
    return value


def _clip(value: float, lo: float, hi: float) -> tuple[float, bool]:
    clipped = clamp(value, lo, hi)
    return clipped, clipped != value


def _apply_passive_decay(
    *,
    risk_score: float,
    last_guard_ts_ms: Optional[int],
    now_ms: int,
    policy: PolicySnapshot,
    rule_hits: list[str],
) -> float:
    risk = clamp(risk_score, 0.0, 1.0)
    if last_guard_ts_ms is None or now_ms <= last_guard_ts_ms:
        return risk
    inactive_ms = now_ms - last_guard_ts_ms
    threshold_ms = policy.passive_decay_after_inactive_s * 1000
    tick_ms = max(1, policy.passive_decay_tick_s * 1000)
    if inactive_ms <= threshold_ms:
        return risk
    ticks = max(1, int((inactive_ms - threshold_ms) // tick_ms))
    decayed = clamp(risk * (policy.passive_decay_multiplier**ticks), 0.0, 1.0)
    if decayed < risk:
        rule_hits.append("PASSIVE_DECAY_APPLIED")
    return decayed


def _tier_without_hysteresis(risk_score: float, policy: PolicySnapshot) -> DefenseTier:
    if risk_score < policy.t0_max:
        return DefenseTier.T0
    if risk_score < policy.t1_max:
        return DefenseTier.T1
    if risk_score < policy.t2_max:
        return DefenseTier.T2
    return DefenseTier.T3


def _downgrade_cutoff(
    previous_tier: DefenseTier,
    policy: PolicySnapshot,
) -> Optional[float]:
    margin = max(0.0, policy.hysteresis_margin)
    if previous_tier == DefenseTier.T3:
        return clamp(policy.t2_max - margin, 0.0, 1.0)
    if previous_tier == DefenseTier.T2:
        return clamp(policy.t1_max - margin, 0.0, 1.0)
    if previous_tier == DefenseTier.T1:
        return clamp(policy.t0_max - margin, 0.0, 1.0)
    return None


def _tier_rank(tier: DefenseTier) -> int:
    return {
        DefenseTier.T0: 0,
        DefenseTier.T1: 1,
        DefenseTier.T2: 2,
        DefenseTier.T3: 3,
    }[tier]


def _in_probation(state: SessionState, now_ms: int) -> bool:
    return bool(
        state.probation_until_ms is not None and now_ms < state.probation_until_ms
    )


__all__ = [
    "Guard",
    "GuardOutput",
    "map_tier",
    "clamp",
    "normalize",
    "is_unnatural_velocity",
    "is_linear_path",
]
