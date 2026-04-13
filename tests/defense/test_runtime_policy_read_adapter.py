from __future__ import annotations

import json
import unittest

from traffic_master_ai.defense.d0_mvp.api.runtime import (
    DefenseRuntime,
    RuntimeAPIError,
    build_evaluate_request,
)
from traffic_master_ai.defense.d0_mvp.policy.loader import (
    InMemoryPolicyStore,
    PolicyLoader,
    RedisPolicyStore,
    RuntimePolicyAuthorityError,
    snapshot_to_document,
)
from traffic_master_ai.defense.d0_mvp.policy.runtime_read_adapter import (
    RuntimeProjectionDecodeError,
    RuntimeProjectionNotFoundError,
    RuntimePolicyReadAdapter,
    RuntimeProjectionStaleError,
    decode_runtime_projected_policy_document,
    decode_runtime_projected_rollout_state,
    ensure_runtime_rollout_state_is_fresh,
    parse_runtime_projected_payload,
)
from traffic_master_ai.defense.d0_mvp.policy.snapshot import PolicySnapshot
from traffic_master_ai.defense.d0_mvp.state.keyspace import POLICY_ROLLOUT_STATE_KEY
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis


def _policy_doc(version: str) -> dict[str, object]:
    return snapshot_to_document(PolicySnapshot(policy_version=version))


class RuntimePolicyReadAdapterTests(unittest.TestCase):
    def test_decode_contract_matches_task_12_projection_payloads(self) -> None:
        policy_doc = decode_runtime_projected_policy_document(
            {
                "schemaVersion": "policy.v1",
                "parameters": {"planner": {"action_matrix": {"T0": "NONE"}}},
                "flags": {"runtime_llm_enabled": False},
            }
        )
        rollout_state = decode_runtime_projected_rollout_state(
            {
                "stage": "CANARY",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "ratio": 0.05,
                "updated_at_ms": 1710000000000,
            }
        )

        self.assertEqual(policy_doc.schema_version, "policy.v1")
        self.assertIn("planner", policy_doc.parameters)
        self.assertEqual(rollout_state.base_policy_version, "policy-v1")
        self.assertEqual(rollout_state.candidate_policy_version, "policy-v2")
        self.assertIsNone(rollout_state.projection_refreshed_at_ms)

    def test_decode_invalid_projection_payloads_raise_typed_contract_error(self) -> None:
        with self.assertRaises(RuntimeProjectionDecodeError):
            decode_runtime_projected_policy_document(
                {
                    "schemaVersion": "",
                    "parameters": {},
                }
            )

        with self.assertRaises(RuntimeProjectionDecodeError):
            decode_runtime_projected_rollout_state(
                {
                    "stage": "CANARY",
                    "base_policy_version": "policy-v1",
                    "candidate_policy_version": "policy-v2",
                    "ratio": 3.0,
                    "updated_at_ms": 1710000000000,
                }
            )

    def test_parse_runtime_projected_payload_accepts_json_strings_and_bytes(self) -> None:
        self.assertEqual(
            parse_runtime_projected_payload('{"schemaVersion":"policy.v1","parameters":{}}'),
            {"schemaVersion": "policy.v1", "parameters": {}},
        )
        self.assertEqual(
            parse_runtime_projected_payload(b'{"stage":"FULL","base_policy_version":"policy-v1","ratio":0.0,"updated_at_ms":1}'),
            {
                "stage": "FULL",
                "base_policy_version": "policy-v1",
                "ratio": 0.0,
                "updated_at_ms": 1,
            },
        )
        self.assertIsNone(parse_runtime_projected_payload("not-json"))

    def test_policy_loader_reads_primary_redis_projection_and_resolves_candidate_policy(self) -> None:
        redis = InMemoryRedis()
        store = RedisPolicyStore(redis)
        store.save_policy_version("policy-v2", _policy_doc("policy-v2"))
        store.set_rollout_state(
            {
                "stage": "CANARY",
                "base_policy_version": PolicySnapshot().policy_version,
                "candidate_policy_version": "policy-v2",
                "ratio": 1.0,
                "updated_at_ms": 1710000000000,
            }
        )

        loader = PolicyLoader(store=store, cache_seconds=0)
        loaded = loader.load("session-1")

        self.assertEqual(loaded.policy_version, "policy-v2")
        self.assertIsInstance(loader.read_adapter, RuntimePolicyReadAdapter)

    def test_policy_loader_does_not_broad_fallback_to_file_store_when_primary_projection_doc_is_missing(self) -> None:
        redis = InMemoryRedis()
        fallback = InMemoryPolicyStore()
        fallback.save_policy_version("policy-v2", _policy_doc("policy-v2"))
        store = RedisPolicyStore(redis, fallback=fallback)
        store.set_rollout_state(
            {
                "stage": "CANARY",
                "base_policy_version": PolicySnapshot().policy_version,
                "candidate_policy_version": "policy-v2",
                "ratio": 1.0,
                "updated_at_ms": 1710000001234,
            }
        )

        loader = PolicyLoader(store=store, cache_seconds=0)
        loaded = loader.load("session-2")

        self.assertEqual(loaded.policy_version, PolicySnapshot().policy_version)

    def test_invalid_primary_rollout_projection_falls_back_to_baseline_without_using_store_fallback(self) -> None:
        redis = InMemoryRedis()
        fallback = InMemoryPolicyStore()
        fallback.set_rollout_state(
            {
                "stage": "CANARY",
                "base_policy_version": PolicySnapshot().policy_version,
                "candidate_policy_version": "policy-v2",
                "ratio": 1.0,
                "updated_at_ms": 1710000001234,
            }
        )
        fallback.save_policy_version("policy-v2", _policy_doc("policy-v2"))
        store = RedisPolicyStore(redis, fallback=fallback)
        redis.set(
            POLICY_ROLLOUT_STATE_KEY,
            json.dumps(
                {
                    "stage": "BROKEN",
                    "base_policy_version": "",
                    "candidate_policy_version": "policy-v2",
                    "ratio": 3.0,
                    "updated_at_ms": "bad",
                }
            ),
        )

        loader = PolicyLoader(store=store, cache_seconds=0)
        loaded = loader.load("session-3")

        self.assertEqual(loaded.policy_version, PolicySnapshot().policy_version)

    def test_runtime_rollout_projection_staleness_guard_raises_typed_error(self) -> None:
        projected = decode_runtime_projected_rollout_state(
            {
                "stage": "CANARY",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "ratio": 0.05,
                "updated_at_ms": 1000,
            }
        )

        with self.assertRaises(RuntimeProjectionStaleError):
            ensure_runtime_rollout_state_is_fresh(
                projected,
                max_staleness_ms=100,
                now_ms=2000,
            )

    def test_runtime_rollout_projection_staleness_guard_prefers_projection_refresh_timestamp(self) -> None:
        projected = decode_runtime_projected_rollout_state(
            {
                "stage": "CANARY",
                "base_policy_version": "policy-v1",
                "candidate_policy_version": "policy-v2",
                "ratio": 0.05,
                "updated_at_ms": 1000,
                "projection_refreshed_at_ms": 1950,
            }
        )

        ensure_runtime_rollout_state_is_fresh(
            projected,
            max_staleness_ms=100,
            now_ms=2000,
        )

    def test_policy_loader_can_drop_stale_rollout_projection_before_resolution(self) -> None:
        redis = InMemoryRedis()
        store = RedisPolicyStore(redis)
        store.save_policy_version("policy-v2", _policy_doc("policy-v2"))
        store.set_rollout_state(
            {
                "stage": "CANARY",
                "base_policy_version": PolicySnapshot().policy_version,
                "candidate_policy_version": "policy-v2",
                "ratio": 1.0,
                "updated_at_ms": 1000,
            }
        )

        loader = PolicyLoader(
            store=store,
            cache_seconds=0,
            projection_max_staleness_ms=100,
        )
        loaded = loader.load("session-4")

        self.assertEqual(loaded.policy_version, PolicySnapshot().policy_version)

    def test_require_projected_rollout_state_raises_when_primary_projection_is_missing(self) -> None:
        adapter = RuntimePolicyReadAdapter(RedisPolicyStore(InMemoryRedis()))

        with self.assertRaises(RuntimeProjectionNotFoundError):
            adapter.require_projected_rollout_state()

    def test_strict_policy_loader_raises_typed_authority_error_when_projection_is_missing(self) -> None:
        loader = PolicyLoader(
            store=RedisPolicyStore(InMemoryRedis()),
            cache_seconds=0,
            strict_authority=True,
        )

        with self.assertRaises(RuntimePolicyAuthorityError):
            loader.load("session-strict-missing")

    def test_strict_policy_loader_raises_on_stale_rollout_projection(self) -> None:
        redis = InMemoryRedis()
        store = RedisPolicyStore(redis)
        store.save_policy_version("policy-v2", _policy_doc("policy-v2"))
        store.set_rollout_state(
            {
                "stage": "CANARY",
                "base_policy_version": PolicySnapshot().policy_version,
                "candidate_policy_version": "policy-v2",
                "ratio": 1.0,
                "updated_at_ms": 1000,
            }
        )
        loader = PolicyLoader(
            store=store,
            cache_seconds=0,
            projection_max_staleness_ms=100,
            strict_authority=True,
        )

        with self.assertRaises(RuntimePolicyAuthorityError):
            loader.load("session-strict-stale")

    def test_strict_runtime_does_not_fail_open_policy_projection_error(self) -> None:
        redis = InMemoryRedis()
        loader = PolicyLoader(
            store=RedisPolicyStore(redis),
            cache_seconds=0,
            strict_authority=True,
        )
        runtime = DefenseRuntime(redis=redis, policy_loader=loader)
        request = build_evaluate_request(
            session_id="session-strict-runtime-missing",
            trace_id="trace-strict-runtime-missing",
            body={
                "event": {
                    "eventType": "API_CALL_OBS",
                    "tsMs": 1710000000000,
                    "flowState": "S2",
                    "requestPath": "/api/availability",
                    "requestMethod": "GET",
                },
                "context": {
                    "policyVersion": PolicySnapshot().policy_version,
                },
            },
        )

        with self.assertRaises(RuntimeAPIError) as exc_info:
            runtime.fail_open_on_unavailable(
                request=request,
                error=RuntimePolicyAuthorityError(
                    session_id=request.session_id,
                    reason="missing rollout projection",
                ),
            )

        self.assertEqual(exc_info.exception.status_code, 503)
        self.assertEqual(
            exc_info.exception.detail["authority"],
            "redis_projection",
        )


if __name__ == "__main__":
    unittest.main()
