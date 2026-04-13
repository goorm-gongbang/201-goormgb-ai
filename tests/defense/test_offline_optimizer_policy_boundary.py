from __future__ import annotations

import json

from traffic_master_ai.defense.d0_mvp.optimizer.effect_evaluator import _build_llm_input
from traffic_master_ai.defense.d0_mvp.optimizer.validator import ProposalValidator


def test_offline_optimizer_validator_rejects_challenge_policy_patch() -> None:
    validator = ProposalValidator()

    result = validator.validate(
        {
            "proposal_id": "proposal-1",
            "base_policy_version": "policy-v1",
            "patches": [
                {
                    "path": "challenge.halt_seconds",
                    "op": "dec",
                    "value": 5,
                    "why": "legacy challenge tuning must be blocked",
                }
            ],
            "rationale": "should be rejected",
            "confidence": 0.4,
            "rollback_conditions": ["block_rate increases"],
            "notes": "",
        },
        expected_base_policy_version="policy-v1",
    )

    assert result.valid is False
    assert "forbidden patch path: challenge.halt_seconds" in result.errors


def test_offline_optimizer_llm_input_excludes_challenge_tuning_paths() -> None:
    payload = _build_llm_input(
        {
            "window_start_ms": 1,
            "window_end_ms": 2,
            "unique_sessions": 10,
            "unique_traces": 10,
            "event_counts_by_type": {},
            "tier_distribution": {},
            "action_distribution": {},
            "block_rate": 0.01,
            "require_s3_rate": 0.02,
            "throttle_applied_rate": 0.03,
            "avg_throttle_delay_ms": 120,
            "s3_pass_rate": 0.8,
            "s3_fail_rate": 0.2,
            "s3_temp_lock_rate": 0.0,
            "dedup_duplicate_rate": 0.0,
            "missing_feature_rate": 0.0,
        },
        "policy-v1",
    )
    decoded = json.loads(payload["input_text"])
    allowlist = decoded["allowlist"]

    assert "challenge.max_attempts" not in allowlist
    assert "challenge.cooldown_ms.first" not in allowlist
    assert "challenge.cooldown_ms.second" not in allowlist
    assert "challenge.halt_seconds" not in allowlist
