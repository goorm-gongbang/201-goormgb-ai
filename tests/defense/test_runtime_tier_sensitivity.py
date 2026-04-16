"""Tests verifying the tuned tier-sensitivity parameters for the D0-MVP runtime.

Goals validated here:
  1. T2 is reachable with moderately bot-like signals after a few events.
  2. Neutral / human-like signals do NOT reach T2.
  3. T0/T1 boundaries are preserved at their original values (0.20 / 0.50).
  4. The LINEAR_PATH weight increase makes straight-line paths more impactful.
  5. The configuration changes are non-extreme: strong bot signals reach T3
     only after sustained anomalous activity, not from a single event.

All tests run without Redis or any external infrastructure.
"""

from __future__ import annotations

import math

import pytest

from traffic_master_ai.defense.d0_mvp.brain.guard import Guard, clamp
from traffic_master_ai.defense.d0_mvp.core.constants import (
    GUARD_WEIGHT_DWELL,
    GUARD_WEIGHT_LINEARITY,
    GUARD_WEIGHT_LINEAR_PATH,
    GUARD_WEIGHT_TREMOR,
    GUARD_WEIGHT_VELOCITY,
    RISK_ALPHA,
    TIER_T0_MAX,
    TIER_T1_MAX,
    TIER_T2_MAX,
)
from traffic_master_ai.defense.d0_mvp.core.enums import DefenseTier, FlowState
from traffic_master_ai.defense.d0_mvp.core.models import SessionState
from traffic_master_ai.defense.d0_mvp.events.common import RuntimeEvent
from traffic_master_ai.defense.d0_mvp.policy.snapshot import PolicySnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(ts_ms: int = 1_000) -> RuntimeEvent:
    return RuntimeEvent(
        event_type="API_CALL_OBS",
        ts_ms=ts_ms,
        flow_state=FlowState.S2,
        session_id="test-sess",
        trace_id=f"trace-{ts_ms}",
    )


def _run_guard(
    features: dict,
    n_events: int,
    *,
    external_score: float | None = None,
) -> tuple[float, DefenseTier]:
    """Run Guard n times with fixed features and return (final_risk_score, final_tier).

    State is manually threaded between calls to avoid Redis dependency.
    Events are spaced 500 ms apart (well within the 30s passive-decay threshold).
    """
    guard = Guard()
    policy = PolicySnapshot()  # uses default constants
    state = SessionState()

    for i in range(n_events):
        ev = _event(ts_ms=1_000 + i * 500)
        output = guard.score(
            trace_id=f"trace-{i}",
            event=ev,
            state=state,
            policy=policy,
            features=features,
            external_score=external_score,
        )
        state = SessionState(
            risk_score=output.r_new,
            defense_tier=output.tier,
            last_guard_ts_ms=ev.ts_ms,
        )

    return state.risk_score, state.defense_tier


def _bot_features() -> dict:
    """Strong bot-like features: near-zero tremor, high linearity, fast straight path."""
    return {
        "tremorStdDev": 0.1,
        "linearityRatio": 0.97,
        "avgVelocity": 1800.0,
        "dwellTime": 40.0,
        "pathRatio": 1.04,
    }


def _moderate_bot_features() -> dict:
    """Moderately anomalous features: above-average linearity, no dwell."""
    return {
        "tremorStdDev": 1.0,
        "linearityRatio": 0.80,
        "avgVelocity": 1200.0,
        "dwellTime": 100.0,
        "pathRatio": 1.15,
    }


def _neutral_features() -> dict:
    """Neutral defaults: approximately what a typical human session produces."""
    return {
        "tremorStdDev": 3.0,
        "linearityRatio": 0.50,
        "avgVelocity": 775.0,
        "dwellTime": 1000.0,
        "pathRatio": 1.20,
    }


def _linear_path_features() -> dict:
    """Features that trigger is_linear_path=1.0 with moderate other values."""
    return {
        "tremorStdDev": 3.0,
        "linearityRatio": 0.95,  # >= 0.92 → linear path fires
        "avgVelocity": 600.0,
        "dwellTime": 500.0,
        "pathRatio": 1.08,       # <= 1.10 → linear path fires
    }


# ---------------------------------------------------------------------------
# A. Constant sanity checks
# ---------------------------------------------------------------------------

class TestTuningConstants:
    """Verify the tuned constant values are in place."""

    def test_risk_alpha_raised(self) -> None:
        assert RISK_ALPHA == pytest.approx(0.45), (
            "RISK_ALPHA should be 0.45 for faster EWMA convergence"
        )

    def test_tier_t2_max_lowered(self) -> None:
        assert TIER_T2_MAX == pytest.approx(0.65), (
            "TIER_T2_MAX should be 0.65 so moderately bot-like signals can reach T2"
        )

    def test_tier_thresholds_unchanged(self) -> None:
        assert TIER_T0_MAX == pytest.approx(0.20), "T0 boundary must stay at 0.20"
        assert TIER_T1_MAX == pytest.approx(0.50), "T1 boundary must stay at 0.50"

    def test_guard_weights_sum_to_one(self) -> None:
        total = (
            GUARD_WEIGHT_TREMOR
            + GUARD_WEIGHT_LINEARITY
            + GUARD_WEIGHT_VELOCITY
            + GUARD_WEIGHT_DWELL
            + GUARD_WEIGHT_LINEAR_PATH
        )
        assert math.isclose(total, 1.0, abs_tol=1e-9), (
            f"Guard weights must sum to 1.0, got {total}"
        )

    def test_linear_path_weight_increased(self) -> None:
        assert GUARD_WEIGHT_LINEAR_PATH == pytest.approx(0.20), (
            "LINEAR_PATH weight should be 0.20 (raised from 0.10)"
        )

    def test_tremor_weight_reduced(self) -> None:
        assert GUARD_WEIGHT_TREMOR == pytest.approx(0.30), (
            "TREMOR weight should be 0.30 (reduced from 0.35)"
        )

    def test_dwell_weight_reduced(self) -> None:
        assert GUARD_WEIGHT_DWELL == pytest.approx(0.10), (
            "DWELL weight should be 0.10 (reduced from 0.15)"
        )


# ---------------------------------------------------------------------------
# B. T2 reachability with tuned parameters
# ---------------------------------------------------------------------------

class TestT2Reachability:
    """Verify that T2 is now reachable for anomalous signals."""

    def test_strong_bot_signals_reach_t2_within_4_events(self) -> None:
        """Strong bot-like features should hit T2 in ≤4 events."""
        risk, tier = _run_guard(_bot_features(), n_events=4)
        assert tier in {DefenseTier.T2, DefenseTier.T3}, (
            f"Expected T2 or T3 after 4 strong-bot events, got {tier} (risk={risk:.4f})"
        )

    def test_moderate_bot_signals_reach_t2_within_6_events(self) -> None:
        """Moderately anomalous features should hit T2 in ≤6 events."""
        risk, tier = _run_guard(_moderate_bot_features(), n_events=6)
        assert tier in {DefenseTier.T2, DefenseTier.T3}, (
            f"Expected T2 or T3 after 6 moderate-bot events, got {tier} (risk={risk:.4f})"
        )

    def test_linear_path_features_reach_t2(self) -> None:
        """A session with a straight-line path pattern should reach T2."""
        risk, tier = _run_guard(_linear_path_features(), n_events=8)
        assert tier in {DefenseTier.T2, DefenseTier.T3}, (
            f"Straight-line path should reach T2 within 8 events, got {tier} (risk={risk:.4f})"
        )

    def test_strong_bot_with_external_score_confirms_t2(self) -> None:
        """Bot features + low external score (high botlikeness) → T2 faster."""
        # external_score=0.1 → s_ext_botlikeness=0.9 → stronger combined signal
        risk, tier = _run_guard(_bot_features(), n_events=3, external_score=0.1)
        assert tier in {DefenseTier.T2, DefenseTier.T3}, (
            f"Bot features + external_score=0.1 should reach T2 in 3 events, got {tier}"
        )


# ---------------------------------------------------------------------------
# C. Sanity: neutral signals must NOT reach T2
# ---------------------------------------------------------------------------

class TestNeutralSignalsBelowT2:
    """Verify that human-like / neutral features stay below the T2 boundary."""

    def test_neutral_features_stay_below_t2_after_10_events(self) -> None:
        """10 events with neutral features should not push risk into T2."""
        risk, tier = _run_guard(_neutral_features(), n_events=10)
        assert tier in {DefenseTier.T0, DefenseTier.T1}, (
            f"Neutral features must stay at T0/T1, got {tier} (risk={risk:.4f})"
        )
        assert risk < TIER_T2_MAX, (
            f"Neutral risk {risk:.4f} must be below T2_MAX={TIER_T2_MAX}"
        )

    def test_neutral_features_converge_below_t1_max(self) -> None:
        """Neutral signal EWMA converges well below T1_MAX=0.50."""
        # Run enough events for EWMA to stabilise
        risk, _ = _run_guard(_neutral_features(), n_events=20)
        assert risk < TIER_T1_MAX, (
            f"Neutral risk convergence {risk:.4f} should be below T1_MAX={TIER_T1_MAX}"
        )

    def test_single_bot_event_does_not_immediately_jump_to_t2(self) -> None:
        """A single strong-bot event from a clean session should not jump to T2."""
        risk, tier = _run_guard(_bot_features(), n_events=1)
        # With α=0.45 and s_t≈0.84, r_new ≈ 0.38 → T1, not T2
        assert tier == DefenseTier.T1, (
            f"Single bot event should land in T1, not T2, got {tier} (risk={risk:.4f})"
        )


# ---------------------------------------------------------------------------
# D. T3 reachability: requires sustained strong signals
# ---------------------------------------------------------------------------

class TestT3RequiresSustainedSignals:
    """T3 (≥0.65) should require several consecutive strong signals."""

    def test_t3_not_reached_on_first_event(self) -> None:
        """Even the strongest single event must not produce T3."""
        risk, tier = _run_guard(_bot_features(), n_events=1)
        assert tier != DefenseTier.T3, (
            f"T3 must not be reached in a single event, got {tier} (risk={risk:.4f})"
        )

    def test_t3_not_reached_after_two_strong_events(self) -> None:
        """Two consecutive strong bot events should land in T2, not T3."""
        risk, tier = _run_guard(_bot_features(), n_events=2)
        # After 2 events: r ≈ 0.59 → T2 range (0.50–0.65)
        assert tier != DefenseTier.T3, (
            f"T3 must not be reached after 2 strong events; got {tier} (risk={risk:.4f})"
        )

    def test_strong_bot_reaches_t3_after_sustained_events(self) -> None:
        """Persistent strong bot signals should eventually push into T3."""
        risk, tier = _run_guard(_bot_features(), n_events=5)
        # Convergence ≈ 0.84 >> T2_MAX=0.65 → sustained anomaly → T3
        assert tier == DefenseTier.T3, (
            f"Sustained strong bot signals should reach T3, got {tier} (risk={risk:.4f})"
        )


# ---------------------------------------------------------------------------
# E. LINEAR_PATH weight impact
# ---------------------------------------------------------------------------

class TestLinearPathWeightImpact:
    """Verify the increased LINEAR_PATH weight has measurable effect."""

    def test_linear_path_feature_increases_s_int_vs_non_linear(self) -> None:
        """Same features but straight vs non-straight path → higher s_int when straight."""
        straight = _linear_path_features()
        curved = {**straight, "linearityRatio": 0.80, "pathRatio": 1.40}

        risk_straight, _ = _run_guard(straight, n_events=5)
        risk_curved, _ = _run_guard(curved, n_events=5)

        assert risk_straight > risk_curved, (
            f"Straight-line path (risk={risk_straight:.4f}) should produce higher risk "
            f"than curved path (risk={risk_curved:.4f})"
        )
