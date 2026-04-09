"""Centralized Redis keyspace definitions grouped by runtime function."""

from __future__ import annotations

SESSION_KEY_PREFIX = "tm:decision-state:session:"
S3_GRACE_KEY_PREFIX = "tm:challenge-grace:s3:"
SESSION_LOCK_KEY_PREFIX = "tm:decision-state-lock:session:"

BLOCK_KEY_PREFIX = "tm:block-state:session:"
DEDUP_KEY_PREFIX = "tm:event-dedup:"
ETL_PROCESSED_KEY_PREFIX = "tm:etl:processed:s3:"
ANALYZER_WINDOW_KEY_PREFIX = "tm:scoring-window:"

POLICY_VERSION_KEY_PREFIX = "tm:decision-policy:version:"
POLICY_ROLLOUT_STATE_KEY = "tm:decision-policy:rollout-state"
POLICY_VERSION_INDEX_KEY = "tm:decision-policy:version-index"

CHALLENGE_KEY_PREFIX = "tm:s3-challenge:"
CHALLENGE_ATTEMPT_KEY_PREFIX = "tm:s3-challenge:attempt:"

TURNSTILE_CACHE_KEY_PREFIX = "tm:turnstile-verdict:"
TURNSTILE_RUN_KEY_PREFIX = "tm:turnstile-run:"
