from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from traffic_master_ai.defense.backoffice_copilot.storage import (
    PolicyProjectionApplyResult,
)
from traffic_master_ai.defense.d0_mvp.policy.projection_reconciler import (
    POLICY_PROJECTION_RECONCILER_LOCK_KEY,
    PolicyProjectionReconciler,
    PolicyProjectionReconcilerConfig,
    load_policy_projection_reconciler_config_from_env,
)
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis


class _FakeAuthority:
    def __init__(self) -> None:
        self.calls = 0

    def refresh_current_runtime_projection(self) -> PolicyProjectionApplyResult:
        self.calls += 1
        return PolicyProjectionApplyResult(
            projected_policy_versions=("policy-v1",),
            version_index=("policy-v1",),
            wrote_rollout_state=True,
        )


class PolicyProjectionReconcilerTests(unittest.TestCase):
    def test_reconciler_refreshes_projection_and_releases_lock(self) -> None:
        redis = InMemoryRedis()
        authority = _FakeAuthority()
        reconciler = PolicyProjectionReconciler(
            redis=redis,
            authority_service=authority,
            config=PolicyProjectionReconcilerConfig(
                enabled=True,
                interval_seconds=60,
                lock_ttl_seconds=55,
            ),
        )

        result = reconciler.reconcile_once()

        self.assertEqual(result.status, "refreshed")
        self.assertEqual(authority.calls, 1)
        self.assertIsNone(redis.get(POLICY_PROJECTION_RECONCILER_LOCK_KEY))
        self.assertIsNotNone(result.projection_result)
        self.assertTrue(result.projection_result.wrote_rollout_state)

    def test_reconciler_skips_when_lock_is_held(self) -> None:
        redis = InMemoryRedis()
        redis.set(POLICY_PROJECTION_RECONCILER_LOCK_KEY, "other-pod", ex=60, nx=True)
        authority = _FakeAuthority()
        reconciler = PolicyProjectionReconciler(
            redis=redis,
            authority_service=authority,
            config=PolicyProjectionReconcilerConfig(
                enabled=True,
                interval_seconds=60,
                lock_ttl_seconds=55,
            ),
        )

        result = reconciler.reconcile_once()

        self.assertEqual(result.status, "lock_missed")
        self.assertEqual(authority.calls, 0)
        self.assertEqual(redis.get(POLICY_PROJECTION_RECONCILER_LOCK_KEY), "other-pod")

    def test_reconciler_config_enables_only_for_strict_pg_and_real_redis(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TM_PG_URL": "postgresql://user:pass@localhost:5432/tm",
                "TM_REDIS_URL": "redis://localhost:6379/0",
            },
            clear=True,
        ):
            enabled = load_policy_projection_reconciler_config_from_env(
                strict_authority=True,
                redis_backend="redis",
            )
            non_strict = load_policy_projection_reconciler_config_from_env(
                strict_authority=False,
                redis_backend="redis",
            )
            memory_backend = load_policy_projection_reconciler_config_from_env(
                strict_authority=True,
                redis_backend="memory",
            )

        self.assertTrue(enabled.enabled)
        self.assertEqual(enabled.interval_seconds, 60)
        self.assertFalse(non_strict.enabled)
        self.assertFalse(memory_backend.enabled)

    def test_reconciler_config_can_be_disabled_by_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TM_PG_URL": "postgresql://user:pass@localhost:5432/tm",
                "TM_REDIS_URL": "redis://localhost:6379/0",
                "TM_POLICY_PROJECTION_RECONCILER_DISABLED": "true",
            },
            clear=True,
        ):
            config = load_policy_projection_reconciler_config_from_env(
                strict_authority=True,
                redis_backend="redis",
            )

        self.assertFalse(config.enabled)


if __name__ == "__main__":
    unittest.main()
