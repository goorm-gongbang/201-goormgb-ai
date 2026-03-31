"""Defense response contract constants for attack-side interpretation."""

from __future__ import annotations

from typing import Final


HTTP_BLOCKED: Final[int] = 403
HTTP_CHALLENGE_REQUIRED: Final[int] = 428

REASON_BLOCKED: Final[str] = "BLOCKED"
REASON_CHALLENGE_REQUIRED: Final[str] = "CHALLENGE_REQUIRED"


def is_blocked_response(http_status: int, reason_code: str | None) -> bool:
    return http_status == HTTP_BLOCKED or reason_code == REASON_BLOCKED


def is_challenge_required_response(http_status: int, reason_code: str | None) -> bool:
    return (
        http_status == HTTP_CHALLENGE_REQUIRED
        or reason_code == REASON_CHALLENGE_REQUIRED
    )

