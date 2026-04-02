"""Environment-variable backed default constants for D0-MVP.

All values are extracted from:
- L0/l0_core.yaml (TTL, timeout, idempotency)
- L0/l0_defense_policy.yaml (risk model, tiering, hysteresis, probation)
- L2/obs_opt/policy_v1.yaml (parameters section)
- L1/runtime/state.yaml (TTL, dedup)

Convention: TM_* env-var overrides are read lazily via `get()` helpers.
"""

from __future__ import annotations

import os
from typing import Any


def _env(key: str, default: Any) -> Any:
    """Read env var with type-preserving default."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes")
    return raw


def _env_first(keys: tuple[str, ...], default: str) -> str:
    """Read the first defined env var from an ordered key list."""
    for key in keys:
        raw = os.environ.get(key)
        if raw is not None:
            return raw
    return default


# ===================================================================
# Risk Model — L0/l0_defense_policy.yaml §3, policy_v1 §risk
# ===================================================================
RISK_ALPHA: float = _env("TM_RISK_ALPHA", 0.30)
PASSIVE_DECAY_AFTER_INACTIVE_S: int = _env("TM_PASSIVE_DECAY_INACTIVE_S", 30)
PASSIVE_DECAY_MULTIPLIER: float = _env("TM_PASSIVE_DECAY_MULTIPLIER", 0.98)
PASSIVE_DECAY_TICK_S: int = _env("TM_PASSIVE_DECAY_TICK_S", 5)

# ===================================================================
# Tiering — L0/l0_defense_policy.yaml §4, policy_v1 §tiering
# ===================================================================
TIER_T0_MAX: float = _env("TM_T0_MAX", 0.20)
TIER_T1_MAX: float = _env("TM_T1_MAX", 0.50)
TIER_T2_MAX: float = _env("TM_T2_MAX", 0.80)
TIER_HYSTERESIS_MARGIN: float = _env("TM_TIER_HYSTERESIS_MARGIN", 0.02)

# ===================================================================
# Probation — L0/l0_defense_policy.yaml §5
# ===================================================================
S3_PROBATION_SECONDS: int = _env("TM_S3_PROBATION_SECONDS", 45)

# ===================================================================
# Redis TTL — L1/runtime/state.yaml §ttl
# ===================================================================
SESSION_STATE_TTL_SECONDS: int = _env("TM_SESSION_STATE_TTL_SECONDS", 1800)
BLOCK_TTL_SECONDS: int = _env("TM_BLOCK_TTL_SECONDS", 1800)
S3_GRACE_TTL_SECONDS: int = _env("TM_S3_GRACE_TTL_SECONDS", 180)
SESSION_DIST_LOCK_ENABLED: bool = _env("TM_SESSION_DIST_LOCK_ENABLED", True)
SESSION_DIST_LOCK_WAIT_MS: int = _env("TM_SESSION_DIST_LOCK_WAIT_MS", 200)
SESSION_DIST_LOCK_TTL_MS: int = _env("TM_SESSION_DIST_LOCK_TTL_MS", 2000)

# ===================================================================
# Dedup — L1/runtime/events.yaml §dedup
# ===================================================================
DEDUP_TS_BUCKET_MS: int = _env("TM_DEDUP_TS_BUCKET_MS", 200)
DEDUP_TTL_SECONDS: int = _env("TM_DEDUP_TTL_SECONDS", 600)

# ===================================================================
# Throttle — policy_v1 §throttle
# ===================================================================
THROTTLE_DELAY_MS_T0: int = 0
THROTTLE_DELAY_MS_T1: int = _env("TM_THROTTLE_DELAY_MS_T1", 80)
THROTTLE_DELAY_MS_T2: int = _env("TM_THROTTLE_DELAY_MS_T2", 250)
THROTTLE_DELAY_MS_T3: int = 0
THROTTLE_MAX_DELAY_MS: int = _env("TM_THROTTLE_MAX_DELAY_MS", 2000)

THROTTLE_INCLUDE_PATH_PREFIXES: list[str] = [
    "/api/catalog",
    "/api/events",
    "/api/queue",
    "/api/sections",
    "/api/blocks",
    "/api/areas",
    "/api/seatmap",
    "/api/seats",
    "/api/availability",
    "/api/recommend",
    "/api/search",
]

THROTTLE_EXCLUDE_PATH_PREFIXES: list[str] = [
    "/api/hold",
    "/api/order",
    "/api/payment",
    "/api/confirm",
    "/defense/challenge/",
    "/health",
]

# ===================================================================
# Challenge — policy_v1 §challenge
# ===================================================================
CHALLENGE_GAME_ID: str = "BASEBALL_CATCH"
CHALLENGE_TTL_SECONDS: int = _env("TM_CHALLENGE_TTL_SECONDS", 15)
CHALLENGE_VERIFY_TIMEOUT_MS: int = _env("TM_CHALLENGE_VERIFY_TIMEOUT_MS", 200)
CHALLENGE_VERIFY_UNAVAILABLE_MODE: str = _env(
    "TM_S3_VERIFY_UNAVAILABLE_MODE", "fail_close"
)
CHALLENGE_VERIFY_UNAVAILABLE_HTTP_STATUS: int = _env(
    "TM_S3_VERIFY_UNAVAILABLE_HTTP_STATUS", 503
)
CHALLENGE_CATCH_RADIUS_PX: int = _env("TM_CHALLENGE_CATCH_RADIUS_PX", 48)
CHALLENGE_TIMING_WINDOW_MS: int = _env("TM_CHALLENGE_TIMING_WINDOW_MS", 320)
CHALLENGE_MAX_ATTEMPTS: int = _env("TM_CHALLENGE_MAX_ATTEMPTS", 3)
CHALLENGE_COOLDOWN_MS_1: int = _env("TM_CHALLENGE_COOLDOWN_MS_1", 0)
CHALLENGE_COOLDOWN_MS_2: int = _env("TM_CHALLENGE_COOLDOWN_MS_2", 2500)
CHALLENGE_HALT_SECONDS: int = _env("TM_CHALLENGE_HALT_SECONDS", 30)
CHALLENGE_ATTEMPT_WINDOW_SECONDS: int = _env("TM_CHALLENGE_ATTEMPT_WINDOW_SECONDS", 60)

# ===================================================================
# Block — policy_v1 §block
# ===================================================================
BLOCK_HTTP_STATUS: int = 403
BLOCK_REASON_CODE: str = "BLOCKED"

# ===================================================================
# Turnstile — policy_v1 §turnstile
# ===================================================================
TURNSTILE_ENABLED: bool = _env("TM_TURNSTILE_ENABLED", True)
TURNSTILE_VERIFY_TIMEOUT_MS: int = _env("TM_TURNSTILE_VERIFY_TIMEOUT_MS", 500)
TURNSTILE_MAX_RETRIES: int = 1
TURNSTILE_VERIFY_BACKOFF_MS: int = _env("TM_TURNSTILE_VERIFY_BACKOFF_MS", 30)
TURNSTILE_CACHE_TTL_SECONDS: int = _env("TM_TURNSTILE_CACHE_TTL_SECONDS", 600)
TURNSTILE_EXTERNAL_SCORE_ON_FAILURE: float = 0.50
TURNSTILE_MAX_RUNS_PER_SESSION: int = _env("TM_TURNSTILE_MAX_RUNS_PER_SESSION", 1)
TURNSTILE_COOLDOWN_SECONDS: int = _env("TM_TURNSTILE_COOLDOWN_SECONDS", 30)

# ===================================================================
# Guard — annex/guard_spec.yaml §internal_score.weights
# ===================================================================
GUARD_WEIGHT_TREMOR: float = 0.35
GUARD_WEIGHT_LINEARITY: float = 0.25
GUARD_WEIGHT_VELOCITY: float = 0.15
GUARD_WEIGHT_DWELL: float = 0.15
GUARD_WEIGHT_LINEAR_PATH: float = 0.10
GUARD_STEP_RISK_EXT_WEIGHT: float = 0.30
GUARD_STEP_RISK_INT_WEIGHT: float = 0.70
GUARD_FEATURE_SUMMARY_MAX_EPM: int = _env("TM_FEATURE_SUMMARY_MAX_EPM", 12)

# ===================================================================
# Analyzer derived signals — annex/analyzer_spec.yaml §derived_signals
# ===================================================================
RAPID_HV_WINDOW_MS: int = _env("TM_RAPID_HV_WINDOW_MS", 1500)
RAPID_HV_THRESHOLD: int = _env("TM_RAPID_HV_THRESHOLD", 3)
SCAN_WINDOW_MS: int = _env("TM_SCAN_WINDOW_MS", 2000)
SCAN_THRESHOLD: int = _env("TM_SCAN_THRESHOLD", 8)
S3_FAIL_BURST_WINDOW_S: int = _env("TM_S3_FAIL_BURST_WINDOW_S", 60)
S3_FAIL_BURST_THRESHOLD: int = _env("TM_S3_FAIL_BURST_THRESHOLD", 2)

# ===================================================================
# Policy baseline version
# ===================================================================
DEFAULT_POLICY_VERSION: str = "v2.0.0-mvp"

# ===================================================================
# Audit — L0/l0_core.yaml §7
# ===================================================================
AUDIT_FILENAME: str = "logs/decision_audit.jsonl"
WAREHOUSE_FILENAME: str = "logs/defense_audit_events.jsonl"
AUDIT_COLLECTOR_CHECKPOINT_FILENAME: str = "logs/decision_audit.checkpoint"
AUDIT_RETENTION_DAYS: int = _env("TM_AUDIT_RETENTION_DAYS", 7)

# ===================================================================
# Idempotency — L0/l0_core.yaml §4
# ===================================================================
IDEMPOTENCY_TTL_SECONDS: int = _env("TM_IDEMPOTENCY_TTL_SECONDS", 600)

# ===================================================================
# Timeout — L0/l0_core.yaml §3
# ===================================================================
MAX_RETRY_PER_STATE: int = 3
SEAT_HOLD_TTL_MS: int = 300_000
PAYMENT_WINDOW_TTL_MS: int = 300_000

# ===================================================================
# Test hooks
# ===================================================================
TEST_MODE_ENABLED: bool = _env("TM_TEST_MODE_ENABLED", False)

# ===================================================================
# Offline LLM — L1/llm/defense_llm_ssot.yaml
# ===================================================================
OFFLINE_LLM_TIMEOUT_MS: int = _env("TM_OFFLINE_LLM_TIMEOUT_MS", 2500)
OFFLINE_LLM_MAX_RETRIES: int = _env("TM_OFFLINE_LLM_MAX_RETRIES", 1)
OFFLINE_LLM_RETRY_BACKOFF_MS: int = _env("TM_OFFLINE_LLM_RETRY_BACKOFF_MS", 100)
OFFLINE_LLM_MAX_OUTPUT_TOKENS: int = _env("TM_OFFLINE_LLM_MAX_OUTPUT_TOKENS", 1200)
OFFLINE_LLM_MODEL: str = _env("TM_OFFLINE_LLM_MODEL", "gpt-5-mini")
OFFLINE_LLM_MAX_CALLS_PER_RUN: int = _env("TM_OFFLINE_LLM_MAX_CALLS_PER_RUN", 2)
OFFLINE_LLM_INPUT_MAX_BYTES: int = _env("TM_OFFLINE_LLM_INPUT_MAX_BYTES", 8000)
OFFLINE_LLM_MAX_SAMPLE_TRACES: int = _env("TM_OFFLINE_LLM_MAX_SAMPLE_TRACES", 50)
OFFLINE_LLM_QPS_LIMIT: int = _env("TM_OFFLINE_LLM_QPS_LIMIT", 5)
OFFLINE_LLM_CONCURRENCY_LIMIT: int = _env("TM_OFFLINE_LLM_CONCURRENCY_LIMIT", 2)
OFFLINE_LLM_CB_WINDOW_SECONDS: int = _env("TM_OFFLINE_LLM_CB_WINDOW_SECONDS", 300)
OFFLINE_LLM_CB_TIMEOUT_RATE_DISABLE: float = _env(
    "TM_OFFLINE_LLM_CB_TIMEOUT_RATE_DISABLE", 0.20
)
OFFLINE_LLM_CB_ERROR_RATE_DISABLE: float = _env(
    "TM_OFFLINE_LLM_CB_ERROR_RATE_DISABLE", 0.20
)
OFFLINE_LLM_CB_DISABLE_SECONDS: int = _env("TM_OFFLINE_LLM_CB_DISABLE_SECONDS", 900)
EVAL_MIN_EVENTS_TOTAL: int = _env("TM_EVAL_MIN_EVENTS_TOTAL", 2000)
EVAL_MIN_UNIQUE_SESSIONS: int = _env("TM_EVAL_MIN_UNIQUE_SESSIONS", 200)
EVAL_MIN_THROTTLE_EVENTS: int = _env("TM_EVAL_MIN_THROTTLE_EVENTS", 100)
EVAL_MIN_S3_EVENTS: int = _env("TM_EVAL_MIN_S3_EVENTS", 100)
EVAL_COOLDOWN_SECONDS: int = _env("TM_EVAL_COOLDOWN_SECONDS", 600)
SUM_MIN_EVENTS_TOTAL: int = _env("TM_SUM_MIN_EVENTS_TOTAL", 500)
SUM_COOLDOWN_SECONDS: int = _env("TM_SUM_COOLDOWN_SECONDS", 300)

# ===================================================================
# Offline observability / optimization logs
# ===================================================================
OFFLINE_OPT_AUDIT_FILENAME: str = _env_first(
    ("TM_OFFLINE_OPT_AUDIT_FILENAME", "TM_OFFLINE_LLM_AUDIT_PATH"),
    "/tmp/logs/offline_optimization_audit.jsonl",
)
OFFLINE_AUDIT_SUMMARY_FILENAME: str = _env(
    "TM_OFFLINE_AUDIT_SUMMARY_FILENAME",
    "/tmp/logs/offline_audit_summary.jsonl",
)
POLICY_STORE_FILENAME: str = _env(
    "TM_POLICY_STORE_FILENAME",
    "/tmp/logs/policy_store.json",
)
POLICY_CACHE_SECONDS: int = _env("TM_POLICY_CACHE_SECONDS", 5)
