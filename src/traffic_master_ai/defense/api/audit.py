"""Append-only JSONL audit logger for defense decisions."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from ..audit_contract import build_canonical_audit_row
from ..d0_mvp.observability.schemas import CANONICAL_AUDIT_EVENT_TYPES
from ..storage_env import load_audit_log_config_from_env, load_s3_archive_config_from_env
from .models import EvaluateRequest, EvaluateResponse, RuntimeStateSnapshot

logger = logging.getLogger(__name__)


class DefenseDecisionAuditLogger:
    """Writes one JSON object per line for each decision."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @classmethod
    def from_env(cls) -> DefenseDecisionAuditLogger:
        return cls(path=load_audit_log_config_from_env().file_path)

    def log(
        self,
        req: EvaluateRequest,
        resp: EvaluateResponse,
        runtime_state: RuntimeStateSnapshot,
    ) -> None:
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        payload = build_canonical_audit_row(
            ts_ms=now_ms,
            session_id=req.session_id,
            event_type="EVALUATE",
            raw_payload={
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
            },
            trace_id=req.trace_id,
            request_id=req.request_id,
            correlation_id=req.correlation_id,
            flow_state=resp.flow_state,
            risk_tier=resp.defense_tier,
            action=resp.action,
            reason_code=resp.reason,
            policy_version=resp.policy_version,
        )
        self._append_payload(payload)

    def log_target_evaluate_event(
        self,
        *,
        session_id: str,
        trace_id: str,
        request_path: str,
        request_method: str,
        target_event_type: str,
        action: str,
        flow_state: str,
        runtime_state: RuntimeStateSnapshot,
        reason_code: str | None = None,
        policy_version: str | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        payload = build_canonical_audit_row(
            ts_ms=now_ms,
            session_id=session_id,
            trace_id=trace_id,
            event_type="EVALUATE",
            flow_state=flow_state,
            action=action,
            reason_code=reason_code,
            policy_version=policy_version or runtime_state.policy_version,
            raw_payload={
                "decision_source": "target_api_early_return",
                "target_event_type": target_event_type,
                "path": request_path,
                "method": request_method.upper(),
                "allow": action == "NONE",
                "runtime_state": runtime_state.model_dump(by_alias=True),
                **(raw_payload or {}),
            },
        )
        self._append_payload(payload)

    def log_challenge_event(
        self,
        *,
        session_id: str,
        challenge_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        row = build_canonical_audit_row(
            ts_ms=now_ms,
            session_id=session_id,
            event_type=event_type,
            raw_payload=payload,
            challenge_id=challenge_id,
        )
        self._append_payload(row)

    @property
    def file_path(self) -> Path:
        return self._path

    def _append_payload(self, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("event_type", "")).strip()
        if event_type not in CANONICAL_AUDIT_EVENT_TYPES:
            raise ValueError(f"event_type not in canonical audit taxonomy: {event_type}")
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock, self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


class S3Uploader:
    """Handles uploading rotated log files to S3."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "ai-defense/audit/",
        region: Optional[str] = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        try:
            import boto3
            self._s3 = boto3.client("s3", region_name=region)
        except ImportError:
            logger.warning("boto3 not installed; S3Uploader will be inactive.")
            self._s3 = None

    @classmethod
    def from_env(cls) -> S3Uploader | None:
        """Build the S3 uploader from env or return None when archiving is disabled."""

        config = load_s3_archive_config_from_env()
        if not config.archive_enabled:
            return None
        return cls(
            bucket=config.bucket or "",
            prefix=config.prefix,
            region=config.region,
        )

    def upload_file(self, local_path: Path) -> bool:
        if not self._s3 or not local_path.exists():
            return False

        # Key format: {prefix}/YYYY/MM/DD/{filename}
        now = datetime.now(UTC)
        key = f"{self.prefix}/{now.strftime('%Y/%m/%d')}/{local_path.name}"
        
        try:
            self._s3.upload_file(str(local_path), self.bucket, key)
            logger.info("Successfully uploaded %s to s3://%s/%s", local_path.name, self.bucket, key)
            return True
        except Exception as exc:
            logger.error("Failed to upload %s to S3: %s", local_path.name, exc)
            return False


def rotate_and_upload_audit_log(
    logger_instance: DefenseDecisionAuditLogger,
    uploader: S3Uploader,
) -> None:
    """Rotates the current log file and uploads the old one to S3."""
    source_path = logger_instance.file_path
    if not source_path.exists() or source_path.stat().st_size == 0:
        return

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    rotated_path = source_path.with_name(f"{source_path.stem}_{timestamp}{source_path.suffix}")

    try:
        # Atomic rename to avoid losing logs during upload
        with logger_instance._lock:
            source_path.rename(rotated_path)
        
        if uploader.upload_file(rotated_path):
            rotated_path.unlink()  # Delete local copy after successful upload
    except Exception as exc:
        logger.error("Audit log rotation failed: %s", exc)


def list_pending_rotated_audit_logs(
    logger_instance: DefenseDecisionAuditLogger,
) -> tuple[Path, ...]:
    source_path = logger_instance.file_path
    pattern = f"{source_path.stem}_*{source_path.suffix}"
    return tuple(
        sorted(
            path
            for path in source_path.parent.glob(pattern)
            if path.is_file()
        )
    )


def upload_pending_rotated_audit_logs(
    logger_instance: DefenseDecisionAuditLogger,
    uploader: S3Uploader,
) -> tuple[Path, ...]:
    uploaded_paths: list[Path] = []
    for rotated_path in list_pending_rotated_audit_logs(logger_instance):
        if uploader.upload_file(rotated_path):
            rotated_path.unlink()
            uploaded_paths.append(rotated_path)
    return tuple(uploaded_paths)


def flush_audit_log_to_archive(
    logger_instance: DefenseDecisionAuditLogger,
    uploader: S3Uploader,
) -> None:
    upload_pending_rotated_audit_logs(logger_instance, uploader)
    rotate_and_upload_audit_log(logger_instance, uploader)
    upload_pending_rotated_audit_logs(logger_instance, uploader)
