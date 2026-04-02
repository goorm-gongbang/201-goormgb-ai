"""Auth-Guard internal block API integration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 2.0
_INTERNAL_API_KEY_HEADER = "X-Internal-Api-Key"


@dataclass(frozen=True, slots=True)
class AuthGuardConfig:
    """Runtime configuration for Auth-Guard internal API."""

    base_url: str
    internal_api_key: str
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> Optional["AuthGuardConfig"]:
        base_url = (os.getenv("AUTH_GUARD_URL") or "").strip().rstrip("/")
        internal_api_key = (os.getenv("INTERNAL_API_KEY") or "").strip()
        if not base_url or not internal_api_key:
            return None
        return cls(base_url=base_url, internal_api_key=internal_api_key)


@dataclass(frozen=True, slots=True)
class BlockUserResult:
    """Normalized result for Auth-Guard block attempts."""

    outcome: str
    http_status: Optional[int] = None
    code: Optional[str] = None
    message: Optional[str] = None

    @property
    def treated_as_success(self) -> bool:
        return self.outcome in {"blocked", "already_blocked"}


class UserBlocker(Protocol):
    """Protocol used by callers that need best-effort user blocking."""

    def block_user(
        self,
        *,
        user_id: str,
        session_id: str,
        trace_id: str,
        trigger: str,
        ) -> BlockUserResult:
        """Attempt to block one user in Auth-Guard."""


class SyncHttpClient(Protocol):
    """Minimal sync HTTP client interface for Auth-Guard calls."""

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> httpx.Response:
        """Send one POST request."""

    def close(self) -> None:
        """Release any underlying resources."""


class AuthGuardBlockService:
    """Best-effort Auth-Guard block client with categorized logging."""

    def __init__(
        self,
        config: Optional[AuthGuardConfig] = None,
        http_client: Optional[SyncHttpClient] = None,
    ) -> None:
        self._config = config
        self._http_client = http_client or httpx.Client()
        self._owns_http_client = http_client is None

    @classmethod
    def from_env(cls) -> "AuthGuardBlockService":
        return cls(config=AuthGuardConfig.from_env())

    def close(self) -> None:
        if not self._owns_http_client:
            return
        self._http_client.close()

    def block_user(
        self,
        *,
        user_id: str,
        session_id: str,
        trace_id: str,
        trigger: str,
    ) -> BlockUserResult:
        normalized_user_id = str(user_id).strip()
        if not normalized_user_id:
            logger.warning(
                "Auth-Guard block skipped: missing user_id session_id=%s trace_id=%s trigger=%s",
                session_id,
                trace_id,
                trigger,
            )
            return BlockUserResult(outcome="skipped_missing_user_id")

        if self._config is None:
            logger.warning(
                "Auth-Guard block skipped: config missing user_id=%s session_id=%s trace_id=%s trigger=%s",
                normalized_user_id,
                session_id,
                trace_id,
                trigger,
            )
            return BlockUserResult(outcome="disabled")

        url = (
            f"{self._config.base_url}/internal/users/"
            f"{quote(normalized_user_id, safe='')}/block"
        )
        headers = {_INTERNAL_API_KEY_HEADER: self._config.internal_api_key}

        try:
            response = self._http_client.post(
                url,
                headers=headers,
                timeout=self._config.timeout_seconds,
            )
        except httpx.RequestError as exc:
            logger.error(
                "Auth-Guard block request failed: user_id=%s session_id=%s trace_id=%s trigger=%s error=%s",
                normalized_user_id,
                session_id,
                trace_id,
                trigger,
                exc,
            )
            return BlockUserResult(outcome="request_error", message=str(exc))

        payload = _response_payload(response)
        code = _payload_str(payload, "code")
        message = _payload_str(payload, "message")
        result = _to_result(
            status_code=response.status_code,
            code=code,
            message=message,
        )
        self._log_result(
            result=result,
            user_id=normalized_user_id,
            session_id=session_id,
            trace_id=trace_id,
            trigger=trigger,
        )
        return result

    def _log_result(
        self,
        *,
        result: BlockUserResult,
        user_id: str,
        session_id: str,
        trace_id: str,
        trigger: str,
    ) -> None:
        if result.outcome == "blocked":
            logger.info(
                "Auth-Guard block synced: user_id=%s session_id=%s trace_id=%s trigger=%s",
                user_id,
                session_id,
                trace_id,
                trigger,
            )
            return
        if result.outcome == "already_blocked":
            logger.info(
                "Auth-Guard block already applied: user_id=%s session_id=%s trace_id=%s trigger=%s",
                user_id,
                session_id,
                trace_id,
                trigger,
            )
            return
        log_message = (
            "Auth-Guard block not synchronized: user_id=%s session_id=%s trace_id=%s "
            "trigger=%s outcome=%s status=%s code=%s message=%s"
        )
        log_args = (
            user_id,
            session_id,
            trace_id,
            trigger,
            result.outcome,
            result.http_status,
            result.code,
            result.message,
        )
        if result.outcome == "not_found":
            logger.warning(log_message, *log_args)
            return
        logger.error(log_message, *log_args)


def _response_payload(response: httpx.Response) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _payload_str(payload: Mapping[str, Any], key: str) -> Optional[str]:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_result(
    *,
    status_code: int,
    code: Optional[str],
    message: Optional[str],
) -> BlockUserResult:
    if 200 <= status_code < 300:
        return BlockUserResult(
            outcome="blocked",
            http_status=status_code,
            code=code,
            message=message,
        )
    if status_code == 409:
        return BlockUserResult(
            outcome="already_blocked",
            http_status=status_code,
            code=code,
            message=message,
        )
    if status_code == 404:
        return BlockUserResult(
            outcome="not_found",
            http_status=status_code,
            code=code,
            message=message,
        )
    if status_code == 401:
        return BlockUserResult(
            outcome="unauthorized",
            http_status=status_code,
            code=code,
            message=message,
        )
    return BlockUserResult(
        outcome="unexpected_status",
        http_status=status_code,
        code=code,
        message=message,
    )


__all__ = [
    "AuthGuardBlockService",
    "AuthGuardConfig",
    "BlockUserResult",
    "UserBlocker",
]
