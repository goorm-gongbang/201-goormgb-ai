from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from traffic_master_ai.defense.backoffice_copilot.storage import (
    ClickHouseOfflineMetricsRepository,
    OfflineMetricsQuery,
)
from traffic_master_ai.defense.d0_mvp.observability.schemas import OPTIMIZER_INCLUDED_AUDIT_EVENT_TYPES
from traffic_master_ai.defense.d0_mvp.api.runtime import DefenseRuntime
from traffic_master_ai.defense.d0_mvp.optimizer.pipeline import OfflineOptimizer
from traffic_master_ai.defense.d0_mvp.policy.loader import InMemoryPolicyStore, PolicyLoader
from traffic_master_ai.defense.d0_mvp.policy.snapshot import PolicySnapshot
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis


class _FakeSelectClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def query(self, sql_text: str, params: dict[str, object]):
        self.calls.append((sql_text, params))
        if "count() AS events_total" in sql_text:
            return [
                {
                    "window_start_ms": params["window_start_ms"],
                    "window_end_ms": params["window_end_ms"],
                    "events_total": 10,
                    "unique_sessions": 3,
                    "unique_traces": 5,
                    "latest_policy_version": "policy-v9",
                    "duplicate_count": 2,
                }
            ]
        if "GROUP BY event_type" in sql_text:
            return [
                {"event_type": "DEF_BLOCK_ENFORCED", "event_count": 1},
                {"event_type": "DEF_GUARD_SCORED", "event_count": 2},
                {"event_type": "DEF_ORCH_EXECUTED", "event_count": 5},
                {"event_type": "DEF_THROTTLE_APPLIED", "event_count": 2},
                {"event_type": "S3_CHALLENGE_HALTED", "event_count": 1},
                {"event_type": "S3_CHALLENGE_RESULT", "event_count": 2},
            ]
        if "LIMIT :scan_limit" in sql_text:
            return [
                {
                    "ts_ms": 5000,
                    "session_id": "sess-e",
                    "event_type": "DEF_BLOCK_ENFORCED",
                    "trace_id": "trace-e",
                    "reason_code": "BLOCKED",
                    "policy_version": "policy-v9",
                    "raw_payload_json": "{}",
                },
                {
                    "ts_ms": 4900,
                    "session_id": "sess-f",
                    "event_type": "S3_CHALLENGE_RESULT",
                    "trace_id": "trace-f",
                    "reason_code": "CHALLENGE_FAIL",
                    "policy_version": "policy-v9",
                    "raw_payload_json": '{"challenge":{"result":"FAIL"}}',
                },
                {
                    "ts_ms": 4800,
                    "session_id": "sess-c",
                    "event_type": "DEF_THROTTLE_APPLIED",
                    "trace_id": "trace-c",
                    "reason_code": "RULE_HIT",
                    "policy_version": "policy-v9",
                    "raw_payload_json": '{"throttle":{"delayMs":350}}',
                },
                {
                    "ts_ms": 4700,
                    "session_id": "sess-b",
                    "event_type": "DEF_ORCH_EXECUTED",
                    "trace_id": "trace-b",
                    "reason_code": None,
                    "policy_version": "policy-v9",
                    "raw_payload_json": "{}",
                },
            ]
        return [
            {
                "ts_ms": 4600,
                "session_id": "sess-b",
                "event_type": "DEF_ORCH_EXECUTED",
                "trace_id": "trace-b",
                "risk_tier": "T1",
                "action": "NONE",
                "reason_code": None,
                "policy_version": "policy-v9",
                "raw_payload_json": "{}",
            },
            {
                "ts_ms": 4500,
                "session_id": "sess-c",
                "event_type": "DEF_ORCH_EXECUTED",
                "trace_id": "trace-c",
                "risk_tier": "T2",
                "action": "THROTTLE",
                "reason_code": None,
                "policy_version": "policy-v9",
                "raw_payload_json": "{}",
            },
            {
                "ts_ms": 4400,
                "session_id": "sess-d",
                "event_type": "DEF_ORCH_EXECUTED",
                "trace_id": "trace-d",
                "risk_tier": "T3",
                "action": "REQUIRE_S3",
                "reason_code": None,
                "policy_version": "policy-v9",
                "raw_payload_json": "{}",
            },
            {
                "ts_ms": 4300,
                "session_id": "sess-e",
                "event_type": "DEF_ORCH_EXECUTED",
                "trace_id": "trace-e",
                "risk_tier": "T3",
                "action": "BLOCK",
                "reason_code": None,
                "policy_version": "policy-v9",
                "raw_payload_json": "{}",
            },
            {
                "ts_ms": 4200,
                "session_id": "sess-d",
                "event_type": "DEF_ORCH_EXECUTED",
                "trace_id": "trace-d",
                "risk_tier": "T3",
                "action": "REQUIRE_S3",
                "reason_code": None,
                "policy_version": "policy-v9",
                "raw_payload_json": "{}",
            },
            {
                "ts_ms": 4100,
                "session_id": "sess-c",
                "event_type": "DEF_THROTTLE_APPLIED",
                "trace_id": "trace-c",
                "risk_tier": None,
                "action": None,
                "reason_code": "RULE_HIT",
                "policy_version": "policy-v9",
                "raw_payload_json": '{"throttle":{"delayMs":350}}',
            },
            {
                "ts_ms": 4000,
                "session_id": "sess-d",
                "event_type": "DEF_THROTTLE_APPLIED",
                "trace_id": "trace-d",
                "risk_tier": None,
                "action": None,
                "reason_code": "RULE_HIT",
                "policy_version": "policy-v9",
                "raw_payload_json": '{"throttle":{"delayMs":150}}',
            },
            {
                "ts_ms": 3900,
                "session_id": "sess-e",
                "event_type": "DEF_BLOCK_ENFORCED",
                "trace_id": "trace-e",
                "risk_tier": None,
                "action": None,
                "reason_code": "BLOCKED",
                "policy_version": "policy-v9",
                "raw_payload_json": "{}",
            },
            {
                "ts_ms": 3800,
                "session_id": "sess-d",
                "event_type": "S3_CHALLENGE_RESULT",
                "trace_id": "trace-d",
                "risk_tier": None,
                "action": None,
                "reason_code": "PASS",
                "policy_version": "policy-v9",
                "raw_payload_json": '{"challenge":{"result":"PASS"}}',
            },
            {
                "ts_ms": 3700,
                "session_id": "sess-f",
                "event_type": "S3_CHALLENGE_RESULT",
                "trace_id": "trace-f",
                "risk_tier": None,
                "action": None,
                "reason_code": "FAIL",
                "policy_version": "policy-v9",
                "raw_payload_json": '{"challenge":{"result":"FAIL"}}',
            },
            {
                "ts_ms": 3600,
                "session_id": "sess-f",
                "event_type": "S3_CHALLENGE_HALTED",
                "trace_id": "trace-f",
                "risk_tier": None,
                "action": None,
                "reason_code": "TEMP_LOCK",
                "policy_version": "policy-v9",
                "raw_payload_json": '{}',
            },
            {
                "ts_ms": 3500,
                "session_id": "sess-b",
                "event_type": "DEF_GUARD_SCORED",
                "trace_id": "trace-b",
                "risk_tier": None,
                "action": None,
                "reason_code": None,
                "policy_version": "policy-v9",
                "raw_payload_json": '{"guard":{"missingFlags":["ua_missing"]}}',
            },
            {
                "ts_ms": 3400,
                "session_id": "sess-c",
                "event_type": "DEF_GUARD_SCORED",
                "trace_id": "trace-c",
                "risk_tier": None,
                "action": None,
                "reason_code": None,
                "policy_version": "policy-v9",
                "raw_payload_json": '{"guard":{"missingFlags":[]}}',
            },
        ]


class _EmptySelectClient:
    def query(self, sql_text: str, params: dict[str, object]):
        del sql_text, params
        return []


class _ErrorSelectClient:
    def query(self, sql_text: str, params: dict[str, object]):
        del sql_text, params
        raise RuntimeError("clickhouse bad response")


class _PolicyVersionSelectClient:
    def __init__(
        self,
        *,
        candidate_empty: bool = False,
        events_total: int = 30,
        unique_traces: int = 10,
    ) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.candidate_empty = candidate_empty
        self.events_total = events_total
        self.unique_traces = unique_traces

    def query(self, sql_text: str, params: dict[str, object]):
        self.calls.append((sql_text, params))
        policy_version = params.get("policy_version")
        if "count() AS events_total" in sql_text:
            if policy_version == "policy-candidate" and self.candidate_empty:
                return []
            return [
                {
                    "window_start_ms": params["window_start_ms"],
                    "window_end_ms": params["window_end_ms"],
                    "events_total": self.events_total,
                    "unique_sessions": 2,
                    "unique_traces": self.unique_traces,
                    "latest_policy_version": policy_version,
                    "duplicate_count": 0,
                }
            ]
        if "GROUP BY event_type" in sql_text:
            return [
                {"event_type": "DEF_ORCH_EXECUTED", "event_count": 2},
                {"event_type": "DEF_BLOCK_ENFORCED", "event_count": 1},
            ]
        if policy_version == "policy-base":
            return [
                _orch_row("policy-base", "trace-base-1", "NONE"),
                _orch_row("policy-base", "trace-base-2", "NONE"),
            ]
        if self.candidate_empty:
            return []
        return [
            _orch_row("policy-candidate", "trace-candidate-1", "BLOCK"),
            _orch_row("policy-candidate", "trace-candidate-2", "NONE"),
            {
                "ts_ms": 4500,
                "session_id": "sess-candidate-1",
                "event_type": "DEF_BLOCK_ENFORCED",
                "trace_id": "trace-candidate-1",
                "risk_tier": None,
                "action": None,
                "reason_code": "BLOCKED",
                "policy_version": "policy-candidate",
                "raw_payload_json": "{}",
            },
        ]


def _orch_row(policy_version: str, trace_id: str, action: str) -> dict[str, object]:
    return {
        "ts_ms": 4600,
        "session_id": f"sess-{trace_id}",
        "event_type": "DEF_ORCH_EXECUTED",
        "trace_id": trace_id,
        "risk_tier": "T3",
        "action": action,
        "reason_code": None,
        "policy_version": policy_version,
        "raw_payload_json": "{}",
    }


class OfflineOptimizerClickHouseMetricsTests(unittest.TestCase):
    def test_clickhouse_repository_computes_metrics_from_raw_fact_queries(self) -> None:
        client = _FakeSelectClient()
        repository = ClickHouseOfflineMetricsRepository(client=client)

        snapshot = repository.read_metrics(
            OfflineMetricsQuery(window_start_ms=1000, window_end_ms=5000)
        )

        self.assertEqual(snapshot.events_total, 10)
        self.assertEqual(snapshot.unique_sessions, 3)
        self.assertEqual(snapshot.unique_traces, 5)
        self.assertEqual(snapshot.latest_policy_version, "policy-v9")
        self.assertEqual(dict(snapshot.event_counts_by_type)["DEF_ORCH_EXECUTED"], 5)
        self.assertEqual(dict(snapshot.tier_distribution), {"T1": 1, "T2": 1, "T3": 2})
        self.assertEqual(
            dict(snapshot.action_distribution),
            {"BLOCK": 1, "NONE": 1, "REQUIRE_S3": 1, "THROTTLE": 1},
        )
        self.assertEqual(snapshot.block_rate, 0.25)
        self.assertEqual(snapshot.require_s3_rate, 0.25)
        self.assertEqual(snapshot.throttle_applied_rate, 0.5)
        self.assertEqual(snapshot.avg_throttle_delay_ms, 250.0)
        self.assertEqual(snapshot.s3_pass_rate, 0.5)
        self.assertEqual(snapshot.s3_fail_rate, 0.5)
        self.assertEqual(snapshot.s3_temp_lock_rate, 0.3333)
        self.assertEqual(snapshot.dedup_duplicate_rate, 0.2)
        self.assertEqual(snapshot.missing_feature_rate, 0.5)
        self.assertEqual(len(client.calls), 3)
        self.assertTrue(all(call[1]["window_start_ms"] == 1000 for call in client.calls))
        self.assertTrue(all(call[1]["window_end_ms"] == 5000 for call in client.calls))
        detail_call = next(
            call for call in client.calls if "AND event_type IN :event_types " in call[0]
        )
        self.assertEqual(
            tuple(detail_call[1]["event_types"]),
            tuple(sorted(OPTIMIZER_INCLUDED_AUDIT_EVENT_TYPES)),
        )

    def test_clickhouse_repository_samples_traces_by_priority_and_limit(self) -> None:
        repository = ClickHouseOfflineMetricsRepository(client=_FakeSelectClient())

        samples = repository.read_trace_samples(
            OfflineMetricsQuery(window_start_ms=1000, window_end_ms=5000, limit=3)
        )

        self.assertEqual(tuple(sample.trace_id for sample in samples), ("trace-e", "trace-f", "trace-c"))
        self.assertEqual(samples[1].reason_code, "CHALLENGE_FAIL")
        self.assertEqual(samples[2].policy_version, "policy-v9")

    def test_clickhouse_repository_returns_zero_snapshot_for_empty_window(self) -> None:
        repository = ClickHouseOfflineMetricsRepository(client=_EmptySelectClient())

        snapshot = repository.read_metrics(
            OfflineMetricsQuery(window_start_ms=1000, window_end_ms=1000)
        )

        self.assertEqual(snapshot.window_start_ms, 1000)
        self.assertEqual(snapshot.window_end_ms, 1000)
        self.assertEqual(snapshot.events_total, 0)
        self.assertEqual(dict(snapshot.event_counts_by_type), {})
        self.assertEqual(snapshot.latest_policy_version, None)

    def test_clickhouse_repository_surfaces_bad_select_response(self) -> None:
        repository = ClickHouseOfflineMetricsRepository(client=_ErrorSelectClient())

        with self.assertRaises(RuntimeError):
            repository.read_metrics(OfflineMetricsQuery(window_start_ms=1000, window_end_ms=5000))

    def test_clickhouse_repository_computes_rollout_guardrail_deltas(self) -> None:
        client = _PolicyVersionSelectClient()
        repository = ClickHouseOfflineMetricsRepository(client=client)

        deltas = repository.read_rollout_guardrail_deltas(
            OfflineMetricsQuery(window_start_ms=1000, window_end_ms=5000),
            base_policy_version="policy-base",
            candidate_policy_version="policy-candidate",
        )

        self.assertIsNotNone(deltas)
        self.assertEqual(deltas["block_rate_pp"], 50.0)
        self.assertNotIn("internal_error_rate_pp", deltas)
        policy_calls = [
            call for call in client.calls if "policy_version = :policy_version" in call[0]
        ]
        self.assertEqual(len(policy_calls), 6)
        self.assertEqual(
            {call[1]["policy_version"] for call in policy_calls},
            {"policy-base", "policy-candidate"},
        )

    def test_clickhouse_repository_returns_none_for_insufficient_guardrail_data(self) -> None:
        repository = ClickHouseOfflineMetricsRepository(
            client=_PolicyVersionSelectClient(candidate_empty=True)
        )

        deltas = repository.read_rollout_guardrail_deltas(
            OfflineMetricsQuery(window_start_ms=1000, window_end_ms=5000),
            base_policy_version="policy-base",
            candidate_policy_version="policy-candidate",
        )

        self.assertIsNone(deltas)

    def test_clickhouse_repository_requires_minimum_guardrail_sample_size(self) -> None:
        repository = ClickHouseOfflineMetricsRepository(
            client=_PolicyVersionSelectClient(events_total=29, unique_traces=9)
        )

        deltas = repository.read_rollout_guardrail_deltas(
            OfflineMetricsQuery(window_start_ms=1000, window_end_ms=5000),
            base_policy_version="policy-base",
            candidate_policy_version="policy-candidate",
        )

        self.assertIsNone(deltas)

    def test_offline_optimizer_collect_metrics_uses_repository_and_default_policy_when_latest_missing(self) -> None:
        class _NoPolicyRepository:
            def read_metrics(self, query: OfflineMetricsQuery):
                return ClickHouseOfflineMetricsRepository(client=_EmptySelectClient()).read_metrics(query)

            def read_trace_samples(self, query: OfflineMetricsQuery):
                del query
                return ()

        optimizer = OfflineOptimizer(
            metrics_repository=_NoPolicyRepository(),
            policy_loader=PolicyLoader(store=InMemoryPolicyStore(), cache_seconds=0),
        )

        metrics = optimizer.collect_metrics(window_seconds=60, now_ms=2000)

        self.assertEqual(metrics["window_start_ms"], 2000 - 60000)
        self.assertEqual(metrics["window_end_ms"], 2000)
        self.assertEqual(metrics["policy_version"], PolicySnapshot().policy_version)

    def test_runtime_offline_optimizer_fails_fast_without_clickhouse_url(self) -> None:
        env = dict(os.environ)
        env.pop("TM_CLICKHOUSE_URL", None)

        with patch.dict(os.environ, env, clear=True):
            runtime = DefenseRuntime(
                redis=InMemoryRedis(),
                policy_loader=PolicyLoader(store=InMemoryPolicyStore(), cache_seconds=0),
            )
            with self.assertRaises(RuntimeError):
                runtime.offline_optimizer_service()


if __name__ == "__main__":
    unittest.main()
