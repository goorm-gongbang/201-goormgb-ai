"""Frozen policy snapshot for a single evaluation cycle.

Ref: L2/obs_opt/policy_v1.yaml — the full parameter set.
     L0/l0_defense_policy.yaml — invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..core.constants import (
    BLOCK_HTTP_STATUS,
    BLOCK_REASON_CODE,
    BLOCK_TTL_SECONDS,
    CHALLENGE_COOLDOWN_MS_1,
    CHALLENGE_COOLDOWN_MS_2,
    CHALLENGE_GAME_ID,
    CHALLENGE_HALT_SECONDS,
    CHALLENGE_MAX_ATTEMPTS,
    CHALLENGE_ATTEMPT_WINDOW_SECONDS,
    CHALLENGE_TTL_SECONDS,
    CHALLENGE_CATCH_RADIUS_PX,
    CHALLENGE_TIMING_WINDOW_MS,
    CHALLENGE_VERIFY_TIMEOUT_MS,
    PASSIVE_DECAY_AFTER_INACTIVE_S,
    PASSIVE_DECAY_MULTIPLIER,
    PASSIVE_DECAY_TICK_S,
    RISK_ALPHA,
    S3_GRACE_TTL_SECONDS,
    S3_PROBATION_SECONDS,
    SESSION_STATE_TTL_SECONDS,
    THROTTLE_DELAY_MS_T0,
    THROTTLE_DELAY_MS_T1,
    THROTTLE_DELAY_MS_T2,
    THROTTLE_DELAY_MS_T3,
    THROTTLE_INCLUDE_PATH_PREFIXES,
    THROTTLE_EXCLUDE_PATH_PREFIXES,
    THROTTLE_MAX_DELAY_MS,
    TIER_HYSTERESIS_MARGIN,
    TIER_T0_MAX,
    TIER_T1_MAX,
    TIER_T2_MAX,
    TURNSTILE_CACHE_TTL_SECONDS,
    TURNSTILE_ENABLED,
    TURNSTILE_EXTERNAL_SCORE_ON_FAILURE,
    TURNSTILE_MAX_RETRIES,
    TURNSTILE_COOLDOWN_SECONDS,
    TURNSTILE_MAX_RUNS_PER_SESSION,
    TURNSTILE_VERIFY_BACKOFF_MS,
    TURNSTILE_VERIFY_TIMEOUT_MS,
    DEFAULT_POLICY_VERSION,
)


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    """Immutable policy parameters for a single evaluation pass.

    Ref: L2/obs_opt/policy_v1.yaml#parameters
    Frozen to guarantee no mid-evaluation mutation.
    """

    # --- meta ---
    policy_version: str = DEFAULT_POLICY_VERSION

    # --- risk ---
    ewma_alpha: float = RISK_ALPHA
    passive_decay_after_inactive_s: int = PASSIVE_DECAY_AFTER_INACTIVE_S
    passive_decay_multiplier: float = PASSIVE_DECAY_MULTIPLIER
    passive_decay_tick_s: int = PASSIVE_DECAY_TICK_S
    probation_seconds_after_s3_pass: int = S3_PROBATION_SECONDS

    # --- tiering ---
    t0_max: float = TIER_T0_MAX
    t1_max: float = TIER_T1_MAX
    t2_max: float = TIER_T2_MAX
    hysteresis_margin: float = TIER_HYSTERESIS_MARGIN

    # --- turnstile ---
    turnstile_enabled: bool = TURNSTILE_ENABLED
    turnstile_secondary_trigger_enabled: bool = False
    turnstile_verify_timeout_ms: int = TURNSTILE_VERIFY_TIMEOUT_MS
    turnstile_verify_max_retries: int = TURNSTILE_MAX_RETRIES
    turnstile_verify_backoff_ms: int = TURNSTILE_VERIFY_BACKOFF_MS
    turnstile_cache_ttl_s: int = TURNSTILE_CACHE_TTL_SECONDS
    turnstile_external_score_on_failure: float = TURNSTILE_EXTERNAL_SCORE_ON_FAILURE
    turnstile_max_runs_per_session: int = TURNSTILE_MAX_RUNS_PER_SESSION
    turnstile_cooldown_seconds: int = TURNSTILE_COOLDOWN_SECONDS

    # --- planner action_matrix ---
    action_t0: str = "NONE"
    action_t1: str = "THROTTLE"
    action_t2: str = "THROTTLE"
    action_t3: str = "BLOCK"

    # --- S3 gate (Planner) ---
    require_s3_for_states: tuple[str, ...] = ("S4", "S5")

    # --- throttle ---
    throttle_delay_ms_t0: int = THROTTLE_DELAY_MS_T0
    throttle_delay_ms_t1: int = THROTTLE_DELAY_MS_T1
    throttle_delay_ms_t2: int = THROTTLE_DELAY_MS_T2
    throttle_delay_ms_t3: int = THROTTLE_DELAY_MS_T3
    throttle_max_delay_ms: int = THROTTLE_MAX_DELAY_MS

    # --- challenge ---
    challenge_game_id: str = CHALLENGE_GAME_ID
    challenge_ttl_seconds: int = CHALLENGE_TTL_SECONDS
    challenge_verify_timeout_ms: int = CHALLENGE_VERIFY_TIMEOUT_MS
    challenge_catch_radius_px: int = CHALLENGE_CATCH_RADIUS_PX
    challenge_timing_window_ms: int = CHALLENGE_TIMING_WINDOW_MS
    challenge_max_attempts: int = CHALLENGE_MAX_ATTEMPTS
    challenge_attempt_window_s: int = CHALLENGE_ATTEMPT_WINDOW_SECONDS
    challenge_cooldown_ms_1: int = CHALLENGE_COOLDOWN_MS_1
    challenge_cooldown_ms_2: int = CHALLENGE_COOLDOWN_MS_2
    challenge_halt_seconds: int = CHALLENGE_HALT_SECONDS
    s3_grace_ttl_seconds: int = S3_GRACE_TTL_SECONDS

    # --- block ---
    block_http_status: int = BLOCK_HTTP_STATUS
    block_reason_code: str = BLOCK_REASON_CODE
    block_ttl_seconds: int = BLOCK_TTL_SECONDS

    # --- session ---
    session_state_ttl_seconds: int = SESSION_STATE_TTL_SECONDS

    # --- throttle endpoint scoping (Gap 6: policy-driven) ---
    throttle_include_path_prefixes: tuple[str, ...] = tuple(THROTTLE_INCLUDE_PATH_PREFIXES)
    throttle_exclude_path_prefixes: tuple[str, ...] = tuple(THROTTLE_EXCLUDE_PATH_PREFIXES)

    # --- feature flags (MVP invariants) ---
    runtime_llm_enabled: bool = False
    dynamic_challenge_enabled: bool = False
    honey_enabled: bool = False
    gate_enabled: bool = False
    sandbox_enabled: bool = False
    s3_challenge_fixed: bool = True

    def throttle_delay_for_tier(self, tier_value: str) -> int:
        """Return delay_ms for a given tier string.

        Ref: policy_v1.yaml#throttle.delay_ms
        """
        return {
            "T0": self.throttle_delay_ms_t0,
            "T1": self.throttle_delay_ms_t1,
            "T2": self.throttle_delay_ms_t2,
            "T3": self.throttle_delay_ms_t3,
        }.get(tier_value, 0)

    def action_for_tier(self, tier_value: str) -> str:
        """Return default action for a given tier string.

        Ref: policy_v1.yaml#planner.action_matrix
        """
        return {
            "T0": self.action_t0,
            "T1": self.action_t1,
            "T2": self.action_t2,
            "T3": self.action_t3,
        }.get(tier_value, "NONE")

    def validate(self) -> list[str]:
        """Run policy_v1.yaml#validation invariant checks.

        Returns list of violation messages (empty = pass).
        """
        errors: list[str] = []

        # monotonic_thresholds: T0_max < T1_max < T2_max < 1.0
        if not (self.t0_max < self.t1_max < self.t2_max < 1.0):
            errors.append(
                f"Non-monotonic thresholds: {self.t0_max}, {self.t1_max}, {self.t2_max}"
            )

        # throttle delay T2 >= T1
        if self.throttle_delay_ms_t2 < self.throttle_delay_ms_t1:
            errors.append(
                f"throttle T2 ({self.throttle_delay_ms_t2}) < T1 ({self.throttle_delay_ms_t1})"
            )

        # cooldown monotonic
        if self.challenge_cooldown_ms_2 < self.challenge_cooldown_ms_1:
            errors.append(
                f"cooldown second ({self.challenge_cooldown_ms_2}) < first ({self.challenge_cooldown_ms_1})"
            )

        if self.turnstile_max_runs_per_session < 1:
            errors.append("turnstile_max_runs_per_session must be >= 1")
        if self.turnstile_cooldown_seconds < 0:
            errors.append("turnstile_cooldown_seconds must be >= 0")

        # MVP reject_if
        if self.runtime_llm_enabled:
            errors.append("runtime_llm_enabled must be false in MVP")
        if self.dynamic_challenge_enabled:
            errors.append("dynamic_challenge_enabled must be false in MVP")

        return errors
