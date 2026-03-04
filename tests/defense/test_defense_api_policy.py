from traffic_master_ai.defense.api.models import EvaluateRequest, RuntimeStateSnapshot
from traffic_master_ai.defense.api.policy import DecisionPolicy, PolicyConfig
from traffic_master_ai.defense.api.state import InMemoryStateStore


def _policy() -> tuple[DecisionPolicy, InMemoryStateStore]:
    store = InMemoryStateStore(ttl_seconds=1800)
    policy = DecisionPolicy(PolicyConfig(), store)
    return policy, store


def test_repetitive_pattern_t2_forces_challenge() -> None:
    policy, store = _policy()
    req = EvaluateRequest(
        session_id="sess-1",
        path="/api/holds",
        method="POST",
        timestamp=1772500000000,
        repetitive_pattern_count=3,
    )

    resp, snap = policy.evaluate(req)

    assert resp.allow is False
    assert resp.action == "DEF_CHALLENGE_FORCED"
    assert resp.defense_tier == "T2"
    assert resp.flow_state == "S3"
    assert "R1_REPETITIVE_PATTERN_T2" in resp.rule_hits
    assert store.get("sess-1") is not None
    assert snap.defense_tier == "T2"


def test_token_mismatch_blocks_immediately() -> None:
    policy, _ = _policy()
    req = EvaluateRequest(
        session_id="sess-2",
        path="/api/holds",
        method="POST",
        timestamp=1772500000000,
        token_mismatch=True,
    )

    resp, _ = policy.evaluate(req)

    assert resp.allow is False
    assert resp.action == "DEF_BLOCKED"
    assert resp.defense_tier == "T3"
    assert resp.flow_state == "SX"
    assert "R3_TOKEN_MISMATCH" in resp.rule_hits


def test_s6_does_not_insert_new_challenge() -> None:
    policy, store = _policy()
    store.upsert(
        "sess-3",
        RuntimeStateSnapshot(
            flow_state="S6",
            defense_tier="T2",
            risk_score=0.7,
            updated_ts_ms=1772500000000,
        ),
    )
    req = EvaluateRequest(
        session_id="sess-3",
        path="/api/payments",
        method="POST",
        timestamp=1772500000000,
        flow_state="S6",
        defense_tier="T2",
        repetitive_pattern_count=5,
    )

    resp, _ = policy.evaluate(req)

    assert resp.allow is True
    assert resp.action is None
    assert resp.flow_state == "S6"
    assert "F5_NO_NEW_INTERVENTION_ON_S6" in resp.rule_hits

