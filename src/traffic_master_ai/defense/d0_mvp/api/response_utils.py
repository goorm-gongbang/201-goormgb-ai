"""Shared API response shaping helpers."""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional

from ..core.enums import ReasonCode
from .compat import Response


def error_payload(
    reason_code: ReasonCode | str,
    message: str,
    detail: Optional[Mapping[str, Any]] = None,
    terminal_reason: Optional[str] = None,
) -> dict[str, Any]:
    """Build an SSOT-aligned root error envelope."""
    resolved = reason_code.value if isinstance(reason_code, ReasonCode) else str(reason_code)
    body: dict[str, Any] = {
        "status": "FAIL",
        "reasonCode": resolved,
        "message": message,
    }
    if detail:
        body["detail"] = dict(detail)
    if terminal_reason:
        body["terminalReason"] = terminal_reason
    return body

def finalize_payload(
    payload: Mapping[str, Any],
    *,
    response: Response | None,
    status_code: int = 200,
    headers: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Apply status/headers when FastAPI injects Response.

    When the compatibility shim is used and no Response instance is passed,
    keep direct-call ergonomics by embedding status/header metadata in the body.
    """
    body = dict(payload)
    if response is not None:
        response.status_code = status_code
        if headers:
            response.headers.update(dict(headers))
        return body
    if status_code != 200:
        body["httpStatus"] = status_code
    if headers:
        body["headers"] = dict(headers)
    return body


def merge_headers(
    base: Optional[Mapping[str, str]],
    extra: Optional[Mapping[str, str]],
) -> dict[str, str]:
    merged: dict[str, str] = {}
    if base:
        merged.update(dict(base))
    if extra:
        merged.update(dict(extra))
    return merged


def parse_request_meta_headers(
    *,
    x_correlation_id: Optional[str],
    x_tm_test_mode: Optional[str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Parse optional request meta headers and return runtime meta + passthrough headers."""
    meta: dict[str, Any] = {}
    passthrough_headers: dict[str, str] = {}

    if x_correlation_id:
        meta["correlationId"] = x_correlation_id
        passthrough_headers["x-correlation-id"] = x_correlation_id

    if x_tm_test_mode is not None:
        if not _is_test_mode_enabled():
            raise ValueError("X-TM-TestMode is disabled")
        parsed_test_mode = _parse_bool_header(x_tm_test_mode)
        if parsed_test_mode is None:
            raise ValueError("X-TM-TestMode must be boolean (true/false/1/0)")
        meta["testMode"] = parsed_test_mode
    return meta, passthrough_headers


def infer_terminal_reason(
    *,
    reason_code: Optional[str],
    action: Optional[str] = None,
    state_to: Optional[str] = None,
) -> Optional[str]:
    if reason_code == ReasonCode.BLOCKED.value or action == "BLOCK":
        return "BLOCKED"
    if state_to == "SX":
        return "DONE"
    if reason_code in {
        ReasonCode.INVALID_TRANSITION.value,
        ReasonCode.INTERNAL_ERROR.value,
        ReasonCode.CHALLENGE_VERIFY_UNAVAILABLE.value,
    }:
        return "ABORT"
    return None


def _is_test_mode_enabled() -> bool:
    raw = str(os.environ.get("TM_TEST_MODE_ENABLED", "false")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _parse_bool_header(raw: str) -> Optional[bool]:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None

__all__ = [
    "error_payload",
    "finalize_payload",
    "infer_terminal_reason",
    "merge_headers",
    "parse_request_meta_headers",
]
