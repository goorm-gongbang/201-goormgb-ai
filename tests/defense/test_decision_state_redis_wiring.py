from __future__ import annotations

from traffic_master_ai.defense.d0_mvp.api.runtime import DefenseRuntime, build_evaluate_request
from traffic_master_ai.defense.d0_mvp.state.keyspace import (
    ANALYZER_WINDOW_KEY_PREFIX,
    BLOCK_KEY_PREFIX,
    DEDUP_KEY_PREFIX,
    POLICY_ROLLOUT_STATE_KEY,
    POLICY_VERSION_INDEX_KEY,
    POLICY_VERSION_KEY_PREFIX,
    SESSION_KEY_PREFIX,
)
from traffic_master_ai.defense.d0_mvp.state.redis_client import InMemoryRedis, build_runtime_redis_from_env


def test_build_runtime_redis_from_env_uses_memory_in_ci(monkeypatch) -> None:
    monkeypatch.delenv("TM_REDIS_URL", raising=False)
    monkeypatch.setenv("CI", "true")

    client, backend = build_runtime_redis_from_env()

    assert backend == "memory"
    assert isinstance(client, InMemoryRedis)


def test_build_runtime_redis_from_env_uses_redis_when_url_present(monkeypatch) -> None:
    monkeypatch.setenv("TM_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CI", "false")

    client, backend = build_runtime_redis_from_env()

    try:
        assert backend == "redis"
        assert hasattr(client, "hgetall")
        assert hasattr(client, "pipeline")
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def test_decision_state_uses_isolated_redis_keyspace() -> None:
    redis = InMemoryRedis()
    session_id = "shared-session"
    snapshot_key = f"tm:sess:{session_id}"
    redis.set(snapshot_key, '{"snapshot":true}')

    runtime = DefenseRuntime(redis=redis)
    req = build_evaluate_request(
        session_id=session_id,
        trace_id="trace-shared-session",
        body={
            "event": {
                "eventType": "API_CALL_OBS",
                "tsMs": 1710000000100,
                "flowState": "S1",
                "requestPath": "/api/availability",
                "requestMethod": "GET",
                "payload": {"category": "READ", "method": "GET"},
            },
            "context": {
                "policyVersion": "def-pol-2.0.0",
                "features": {
                    "tremorStdDev": 0.2,
                    "linearityRatio": 0.98,
                    "avgVelocity": 1800.0,
                    "dwellTime": 50.0,
                    "pathRatio": 1.02,
                },
            },
        },
    )

    runtime.evaluate(req)
    runtime.block_state.set_block(
        session_id=session_id,
        blocked_at_ms=1710000000200,
        policy_version="def-pol-2.0.0",
    )

    assert redis.get(snapshot_key) == '{"snapshot":true}'
    assert redis.hgetall(f"{SESSION_KEY_PREFIX}{session_id}") != {}
    assert redis.hgetall(f"{BLOCK_KEY_PREFIX}{session_id}") != {}
    assert POLICY_ROLLOUT_STATE_KEY in redis._data
    assert POLICY_VERSION_INDEX_KEY in redis._data
    assert any(str(key).startswith(POLICY_VERSION_KEY_PREFIX) for key in redis._data)
    assert any(str(key).startswith(f"{DEDUP_KEY_PREFIX}guard:") for key in redis._data)
    assert any(str(key).startswith(f"{DEDUP_KEY_PREFIX}analyzer:") for key in redis._data)
    assert any(str(key).startswith(ANALYZER_WINDOW_KEY_PREFIX) for key in redis._data)
