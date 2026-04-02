"""Block state manager — tm:block-state:session:{sessionId} CRUD.

Ref: L1/runtime/state.yaml#redis.keyspace.block_key
     L1/runtime/state.yaml#schema.block_fields
     L1/runtime/state.yaml#atomicity_and_concurrency.terminal_first
"""

from __future__ import annotations

from typing import Any, Optional

from ..core.constants import BLOCK_TTL_SECONDS
from .keyspace import BLOCK_KEY_PREFIX
from .redis_client import RedisLike


class BlockStateManager:
    """Manages tm:block-state:session:{sessionId} Redis hash.

    terminal-first rule (state.yaml#atomicity_and_concurrency):
        If tm:block:{sessionId} exists, ALL subsequent decisions are BLOCK.
    """

    def __init__(
        self,
        redis: RedisLike,
        block_ttl_s: int = BLOCK_TTL_SECONDS,
    ) -> None:
        self._redis = redis
        self._block_ttl_s = block_ttl_s

    @staticmethod
    def block_key(session_id: str) -> str:
        return f"{BLOCK_KEY_PREFIX}{session_id}"

    def is_blocked(self, session_id: str) -> bool:
        """Check if session is currently blocked.

        Ref: state.yaml#atomicity_and_concurrency.terminal_first
        """
        return self._redis.exists(self.block_key(session_id)) > 0

    def get_block(self, session_id: str) -> Optional[dict[str, Any]]:
        """Read block state if exists."""
        raw = self._redis.hgetall(self.block_key(session_id))
        return raw if raw else None

    def set_block(
        self,
        session_id: str,
        blocked_at_ms: int,
        reason_code: str = "BLOCKED",
        policy_version: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Create block persistence.

        Ref: state.yaml#schema.block_fields.value_schema
             policy_v1.yaml#block.persistence
        """
        effective_ttl_s = self._block_ttl_s if ttl_seconds is None else max(1, int(ttl_seconds))
        blocked_until_ms = blocked_at_ms + (effective_ttl_s * 1000)
        data: dict[str, Any] = {
            "blockedAtMs": blocked_at_ms,
            "blockedUntilMs": blocked_until_ms,
        }
        if reason_code:
            data["reasonCode"] = reason_code
        if policy_version:
            data["policyVersion"] = policy_version

        key = self.block_key(session_id)
        self._redis.hset(key, data)
        self._redis.expire(key, effective_ttl_s)

    def get_block_ttl_seconds(self, session_id: str) -> Optional[int]:
        """Return the remaining TTL for one persisted block key."""
        ttl = self._redis.ttl(self.block_key(session_id))
        if ttl < 0:
            return None
        return ttl

    def remove_block(self, session_id: str) -> None:
        """Remove block (admin/test use only)."""
        self._redis.delete(self.block_key(session_id))
