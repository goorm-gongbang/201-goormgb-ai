"""Runtime event dataclass.

Ref: L1/runtime/events.yaml#common_context.schema
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..core.enums import FlowState
from .catalog import validate_runtime_event_envelope


@dataclass(slots=True)
class RuntimeEvent:
    """Incoming runtime event matching events.yaml#common_context.schema.

    All fields align with the common_context.schema + payload extensions.
    """

    # --- required (common_context.schema) ---
    event_type: str
    ts_ms: int
    flow_state: FlowState

    # --- identifiers (from headers) ---
    session_id: str = ""
    trace_id: str = ""

    # --- optional (common_context.schema) ---
    request_path: Optional[str] = None
    request_method: Optional[str] = None
    source: Optional[str] = None  # "FE" | "ADAPTER" | "AI_RUNTIME" | "BE"

    # --- payload (event-type-specific fields) ---
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def from_state(self) -> Optional[str]:
        """FLOW_STATE_TRANSITION.fromState."""
        return self.payload.get("fromState")

    @property
    def to_state(self) -> Optional[str]:
        """FLOW_STATE_TRANSITION.toState."""
        return self.payload.get("toState")

    @property
    def hvc_tag(self) -> Optional[str]:
        """HIGH_VALUE_CLICK.tag."""
        return self.payload.get("tag")

    @property
    def s3_result(self) -> Optional[str]:
        """S3_RESULT.result (PASS/FAIL/UNKNOWN)."""
        return self.payload.get("result")

    @property
    def external_score(self) -> Optional[float]:
        """TURNSTILE_VERIFIED.externalScore."""
        val = self.payload.get("externalScore")
        return float(val) if val is not None else None

    @property
    def verify_status(self) -> Optional[str]:
        """TURNSTILE_VERIFIED.verifyStatus."""
        return self.payload.get("verifyStatus")

    def validate(self) -> list[str]:
        """Validate common context + payload against events catalog."""
        return validate_runtime_event_envelope(
            event_type=self.event_type,
            ts_ms=self.ts_ms,
            flow_state=self.flow_state.value,
            payload=self.payload,
        )
