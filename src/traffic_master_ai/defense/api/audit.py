"""Append-only JSONL audit logger for defense decisions."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from .models import EvaluateRequest, EvaluateResponse, RuntimeStateSnapshot


class DefenseDecisionAuditLogger:
    """Writes one JSON object per line for each decision."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @classmethod
    def from_env(cls) -> DefenseDecisionAuditLogger:
        path = os.getenv("TM_DEFENSE_AUDIT_LOG_PATH", "logs/defense_decision_audit.jsonl")
        return cls(path=path)

    def log(
        self,
        req: EvaluateRequest,
        resp: EvaluateResponse,
        runtime_state: RuntimeStateSnapshot,
    ) -> None:
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        payload: dict[str, Any] = {
            "ts_ms": now_ms,
            "session_id": req.session_id,
            "trace_id": req.trace_id,
            "request_id": req.request_id,
            "correlation_id": req.correlation_id,
            "flow_state": resp.flow_state,
            "event_type": "EVALUATE",
            "defense_tier": resp.defense_tier,
            "action": resp.action,
            "reason_code": resp.reason,
            "policy_version": resp.policy_version,
            "decision_id": resp.decision_id,
            "risk_score": resp.risk_score,
            "rule_hits": resp.rule_hits,
            "path": req.path,
            "method": req.method.upper(),
            "allow": resp.allow,
            "runtime_state": runtime_state.model_dump(),
            "telemetry_features": (
                req.telemetry_features.model_dump(by_alias=True)
                if req.telemetry_features is not None
                else None
            ),
        }
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock, self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def log_challenge_event(
        self,
        *,
        session_id: str,
        challenge_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        line = json.dumps(
            {
                "ts_ms": now_ms,
                "session_id": session_id,
                "challenge_id": challenge_id,
                "event_type": event_type,
                "payload": payload,
            },
            ensure_ascii=False,
        )
        with self._lock, self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
