from traffic_master_ai.defense.api.models import EvaluateRequest, RuntimeStateSnapshot
from traffic_master_ai.defense.api.policy import DecisionPolicy, PolicyConfig
from traffic_master_ai.defense.api.state import InMemoryStateStore


def _policy() -> tuple[DecisionPolicy, InMemoryStateStore]:
    store = InMemoryStateStore(ttl_seconds=1800)
    policy = DecisionPolicy(PolicyConfig(), store)
    return policy, store


def test_vqa_gate_requires_challenge_once_after_queue() -> None:
    policy, store = _policy()
    req = EvaluateRequest(
        session_id="sess-1",
        path="/api/holds",
        method="POST",
        timestamp=1772500000000,
    )

    resp, snap = policy.evaluate(req)

    assert resp.allow is False
    assert resp.action == "CHALLENGE"
    assert resp.flow_state == "F2"
    assert "S3_QUEUE_EXIT_VQA_REQUIRED" in resp.rule_hits
    assert store.get("sess-1") is not None
    assert snap.vqa_passed is False


def test_repetitive_pattern_t2_gates_high_value_write() -> None:
    policy, store = _policy()
    store.upsert(
        "sess-2",
        RuntimeStateSnapshot(
            flow_state="F4",
            defense_tier="T1",
            vqa_passed=True,
            updated_ts_ms=1772500000000,
        ),
    )
    req = EvaluateRequest(
        session_id="sess-2",
        path="/api/holds",
        method="POST",
        timestamp=1772500000000,
        repetitive_pattern_count=3,
    )

    resp, _ = policy.evaluate(req)

    assert resp.allow is False
    assert resp.action == "GATE"
    assert resp.defense_tier == "T2"
    assert "T2_GATE_HIGH_VALUE_WRITE" in resp.rule_hits
    assert resp.headers_to_add.get("x-defense-action") == "gate"
    assert "throttle" in resp.headers_to_add.get("x-defense-actions", "")


def test_challenge_fail_threshold_blocks() -> None:
    policy, _ = _policy()
    req = EvaluateRequest(
        session_id="sess-3",
        path="/api/holds",
        method="POST",
        timestamp=1772500000000,
        challenge_fail_count=3,
    )

    resp, _ = policy.evaluate(req)

    assert resp.allow is False
    assert resp.action == "BLOCK"
    assert resp.defense_tier == "T3"
    assert resp.flow_state == "FX"
    assert "R2_CHALLENGE_FAIL_THRESHOLD" in resp.rule_hits


def test_s6_does_not_insert_new_challenge() -> None:
    policy, store = _policy()
    store.upsert(
        "sess-4",
        RuntimeStateSnapshot(
            flow_state="FX",
            defense_tier="T2",
            vqa_passed=False,
            risk_score=0.7,
            updated_ts_ms=1772500000000,
        ),
    )
    req = EvaluateRequest(
        session_id="sess-4",
        path="/api/payments",
        method="POST",
        timestamp=1772500000000,
        flow_state="FX",
        defense_tier="T2",
        repetitive_pattern_count=5,
    )

    resp, _ = policy.evaluate(req)

    assert resp.allow is True
    assert resp.action == "NONE"
    assert resp.flow_state == "FX"
    assert "FX_NO_NEW_INTERVENTION_ON_TERMINAL" in resp.rule_hits


def test_t3_without_decisive_hit_uses_gate_not_forced_block() -> None:
    policy, store = _policy()
    store.upsert(
        "sess-t3-1",
        RuntimeStateSnapshot(
            flow_state="F4",
            defense_tier="T3",
            vqa_passed=True,
            risk_score=0.9,
            updated_ts_ms=1772500000000,
        ),
    )
    req = EvaluateRequest(
        session_id="sess-t3-1",
        path="/api/holds",
        method="POST",
        timestamp=1772500000000,
        defense_tier="T3",
    )

    resp, _ = policy.evaluate(req)

    assert resp.allow is False
    assert resp.action == "GATE"
    assert resp.defense_tier == "T3"
    assert "T3_GATE_HIGH_VALUE_WRITE" in resp.rule_hits
    assert resp.reason == "HIGH_VALUE_GATED"
