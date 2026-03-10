"""Analyzer implementation for D0-MVP.

Ref: annex/analyzer_spec.yaml
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..core.constants import (
    RAPID_HV_THRESHOLD,
    RAPID_HV_WINDOW_MS,
    S3_FAIL_BURST_THRESHOLD,
    S3_FAIL_BURST_WINDOW_S,
    SCAN_THRESHOLD,
    SCAN_WINDOW_MS,
)
from ..core.models import SessionState
from ..events.catalog import API_CALL_OBS, HIGH_VALUE_CLICK, S3_FAIL, S3_PASS, S3_RESULT
from ..events.common import RuntimeEvent
from ..policy.snapshot import PolicySnapshot
from ..state.dedup import DedupChecker
from ..state.redis_client import RedisLike
from ..state.session_state import SessionStateManager


@dataclass(slots=True, frozen=True)
class EvidenceUpdate:
    """Analyzer evidence update payload."""

    rule_hits: tuple[str, ...]
    missing_flags: tuple[str, ...]
    derived_signals: dict[str, bool]
    counters_snapshot: dict[str, int]
    notes: Optional[str] = None


@dataclass(slots=True, frozen=True)
class EvidenceSummaryForPlanner:
    """Compact evidence summary consumed by Planner."""

    flow_state: str
    tier: str
    in_probation: bool
    s3_passed: bool
    s3_failed_recently: bool
    scan_pressure: str
    hv_click_pressure: str
    counters: dict[str, int]


@dataclass(slots=True, frozen=True)
class AnalyzerOutput:
    """Analyzer stage output contract."""

    evidence_update: EvidenceUpdate
    evidence_summary_for_planner: EvidenceSummaryForPlanner
    is_duplicate: bool
    dedup_key: Optional[str] = None


class Analyzer:
    """Deterministic counter/evidence updater.

    Ref: annex/analyzer_spec.yaml#derived_signals, #redis_updates, #outputs
    """

    def __init__(
        self,
        *,
        redis: RedisLike,
        session_state: SessionStateManager,
        dedup: Optional[DedupChecker] = None,
        rapid_hv_window_ms: int = RAPID_HV_WINDOW_MS,
        rapid_hv_threshold: int = RAPID_HV_THRESHOLD,
        scan_window_ms: int = SCAN_WINDOW_MS,
        scan_threshold: int = SCAN_THRESHOLD,
        s3_fail_burst_window_s: int = S3_FAIL_BURST_WINDOW_S,
        s3_fail_burst_threshold: int = S3_FAIL_BURST_THRESHOLD,
    ) -> None:
        self._redis = redis
        self._session_state = session_state
        self._dedup = dedup
        self._rapid_hv_window_ms = rapid_hv_window_ms
        self._rapid_hv_threshold = rapid_hv_threshold
        self._scan_window_ms = scan_window_ms
        self._scan_threshold = scan_threshold
        self._s3_fail_burst_window_s = s3_fail_burst_window_s
        self._s3_fail_burst_threshold = s3_fail_burst_threshold

    def analyze(
        self,
        *,
        session_id: str,
        trace_id: str,
        event: RuntimeEvent,
        state: SessionState,
        policy: PolicySnapshot,
    ) -> AnalyzerOutput:
        """Update counters/evidence for one event.

        Dedup behavior: duplicate event -> no-op for counters.
        """
        dedup_key: Optional[str] = None
        is_duplicate = False
        if self._dedup is not None:
            dedup_key = self._dedup.dedup_key(trace_id, event.event_type, event.ts_ms)
            is_duplicate = self._dedup.check_and_mark(trace_id, event.event_type, event.ts_ms)

        now_ms = int(time.time() * 1000)
        challenge_fail_count = state.challenge_fail_count
        seat_taken_streak = state.seat_taken_streak
        hold_fail_streak = state.hold_fail_streak
        probation_until_ms = state.probation_until_ms

        rule_hits: list[str] = []
        missing_flags: list[str] = []

        hv_count = self._window_count_read(
            "hv", session_id, event.ts_ms, self._rapid_hv_window_ms
        )
        scan_count = self._window_count_read(
            "scan", session_id, event.ts_ms, self._scan_window_ms
        )
        s3_fail_count = self._window_count_read(
            "s3fail",
            session_id,
            event.ts_ms,
            self._s3_fail_burst_window_s * 1000,
        )

        if not is_duplicate:
            if event.event_type == HIGH_VALUE_CLICK:
                hv_count = self._window_count_inc(
                    "hv", session_id, event.ts_ms, self._rapid_hv_window_ms
                )
                rule_hits.append("HIGH_VALUE_CLICK_OBSERVED")

                hold_result = str(event.payload.get("holdResult", "")).upper()
                if hold_result == "FAIL":
                    hold_fail_streak = self._session_state.increment_by_role(
                        "analyzer",
                        session_id,
                        "holdFailStreak",
                        amount=1,
                        is_allow=False,
                    )
                    seat_taken_streak = 0
                    self._session_state.update_by_role(
                        "analyzer",
                        session_id,
                        {"seatTakenStreak": 0},
                        is_allow=False,
                    )
                    rule_hits.append("HOLD_FAIL")
                elif hold_result == "SUCCESS":
                    seat_taken_streak = self._session_state.increment_by_role(
                        "analyzer",
                        session_id,
                        "seatTakenStreak",
                        amount=1,
                        is_allow=False,
                    )
                    hold_fail_streak = 0
                    self._session_state.update_by_role(
                        "analyzer",
                        session_id,
                        {"holdFailStreak": 0},
                        is_allow=False,
                    )
                    rule_hits.append("HOLD_SUCCESS")

            elif event.event_type == API_CALL_OBS:
                category = str(event.payload.get("category", "")).upper()
                method = str(event.payload.get("method", "")).upper()
                path = str(event.payload.get("path", event.request_path or ""))
                if category == "READ" or method == "GET":
                    scan_count = self._window_count_inc(
                        "scan", session_id, event.ts_ms, self._scan_window_ms
                    )
                    rule_hits.append("SCAN_READ_CALL")

                hold_status = event.payload.get("statusCode")
                if isinstance(hold_status, int) and path.startswith("/api/hold"):
                    if hold_status >= 400:
                        hold_fail_streak = self._session_state.increment_by_role(
                            "analyzer",
                            session_id,
                            "holdFailStreak",
                            amount=1,
                            is_allow=False,
                        )
                        seat_taken_streak = 0
                        self._session_state.update_by_role(
                            "analyzer",
                            session_id,
                            {"seatTakenStreak": 0},
                            is_allow=False,
                        )
                        rule_hits.append("HOLD_FAIL")
                    elif hold_status < 300:
                        seat_taken_streak = self._session_state.increment_by_role(
                            "analyzer",
                            session_id,
                            "seatTakenStreak",
                            amount=1,
                            is_allow=False,
                        )
                        hold_fail_streak = 0
                        self._session_state.update_by_role(
                            "analyzer",
                            session_id,
                            {"holdFailStreak": 0},
                            is_allow=False,
                        )
                        rule_hits.append("HOLD_SUCCESS")

            elif event.event_type == S3_RESULT:
                result = event.s3_result or str(event.payload.get("result", ""))
                if result == S3_FAIL:
                    challenge_fail_count = self._session_state.increment_by_role(
                        "analyzer",
                        session_id,
                        "challengeFailCount",
                        amount=1,
                        is_allow=False,
                    )
                    s3_fail_count = self._window_count_inc(
                        "s3fail",
                        session_id,
                        event.ts_ms,
                        self._s3_fail_burst_window_s * 1000,
                    )
                    rule_hits.append("S3_FAIL")
                elif result == S3_PASS:
                    challenge_fail_count = 0
                    probation_until_ms = (
                        now_ms + (policy.probation_seconds_after_s3_pass * 1000)
                    )
                    self._session_state.update_by_role(
                        "analyzer",
                        session_id,
                        {
                            "challengeFailCount": 0,
                            "probationUntilMs": probation_until_ms,
                        },
                        is_allow=False,
                    )
                    rule_hits.append("S3_PASS")

            changes: dict[str, Any] = {
                "challengeFailCount": challenge_fail_count,
                "seatTakenStreak": seat_taken_streak,
                "holdFailStreak": hold_fail_streak,
            }
            if probation_until_ms is not None:
                changes["probationUntilMs"] = probation_until_ms

            if event.event_type not in {HIGH_VALUE_CLICK, API_CALL_OBS, S3_RESULT}:
                self._session_state.update_by_role(
                    "analyzer",
                    session_id,
                    changes,
                    is_allow=False,
                )

        derived_signals = {
            "rapid_high_value_click": hv_count >= self._rapid_hv_threshold,
            "excessive_read_scanning": scan_count >= self._scan_threshold,
            "s3_fail_burst": s3_fail_count >= self._s3_fail_burst_threshold,
        }

        if derived_signals["rapid_high_value_click"]:
            rule_hits.append("RAPID_HIGH_VALUE_CLICK")
        if derived_signals["excessive_read_scanning"]:
            rule_hits.append("EXCESSIVE_READ_SCANNING")
        if derived_signals["s3_fail_burst"]:
            rule_hits.append("S3_FAIL_BURST")

        counters_snapshot = {
            "challengeFailCount": challenge_fail_count,
            "seatTakenStreak": seat_taken_streak,
            "holdFailStreak": hold_fail_streak,
        }

        in_probation = bool(probation_until_ms is not None and now_ms < probation_until_ms)

        evidence_update = EvidenceUpdate(
            rule_hits=tuple(rule_hits),
            missing_flags=tuple(missing_flags),
            derived_signals=derived_signals,
            counters_snapshot=counters_snapshot,
        )

        evidence_summary = EvidenceSummaryForPlanner(
            flow_state=event.flow_state.value,
            tier=state.defense_tier.value,
            in_probation=in_probation,
            s3_passed=state.s3_passed,
            s3_failed_recently=derived_signals["s3_fail_burst"],
            scan_pressure=_pressure(scan_count, self._scan_threshold),
            hv_click_pressure=_pressure(hv_count, self._rapid_hv_threshold),
            counters={
                "challengeFailCount": challenge_fail_count,
                "holdFailStreak": hold_fail_streak,
            },
        )

        return AnalyzerOutput(
            evidence_update=evidence_update,
            evidence_summary_for_planner=evidence_summary,
            is_duplicate=is_duplicate,
            dedup_key=dedup_key,
        )

    def _window_count_inc(
        self,
        metric: str,
        session_id: str,
        ts_ms: int,
        window_ms: int,
    ) -> int:
        key = self._window_key(metric, session_id, ts_ms, window_ms)
        count = self._redis.incr(key)
        self._redis.expire(key, max(1, int(window_ms / 1000) + 2))
        return count

    def _window_count_read(
        self,
        metric: str,
        session_id: str,
        ts_ms: int,
        window_ms: int,
    ) -> int:
        key = self._window_key(metric, session_id, ts_ms, window_ms)
        raw = self._redis.get(key)
        if raw is None:
            return 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    def _window_key(self, metric: str, session_id: str, ts_ms: int, window_ms: int) -> str:
        bucket = int(ts_ms // max(1, window_ms))
        return f"tm:analyzer:win:{metric}:{session_id}:{bucket}"



def _pressure(count: int, threshold: int) -> str:
    if count >= threshold:
        return "HIGH"
    if count >= max(1, threshold // 2):
        return "MED"
    return "LOW"


__all__ = [
    "Analyzer",
    "AnalyzerOutput",
    "EvidenceUpdate",
    "EvidenceSummaryForPlanner",
]
