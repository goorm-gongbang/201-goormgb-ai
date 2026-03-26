"""Append-only JSONL audit logger for defense decisions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from .models import EvaluateRequest, EvaluateResponse, RuntimeStateSnapshot
from .settings import read_str


class S3Uploader:
    """Best-effort S3 uploader used by background archive loop."""

    def __init__(self, *, bucket: str, prefix: str = "", region: str | None = None) -> None:
        self._bucket = bucket
        self._prefix = prefix
        self._region = region

    def upload_file(self, src: Path, key: str) -> None:
        try:
            import boto3  # type: ignore
        except Exception:
            return

        kwargs: dict[str, Any] = {}
        if self._region:
            kwargs["region_name"] = self._region
        client = boto3.client("s3", **kwargs)
        client.upload_file(str(src), self._bucket, key)


class DefenseDecisionAuditLogger:
    """Writes one JSON object per line for each decision."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @classmethod
    def from_settings(cls) -> DefenseDecisionAuditLogger:
        path = read_str("TM_DEFENSE_AUDIT_LOG_PATH", "logs/defense_decision_audit.jsonl")
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


def rotate_and_upload_audit_log(audit: DefenseDecisionAuditLogger, uploader: S3Uploader) -> None:
    """Rotate current audit log and upload rotated file to S3."""

    src_path = audit._path
    if not src_path.exists() or src_path.stat().st_size <= 0:
        return

    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rotated_name = f"{src_path.name}.{now}"
    rotated_path = src_path.with_name(rotated_name)

    with audit._lock:
        if not src_path.exists() or src_path.stat().st_size <= 0:
            return
        src_path.rename(rotated_path)

    key = f"{uploader._prefix}{rotated_name}"
    try:
        uploader.upload_file(rotated_path, key)
    finally:
        rotated_path.unlink(missing_ok=True)
