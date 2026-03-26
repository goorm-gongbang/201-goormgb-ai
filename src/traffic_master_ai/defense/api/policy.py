"""Deterministic runtime policy aligned with defense ACT v2."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass

from .models import DefenseActionStr, EvaluateRequest, EvaluateResponse, RuntimeStateSnapshot
from .state import RuntimeStateStore

_TIER_RANK = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
_ACTION_PRIORITY: dict[DefenseActionStr, int] = {
    "NONE": 0,
    "THROTTLE": 1,
    "GATE": 2,
    "CHALLENGE": 3,
    "BLOCK": 4,
}


@dataclass(slots=True)
class PolicyConfig:
    """Runtime policy parameters loaded from env."""

    policy_version: str = "def-pol-2.0.0"
    challenge_fail_threshold: int = 3
    repetitive_t1_threshold: int = 1
    repetitive_t2_threshold: int = 3
    throttle_light_ms: int = 200
    throttle_strong_ms: int = 1800
    high_value_paths: tuple[str, ...] = (
        "/queue/matches/",
        "/seat/matches/",
    )
    vqa_gate_paths: tuple[str, ...] = (
        "/queue/matches/",
        "/seat/matches/",
    )
    challenge_api_paths: tuple[str, ...] = (
        "/ai/challenge/start",
        "/ai/challenge/verify",
    )

    @staticmethod
    def from_env() -> PolicyConfig:
        return PolicyConfig(
            policy_version=os.getenv("TM_DEFENSE_POLICY_VERSION", "def-pol-2.0.0"),
            challenge_fail_threshold=int(os.getenv("TM_CHALLENGE_FAIL_THRESHOLD", "3")),
            repetitive_t1_threshold=int(os.getenv("TM_REPETITIVE_PATTERN_T1_THRESHOLD", "1")),
            repetitive_t2_threshold=int(os.getenv("TM_REPETITIVE_PATTERN_T2_THRESHOLD", "3")),
            throttle_light_ms=int(os.getenv("TM_T1_THROTTLE_MS", "200")),
            throttle_strong_ms=int(os.getenv("TM_T2_THROTTLE_MS", "1800")),
            high_value_paths=_csv_tuple(
                os.getenv(
                    "TM_HIGH_VALUE_PATH_PREFIXES",
                    "/queue/matches/,/seat/matches/",
                )
            ),
            vqa_gate_paths=_csv_tuple(
                os.getenv(
                    "TM_VQA_GATE_PATH_PREFIXES",
                    "/queue/matches/,/seat/matches/",
                )
            ),
            challenge_api_paths=_csv_tuple(
                os.getenv(
                    "TM_CHALLENGE_API_PATH_PREFIXES",
                    "/ai/challenge/start,/ai/challenge/verify",
                )
            ),
        )


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _max_tier(a: str, b: str) -> str:
    return a if _TIER_RANK[a] >= _TIER_RANK[b] else b


class DecisionPolicy:
    """Deterministic runtime policy without runtime LLM."""

    def __init__(self, cfg: PolicyConfig, store: RuntimeStateStore) -> None:
        self._cfg = cfg
        self._store = store

    def evaluate(self, req: EvaluateRequest) -> tuple[EvaluateResponse, RuntimeStateSnapshot]:
        started = time.perf_counter()
        now_ms = int(time.time() * 1000)
        decision_id = f"dec-{uuid.uuid4().hex[:12]}"
        rule_hits: list[str] = []

        prev = self._store.get(req.session_id) or RuntimeStateSnapshot(updated_ts_ms=now_ms)
        flow_state = req.flow_state or prev.flow_state
        tier = req.defense_tier or prev.defense_tier
        challenge_fail_count = max(req.challenge_fail_count, prev.challenge_fail_count)

        if req.token_mismatch:
            # Token mismatch handling stays in backend by latest policy.
            rule_hits.append("TOKEN_MISMATCH_BACKEND_OWNED")

        # Score -> tier update (deterministic, no LLM).
        if req.repetitive_pattern_count >= self._cfg.repetitive_t2_threshold:
            tier = _max_tier(tier, "T2")
            rule_hits.append("R1_REPETITIVE_PATTERN_T2")
        elif req.repetitive_pattern_count >= self._cfg.repetitive_t1_threshold:
            tier = _max_tier(tier, "T1")
            rule_hits.append("R1_REPETITIVE_PATTERN_T1")

        if challenge_fail_count >= self._cfg.challenge_fail_threshold:
            tier = "T3"
            rule_hits.append("R2_CHALLENGE_FAIL_THRESHOLD")

        # S6 invariant: no new friction. BLOCK only when decisive.
        if flow_state == "S6":
            rule_hits.append("F5_NO_NEW_INTERVENTION_ON_S6")
            if "R2_CHALLENGE_FAIL_THRESHOLD" in rule_hits:
                resp = self._build_response(
                    allow=False,
                    req=req,
                    flow_state="SX",
                    defense_tier="T3",
                    actions=["BLOCK"],
                    reason="BLOCKED",
                    risk_score=0.95,
                    rule_hits=rule_hits,
                    decision_id=decision_id,
                    started=started,
                )
            else:
                resp = self._build_response(
                    allow=True,
                    req=req,
                    flow_state=flow_state,
                    defense_tier=tier,
                    actions=["NONE"],
                    reason=None,
                    risk_score=self._risk_score_for_tier(tier, prev.risk_score),
                    rule_hits=rule_hits,
                    decision_id=decision_id,
                    started=started,
                )
            return self._finalize(req, prev, resp, challenge_fail_count, now_ms)

        if "R2_CHALLENGE_FAIL_THRESHOLD" in rule_hits:
            resp = self._build_response(
                allow=False,
                req=req,
                flow_state="SX",
                defense_tier="T3",
                actions=["BLOCK"],
                reason="BLOCKED",
                risk_score=0.92,
                rule_hits=rule_hits,
                decision_id=decision_id,
                started=started,
            )
            return self._finalize(req, prev, resp, challenge_fail_count, now_ms)

        if self._requires_vqa(req, prev):
            rule_hits.append("S3_QUEUE_EXIT_VQA_REQUIRED")
            resp = self._build_response(
                allow=False,
                req=req,
                flow_state="S3",
                defense_tier=tier,
                actions=["CHALLENGE"],
                reason="CHALLENGE_REQUIRED",
                risk_score=max(prev.risk_score, 0.4),
                rule_hits=rule_hits,
                decision_id=decision_id,
                started=started,
            )
            return self._finalize(req, prev, resp, challenge_fail_count, now_ms)

        if tier == "T2":
            if req.method.upper() == "POST" and self._is_high_value_path(req.path):
                rule_hits.append("T2_GATE_HIGH_VALUE_WRITE")
                actions: list[DefenseActionStr] = ["GATE", "THROTTLE"]
                resp = self._build_response(
                    allow=False,
                    req=req,
                    flow_state=flow_state,
                    defense_tier=tier,
                    actions=actions,
                    reason="HIGH_VALUE_GATED",
                    risk_score=max(prev.risk_score, 0.72),
                    rule_hits=rule_hits,
                    decision_id=decision_id,
                    started=started,
                )
            else:
                rule_hits.append("T2_THROTTLE_STRONG")
                resp = self._build_response(
                    allow=True,
                    req=req,
                    flow_state=flow_state,
                    defense_tier=tier,
                    actions=["THROTTLE"],
                    reason=None,
                    risk_score=max(prev.risk_score, 0.62),
                    rule_hits=rule_hits,
                    decision_id=decision_id,
                    started=started,
                )
            return self._finalize(req, prev, resp, challenge_fail_count, now_ms)

        if tier == "T3":
            if req.method.upper() == "POST" and self._is_high_value_path(req.path):
                rule_hits.append("T3_GATE_HIGH_VALUE_WRITE")
                resp = self._build_response(
                    allow=False,
                    req=req,
                    flow_state=flow_state,
                    defense_tier="T3",
                    actions=["GATE", "THROTTLE"],
                    reason="HIGH_VALUE_GATED",
                    risk_score=max(prev.risk_score, 0.85),
                    rule_hits=rule_hits,
                    decision_id=decision_id,
                    started=started,
                )
            else:
                rule_hits.append("T3_THROTTLE_STRONG")
                resp = self._build_response(
                    allow=True,
                    req=req,
                    flow_state=flow_state,
                    defense_tier="T3",
                    actions=["THROTTLE"],
                    reason=None,
                    risk_score=max(prev.risk_score, 0.82),
                    rule_hits=rule_hits,
                    decision_id=decision_id,
                    started=started,
                )
            return self._finalize(req, prev, resp, challenge_fail_count, now_ms)

        if tier == "T1":
            if req.repetitive_pattern_count >= self._cfg.repetitive_t1_threshold:
                rule_hits.append("T1_THROTTLE_LIGHT")
                resp = self._build_response(
                    allow=True,
                    req=req,
                    flow_state=flow_state,
                    defense_tier=tier,
                    actions=["THROTTLE"],
                    reason=None,
                    risk_score=max(prev.risk_score, 0.35),
                    rule_hits=rule_hits,
                    decision_id=decision_id,
                    started=started,
                )
            else:
                resp = self._build_response(
                    allow=True,
                    req=req,
                    flow_state=flow_state,
                    defense_tier=tier,
                    actions=["NONE"],
                    reason=None,
                    risk_score=max(prev.risk_score, 0.2),
                    rule_hits=rule_hits,
                    decision_id=decision_id,
                    started=started,
                )
            return self._finalize(req, prev, resp, challenge_fail_count, now_ms)

        rule_hits.append("DEFAULT_ALLOW")
        resp = self._build_response(
            allow=True,
            req=req,
            flow_state=flow_state,
            defense_tier="T0",
            actions=["NONE"],
            reason=None,
            risk_score=max(prev.risk_score * 0.9, 0.05),
            rule_hits=rule_hits,
            decision_id=decision_id,
            started=started,
        )
        return self._finalize(req, prev, resp, challenge_fail_count, now_ms)

    def _finalize(
        self,
        req: EvaluateRequest,
        prev: RuntimeStateSnapshot,
        resp: EvaluateResponse,
        challenge_fail_count: int,
        now_ms: int,
    ) -> tuple[EvaluateResponse, RuntimeStateSnapshot]:
        snap = self._next_snapshot(
            prev,
            resp,
            challenge_fail_count,
            now_ms,
        )
        self._store.upsert(req.session_id, snap)
        return resp, snap

    def _requires_vqa(self, req: EvaluateRequest, state: RuntimeStateSnapshot) -> bool:
        if state.vqa_passed:
            return False
        if any(req.path.startswith(prefix) for prefix in self._cfg.challenge_api_paths):
            return False
        return any(req.path.startswith(prefix) for prefix in self._cfg.vqa_gate_paths)

    def _is_high_value_path(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in self._cfg.high_value_paths)

    def _risk_score_for_tier(self, tier: str, prev_score: float) -> float:
        floor = {"T0": 0.05, "T1": 0.30, "T2": 0.60, "T3": 0.90}[tier]
        return max(prev_score, floor)

    def _next_snapshot(
        self,
        prev: RuntimeStateSnapshot,
        resp: EvaluateResponse,
        challenge_fail_count: int,
        now_ms: int,
    ) -> RuntimeStateSnapshot:
        return RuntimeStateSnapshot(
            flow_state=resp.flow_state,
            defense_tier=resp.defense_tier,
            risk_score=resp.risk_score if resp.risk_score is not None else prev.risk_score,
            challenge_fail_count=challenge_fail_count,
            seat_taken_streak=prev.seat_taken_streak,
            hold_fail_streak=prev.hold_fail_streak,
            heavy_budget_left=prev.heavy_budget_left,
            replan_budget_left=prev.replan_budget_left,
            probation_until_ms=prev.probation_until_ms,
            policy_version=self._cfg.policy_version,
            updated_ts_ms=now_ms,
            vqa_required=prev.vqa_required,
            vqa_passed=prev.vqa_passed,
            vqa_attempt_count=prev.vqa_attempt_count,
            vqa_retry_limit=prev.vqa_retry_limit,
            vqa_last_result=prev.vqa_last_result,
            active_challenge_id=prev.active_challenge_id,
            active_challenge_expires_at_ms=prev.active_challenge_expires_at_ms,
        )

    def _build_response(
        self,
        *,
        allow: bool,
        req: EvaluateRequest,
        flow_state: str,
        defense_tier: str,
        actions: list[DefenseActionStr],
        reason: str | None,
        risk_score: float | None,
        rule_hits: list[str],
        decision_id: str,
        started: float,
    ) -> EvaluateResponse:
        primary = max(actions, key=lambda action: _ACTION_PRIORITY[action])
        headers = self._headers_for(primary, actions, defense_tier, reason)
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        return EvaluateResponse(
            allow=allow,
            session_id=req.session_id,
            flow_state=flow_state,  # type: ignore[arg-type]
            defense_tier=defense_tier,  # type: ignore[arg-type]
            action=primary,
            actions=actions,
            reason=reason,
            rule_hits=rule_hits,
            risk_score=risk_score,
            policy_version=self._cfg.policy_version,
            headers_to_add=headers,
            decision_id=decision_id,
            latency_ms=latency_ms,
            version="v2",
        )

    def _headers_for(
        self,
        primary: DefenseActionStr,
        actions: list[DefenseActionStr],
        defense_tier: str,
        reason: str | None,
    ) -> dict[str, str]:
        headers = {
            "x-defense-policy-version": self._cfg.policy_version,
            "x-defense-tier": defense_tier,
            "x-defense-action": primary.lower(),
            "x-defense-actions": ",".join(action.lower() for action in actions),
        }
        if "THROTTLE" in actions:
            if defense_tier in ("T2", "T3"):
                throttle_ms = self._cfg.throttle_strong_ms
            else:
                throttle_ms = self._cfg.throttle_light_ms
            headers["x-throttle-ms"] = str(throttle_ms)
        if "CHALLENGE" in actions:
            headers["x-challenge-type"] = "queue_gate"
            headers["x-challenge-required"] = "true"
        if "GATE" in actions:
            headers["x-gate-mode"] = "high-value-write"
        if primary == "BLOCK":
            headers["x-block-reason"] = (reason or "blocked").lower()
        return headers
