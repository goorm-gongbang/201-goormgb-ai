"""Throttle actuator.

Ref: annex/throttle_spec.yaml
     — Adapter delay injection helper using policy-based endpoint scoping.
"""

from __future__ import annotations

import time
from typing import Optional

from ..core.enums import DefenseAction, DefenseTier
from ..policy.snapshot import PolicySnapshot


class ThrottleActuator:
    """Adapter delay injection helper.

    Ref: annex/throttle_spec.yaml#adapter_enforcement
    Gap 6: Uses PolicySnapshot for include/exclude path prefixes
    instead of hardcoded constants.
    """

    def resolve_delay_ms(
        self,
        *,
        action: DefenseAction,
        tier: DefenseTier,
        policy: PolicySnapshot,
        request_path: Optional[str],
        override_delay_ms: Optional[int] = None,
    ) -> int:
        """Resolve throttle delay by policy and endpoint scope.

        Ref: annex/throttle_spec.yaml#mvp_parameters
        """
        if action != DefenseAction.THROTTLE:
            return 0

        if not self._path_is_throttled(request_path, policy):
            return 0

        delay = (
            override_delay_ms
            if override_delay_ms is not None
            else policy.throttle_delay_for_tier(tier.value)
        )
        if delay < 0:
            delay = 0
        if delay > policy.throttle_max_delay_ms:
            delay = policy.throttle_max_delay_ms
        return int(delay)

    def apply_delay(self, delay_ms: int) -> None:
        """Apply blocking delay for ext_authz adapter path.

        Ref: annex/throttle_spec.yaml#adapter_enforcement.step_4
        """
        if delay_ms <= 0:
            return
        time.sleep(delay_ms / 1000.0)

    def _path_is_throttled(
        self,
        request_path: Optional[str],
        policy: PolicySnapshot,
    ) -> bool:
        """Check if the request path should be throttled.

        Gap 6: Uses policy.throttle_include/exclude_path_prefixes
        instead of hardcoded constants.
        Ref: annex/throttle_spec.yaml#endpoint_application
        """
        if not request_path:
            return False

        for prefix in policy.throttle_exclude_path_prefixes:
            if request_path.startswith(prefix):
                return False

        for prefix in policy.throttle_include_path_prefixes:
            if request_path.startswith(prefix):
                return True

        return False


__all__ = ["ThrottleActuator"]
