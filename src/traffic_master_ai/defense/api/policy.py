"""Deterministic policy with runtime state persistence."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass

from .models import EvaluateRequest, EvaluateResponse, RuntimeStateSnapshot
from .state import RuntimeStateStore

_TIER_RANK = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}


@dataclass(slots=True)
class PolicyConfig:
    """Runtime policy parameters loaded from env."""

    policy_version: str = "def-pol-0.1.0"
    challenge_fail_threshold: int = 3
    repetitive_t1_threshold: int = 1
    repetitive_t2_threshold: int = 3
    block_on_token_mismatch: bool = True
    strict_post_paths: tuple[str, ...] = ("/api/queue/", "/api/holds", "/api/payments")

    @staticmethod
    def from_env() -> "PolicyConfig":
        """Load policy from environment variables with safe defaults."""
        return PolicyConfig(
            policy_version=os.getenv("TM_DEFENSE_POLICY_VERSION", "def-pol-0.1.0"),
            challenge_fail_threshold=int(os.getenv("TM_CHALLENGE_FAIL_THRESHOLD", "3")),
            repetitive_t1_threshold=int(os.getenv("TM_REPETITIVE_PATTERN_T1_THRESHOLD", "1")),
            repetitive_t2_threshold=int(os.getenv("TM_REPETITIVE_PATTERN_T2_THRESHOLD", "3")),
            block_on_token_mismatch=os.getenv("TM_BLOCK_ON_TOKEN_MISMATCH", "true").lower() == "true",
            strict_post_paths=tuple(
                p.strip()
                for p in os.getenv(
                    "TM_STRICT_POST_PATH_PREFIXES",
                    "/api/queue/,/api/holds,/api/payments",
                ).split(",")
                if p.strip()
            ),
        )


class DecisionPolicy:
    """Deterministic policy to unblock adapter/cloud integration."""

    def __init__(self, cfg: PolicyConfig, store: RuntimeStateStore) -> None:
        self._cfg = cfg
        self._store = store

    def evaluate(self, req: EvaluateRequest) -> tuple[EvaluateResponse, RuntimeStateSnapshot]:
        """Apply rules, persist runtime state, and return response."""
        started = time.perf_counter()
        decision_id = f"dec-{uuid.uuid4().hex[:12]}"
        now_ms = int(time.time() * 1000)
        rule_hits: list[str] = []

        prev = self._store.get(req.session_id) or RuntimeStateSnapshot(updated_ts_ms=now_ms)
        flow_state = req.flow_state or prev.flow_state
        incoming_tier = req.defense_tier or prev.defense_tier
        challenge_fail_count = max(req.challenge_fail_count, prev.challenge_fail_count)

        # R-3 token mismatch: immediate block.
        if self._cfg.block_on_token_mismatch and req.token_mismatch:
            rule_hits.append("R3_TOKEN_MISMATCH")
            resp = self._build_response(
                allow=False,
                req=req,
                flow_state="SX",
                defense_tier="T3",
                action="DEF_BLOCKED",
                reason="BLOCKED",
                risk_score=1.0,
                rule_hits=rule_hits,
                decision_id=decision_id,
                started=started,
            )
            snap = self._next_snapshot(prev, resp, challenge_fail_count, now_ms)
            self._store.upsert(req.session_id, snap)
            return resp, snap

        # R-2 challenge fail accumulation.
        if challenge_fail_count >= self._cfg.challenge_fail_threshold:
            rule_hits.append("R2_CHALLENGE_FAIL_THRESHOLD")
            resp = self._build_response(
                allow=False,
                req=req,
                flow_state="SX",
                defense_tier="T3",
                action="DEF_BLOCKED",
                reason="CHALLENGE_REQUIRED",
                risk_score=0.92,
                rule_hits=rule_hits,
                decision_id=decision_id,
                started=started,
            )
            snap = self._next_snapshot(prev, resp, challenge_fail_count, now_ms)
            self._store.upsert(req.session_id, snap)
            return resp, snap

        # F-5: at S6 no new friction except block.
        if flow_state == "S6":
            rule_hits.append("F5_NO_NEW_INTERVENTION_ON_S6")
            resp = self._build_response(
                allow=True,
                req=req,
                flow_state=flow_state,
                defense_tier=incoming_tier,
                action=None,
                reason=None,
                risk_score=max(prev.risk_score * 0.95, 0.05),
                rule_hits=rule_hits,
                decision_id=decision_id,
                started=started,
            )
            snap = self._next_snapshot(prev, resp, challenge_fail_count, now_ms)
            self._store.upsert(req.session_id, snap)
            return resp, snap

        # R-1 repetitive pattern.
        if req.repetitive_pattern_count >= self._cfg.repetitive_t2_threshold:
            rule_hits.append("R1_REPETITIVE_PATTERN_T2")
            resp = self._build_response(
                allow=False,
                req=req,
                flow_state="S3",
                defense_tier="T2",
                action="DEF_CHALLENGE_FORCED",
                reason="CHALLENGE_REQUIRED",
                risk_score=0.72,
                rule_hits=rule_hits,
                decision_id=decision_id,
                started=started,
            )
            snap = self._next_snapshot(prev, resp, challenge_fail_count, now_ms)
            self._store.upsert(req.session_id, snap)
            return resp, snap

        if req.repetitive_pattern_count >= self._cfg.repetitive_t1_threshold:
            rule_hits.append("R1_REPETITIVE_PATTERN_T1")
            resp = self._build_response(
                allow=True,
                req=req,
                flow_state=flow_state,
                defense_tier=self._max_tier(incoming_tier, "T1"),
                action="DEF_SANDBOXED",
                reason=None,
                risk_score=max(prev.risk_score, 0.35),
                rule_hits=rule_hits,
                decision_id=decision_id,
                started=started,
            )
            snap = self._next_snapshot(prev, resp, challenge_fail_count, now_ms)
            self._store.upsert(req.session_id, snap)
            return resp, snap

        # Strict POST path in elevated tiers.
        if (
            incoming_tier in ("T2", "T3")
            and req.method.upper() == "POST"
            and self._is_strict_path(req.path)
        ):
            rule_hits.append("STRICT_POST_PATH_CHALLENGE")
            resp = self._build_response(
                allow=False,
                req=req,
                flow_state="S3",
                defense_tier=incoming_tier,
                action="DEF_CHALLENGE_FORCED",
                reason="CHALLENGE_REQUIRED",
                risk_score=max(prev.risk_score, 0.62),
                rule_hits=rule_hits,
                decision_id=decision_id,
                started=started,
            )
            snap = self._next_snapshot(prev, resp, challenge_fail_count, now_ms)
            self._store.upsert(req.session_id, snap)
            return resp, snap

        # Default allow.
        rule_hits.append("DEFAULT_ALLOW")
        resp = self._build_response(
            allow=True,
            req=req,
            flow_state=flow_state,
            defense_tier=incoming_tier,
            action=None,
            reason=None,
            risk_score=max(prev.risk_score * 0.90, 0.05),
            rule_hits=rule_hits,
            decision_id=decision_id,
            started=started,
        )
        snap = self._next_snapshot(prev, resp, challenge_fail_count, now_ms)
        self._store.upsert(req.session_id, snap)
        return resp, snap

    def _is_strict_path(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in self._cfg.strict_post_paths)

    def _max_tier(self, a: str, b: str) -> str:
        return a if _TIER_RANK[a] >= _TIER_RANK[b] else b

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
        )

    def _build_response(
        self,
        *,
        allow: bool,
        req: EvaluateRequest,
        flow_state: str,
        defense_tier: str,
        action: str | None,
        reason: str | None,
        risk_score: float | None,
        rule_hits: list[str],
        decision_id: str,
        started: float,
    ) -> EvaluateResponse:
        headers: dict[str, str] = {"x-defense-policy-version": self._cfg.policy_version}
        if action == "DEF_BLOCKED":
            headers["x-defense-action"] = "blocked"
            headers["x-defense-tier"] = "T3"
            headers["x-block-reason"] = "policy_violation" if reason == "BLOCKED" else "blocked"
        elif action == "DEF_CHALLENGE_FORCED":
            headers["x-defense-action"] = "challenge"
            headers["x-defense-tier"] = defense_tier
            headers["x-challenge-type"] = "quiz"
        elif action == "DEF_SANDBOXED":
            headers["x-defense-action"] = "sandbox"
            headers["x-defense-tier"] = defense_tier

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        return EvaluateResponse(
            allow=allow,
            session_id=req.session_id,
            flow_state=flow_state,  # type: ignore[arg-type]
            defense_tier=defense_tier,  # type: ignore[arg-type]
            action=action,  # type: ignore[arg-type]
            reason=reason,
            rule_hits=rule_hits,
            risk_score=risk_score,
            policy_version=self._cfg.policy_version,
            headers_to_add=headers,
            decision_id=decision_id,
            latency_ms=latency_ms,
            version="v1",
        )
