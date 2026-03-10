"""Shared API response shaping helpers."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..core.enums import ReasonCode
from .compat import Response


def error_payload(
    reason_code: ReasonCode | str,
    message: str,
    detail: Optional[Mapping[str, Any]] = None,
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

__all__ = ["error_payload", "finalize_payload"]
