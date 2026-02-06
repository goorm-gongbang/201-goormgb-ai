"""Decision Log Schema for Defense PoC-0 Audit Trail.

Provides machine-readable and human-readable log entries for
every decision made by the Defense Engine.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class DecisionLogEntry:
    """A single decision log entry capturing engine and brain state.

    All top-level fields must always exist (no key deletion).
    Values may be None when not applicable.

    Attributes:
        ts: Timestamp of the decision (ISO8601 when serialized).
        trace_id: Scenario ID or Session ID for correlation.
        seq: Sequence number within the trace.
        event: Event context (type, event_id, source, payload_summary).
        state_transition: Flow state change (from, to).
        tier_transition: Defense tier change (from, to).
        evidence_snapshot: Brain evidence state at decision time.
        decision: Planned actions and terminal outcomes.
    """

    ts: datetime
    trace_id: str
    seq: int
    event: Dict[str, Any]
    state_transition: Dict[str, Optional[str]]
    tier_transition: Dict[str, Optional[str]]
    evidence_snapshot: Dict[str, Any]
    decision: Dict[str, Any]

    @staticmethod
    def create_event_dict(
        event_type: str,
        event_id: str,
        source: str,
        payload_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a standardized event dictionary.

        Args:
            event_type: Canonical event type string.
            event_id: Unique event identifier.
            source: Event source (PAGE, SERVER, etc.).
            payload_summary: Optional summary of event payload.

        Returns:
            Event dictionary with required keys.
        """
        return {
            "type": event_type,
            "event_id": event_id,
            "source": source,
            "payload_summary": payload_summary,
        }

    @staticmethod
    def create_state_transition(
        from_state: Optional[str],
        to_state: Optional[str],
    ) -> Dict[str, Optional[str]]:
        """Create a state transition dictionary.

        Args:
            from_state: Previous flow state value.
            to_state: New flow state value.

        Returns:
            State transition dictionary.
        """
        return {"from": from_state, "to": to_state}

    @staticmethod
    def create_tier_transition(
        from_tier: Optional[str],
        to_tier: Optional[str],
    ) -> Dict[str, Optional[str]]:
        """Create a tier transition dictionary.

        Args:
            from_tier: Previous defense tier value.
            to_tier: New defense tier value.

        Returns:
            Tier transition dictionary.
        """
        return {"from": from_tier, "to": to_tier}

    @staticmethod
    def create_evidence_snapshot(
        last_signal_ts: Optional[int] = None,
        challenge_fail_count: int = 0,
        seat_taken_streak: int = 0,
        token_mismatch_detected: bool = False,
        signal_history: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create an evidence snapshot dictionary from EvidenceState fields.

        Args:
            last_signal_ts: Timestamp of last signal event.
            challenge_fail_count: Number of consecutive challenge failures.
            seat_taken_streak: Number of consecutive seat-taken events.
            token_mismatch_detected: Whether token mismatch was detected.
            signal_history: List of recent signal types.

        Returns:
            Evidence snapshot dictionary.
        """
        return {
            "last_signal_ts": last_signal_ts,
            "challenge_fail_count": challenge_fail_count,
            "seat_taken_streak": seat_taken_streak,
            "token_mismatch_detected": token_mismatch_detected,
            "signal_history": signal_history or [],
        }

    @staticmethod
    def create_decision(
        planned_actions: Optional[List[str]] = None,
        terminal_reason: Optional[str] = None,
        failure_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a decision dictionary.

        Args:
            planned_actions: List of planned action types.
            terminal_reason: Terminal reason if flow ended.
            failure_code: Failure code if applicable.

        Returns:
            Decision dictionary.
        """
        return {
            "planned_actions": planned_actions or [],
            "terminal_reason": terminal_reason,
            "failure_code": failure_code,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary.

        Converts datetime to ISO8601 string format.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        result = asdict(self)
        # Convert datetime to ISO8601 string
        result["ts"] = self.ts.isoformat()
        return result

    def to_json(self, indent: Optional[int] = None) -> str:
        """Convert to JSON string.

        Args:
            indent: Optional indentation for pretty printing.

        Returns:
            JSON string representation.
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def log_entry_from_step_result(
    trace_id: str,
    step_result: Any,  # StepResult from scenarios
    evidence: Any,  # EvidenceState from brain
    ts: Optional[datetime] = None,
) -> DecisionLogEntry:
    """Create a DecisionLogEntry from a ScenarioRunner step result.

    Args:
        trace_id: Scenario or session ID.
        step_result: StepResult object from runner execution.
        evidence: EvidenceState at decision time.
        ts: Timestamp (defaults to now).

    Returns:
        DecisionLogEntry instance.
    """
    if ts is None:
        ts = datetime.now()

    return DecisionLogEntry(
        ts=ts,
        trace_id=trace_id,
        seq=step_result.seq,
        event=DecisionLogEntry.create_event_dict(
            event_type=step_result.input_event_type,
            event_id=f"evt-{step_result.seq:04d}",
            source="PAGE",  # Default source
            payload_summary=None,
        ),
        state_transition=DecisionLogEntry.create_state_transition(
            from_state=step_result.from_state.value,
            to_state=step_result.to_state.value,
        ),
        tier_transition=DecisionLogEntry.create_tier_transition(
            from_tier=step_result.from_tier.value,
            to_tier=step_result.to_tier.value,
        ),
        evidence_snapshot=DecisionLogEntry.create_evidence_snapshot(
            last_signal_ts=evidence.last_signal_ts if hasattr(evidence, "last_signal_ts") else None,
            challenge_fail_count=getattr(evidence, "challenge_fail_count", 0),
            seat_taken_streak=getattr(evidence, "seat_taken_streak", 0),
            token_mismatch_detected=getattr(evidence, "token_mismatch_detected", False),
            signal_history=list(evidence.signal_history) if hasattr(evidence, "signal_history") else [],
        ),
        decision=DecisionLogEntry.create_decision(
            planned_actions=step_result.planned_actions,
            terminal_reason=step_result.terminal_reason.value if step_result.terminal_reason else None,
            failure_code=step_result.failure_code.value if step_result.failure_code else None,
        ),
    )


__all__ = [
    "DecisionLogEntry",
    "log_entry_from_step_result",
]
