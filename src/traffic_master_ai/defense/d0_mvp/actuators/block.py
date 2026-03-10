"""Block actuator.

Ref: annex/block_spec.yaml
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..core.enums import ReasonCode
from ..core.models import ErrorResponse
from ..state.block_state import BlockStateManager


@dataclass(slots=True, frozen=True)
class BlockResult:
    """Block enforcement output."""

    http_status: int
    reason_code: ReasonCode
    body: ErrorResponse
    headers: dict[str, str]


class BlockActuator:
    """Persisted block enforcer."""

    def __init__(self, block_state: BlockStateManager) -> None:
        self._block_state = block_state

    def enforce(
        self,
        *,
        session_id: str,
        tier: str,
        policy_version: str,
        blocked_at_ms: int,
        block_ttl_seconds: int,
    ) -> BlockResult:
        """Persist block state and build deny response contract."""
        self._block_state.set_block(
            session_id=session_id,
            blocked_at_ms=blocked_at_ms,
            reason_code=ReasonCode.BLOCKED.value,
            policy_version=policy_version,
            ttl_seconds=block_ttl_seconds,
        )
        headers = {
            "x-defense-tier": tier,
            "x-defense-action": "BLOCK",
            "x-defense-policy-version": policy_version,
            "x-defense-block-ttl-seconds": str(block_ttl_seconds),
        }
        return BlockResult(
            http_status=403,
            reason_code=ReasonCode.BLOCKED,
            body=ErrorResponse.from_reason(
                reason_code=ReasonCode.BLOCKED,
                message="요청이 차단되었습니다.",
            ),
            headers=headers,
        )


__all__ = ["BlockActuator", "BlockResult"]
