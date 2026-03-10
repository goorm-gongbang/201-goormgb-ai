"""Read-only query service backing the admin console."""

from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Optional

from .warehouse import AuditWarehouse


class AdminDashboardService:
    """Near-real-time metrics and drilldown views from warehouse rows."""

    def __init__(self, warehouse: AuditWarehouse) -> None:
        self._warehouse = warehouse

    def overview(self, *, window_seconds: int = 300, now_ms: Optional[int] = None) -> dict[str, Any]:
        rows = self._window_rows(window_seconds=window_seconds, now_ms=now_ms)
        orch_rows = self._canonical_rows(self._filter(rows, event_type="DEF_ORCH_EXECUTED"))
        throttle_rows = [
            row for row in self._canonical_rows(self._filter(rows, event_type="DEF_THROTTLE_APPLIED"))
            if not _is_duplicate(row)
        ]
        block_rows = [
            row for row in self._canonical_rows(self._filter(rows, event_type="DEF_BLOCK_ENFORCED"))
            if not _is_duplicate(row)
        ]
        challenge_rows = [
            row for row in self._canonical_rows(self._filter(rows, event_type="S3_CHALLENGE_RESULT"))
            if not _is_duplicate(row)
        ]

        unique_orch = {str(row.get("traceId", "")) for row in orch_rows if row.get("traceId")}
        req_count = len(unique_orch)
        rpm = round((req_count * 60.0) / max(window_seconds, 1), 2)

        throttle_delays = [
            int(delay)
            for delay in (_nested(row, "throttle", "delayMs") for row in throttle_rows)
            if isinstance(delay, int)
        ]
        block_rate = _safe_rate(len({row.get("traceId") for row in block_rows}), req_count)
        require_s3_rate = _safe_rate(
            len({row.get("traceId") for row in orch_rows if _nested(row, "serverDecision", "action") == "REQUIRE_S3"}),
            req_count,
        )
        throttle_rate = _safe_rate(len({row.get("traceId") for row in throttle_rows}), req_count)

        return {
            "windowSeconds": window_seconds,
            "requestRateRpm": rpm,
            "tierDistribution": _distribution(
                orch_rows,
                lambda row: _nested(row, "serverDecision", "riskTier"),
                dedup_unique_trace=True,
            ),
            "actionDistribution": _distribution(
                orch_rows,
                lambda row: _nested(row, "serverDecision", "action"),
                dedup_unique_trace=True,
            ),
            "s3PassFail": _distribution(
                challenge_rows,
                lambda row: _nested(row, "challenge", "result") or "UNKNOWN",
                dedup_unique_trace=True,
            ),
            "throttleAppliedRate": throttle_rate,
            "throttleDelayMs": {
                "p50": _percentile(throttle_delays, 50),
                "p90": _percentile(throttle_delays, 90),
                "avg": _avg(throttle_delays),
            },
            "blockRate": block_rate,
            "requireS3Rate": require_s3_rate,
            "errorBreakdown": _distribution(
                [row for row in rows if _nested(row, "result", "status") == "FAIL"],
                lambda row: _nested(row, "result", "reasonCode") or "UNKNOWN",
                dedup_unique_trace=True,
            ),
        }

    def integrity(self, *, window_seconds: int = 300, now_ms: Optional[int] = None) -> dict[str, Any]:
        rows = self._window_rows(window_seconds=window_seconds, now_ms=now_ms)
        guard_rows = self._canonical_rows(self._filter(rows, event_type="DEF_GUARD_SCORED"))
        duplicate_rate = _safe_rate(sum(1 for row in rows if _is_duplicate(row)), len(rows))
        missing_feature_rate = _safe_rate(
            sum(1 for row in guard_rows if _nested(row, "guard", "missingFlags")),
            len(guard_rows),
        )
        return {
            "windowSeconds": window_seconds,
            "dedupDuplicateRate": duplicate_rate,
            "missingFeatureRate": missing_feature_rate,
            "warnings": _integrity_warnings(duplicate_rate, missing_feature_rate),
        }

    def session_drilldown(
        self,
        *,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        rows = self._warehouse.query(session_id=session_id, trace_id=trace_id, limit=limit)
        rows.sort(key=lambda row: int(row.get("tsMs", 0)), reverse=True)
        state_summary = _state_summary(rows)
        links = []
        latest_langsmith = next(
            (
                _nested(row, "langsmith", "traceUrl")
                for row in rows
                if _nested(row, "langsmith", "traceUrl")
            ),
            None,
        )
        if latest_langsmith:
            links.append({"name": "LangSmith trace", "url": latest_langsmith})
        return {
            "timeline": rows,
            "stateSummary": state_summary,
            "links": links,
        }

    def throttle_view(self, *, window_seconds: int = 300, now_ms: Optional[int] = None) -> dict[str, Any]:
        rows = self._window_rows(window_seconds=window_seconds, now_ms=now_ms)
        throttle_rows = [
            row for row in self._canonical_rows(self._filter(rows, event_type="DEF_THROTTLE_APPLIED"))
            if not _is_duplicate(row)
        ]
        top = Counter(
            str(_nested(row, "throttle", "endpointPath") or "UNKNOWN") for row in throttle_rows
        )
        return {
            "windowSeconds": window_seconds,
            "throttleAppliedRate": self.overview(window_seconds=window_seconds, now_ms=now_ms)["throttleAppliedRate"],
            "topEndpoints": [{"endpointPath": key, "count": value} for key, value in top.most_common(20)],
        }

    def s3_view(self, *, window_seconds: int = 300, now_ms: Optional[int] = None) -> dict[str, Any]:
        rows = self._window_rows(window_seconds=window_seconds, now_ms=now_ms)
        challenge_rows = [
            row for row in self._canonical_rows(self._filter(rows, event_type="S3_CHALLENGE_RESULT"))
            if not _is_duplicate(row)
        ]
        trend: dict[str, Counter[str]] = defaultdict(Counter)
        for row in challenge_rows:
            bucket = _minute_bucket(int(row.get("tsMs", 0)))
            trend[bucket][str(_nested(row, "challenge", "result") or "UNKNOWN")] += 1
        halted = self._canonical_rows(self._filter(rows, event_type="S3_CHALLENGE_HALTED"))
        temp_lock_rate = _safe_rate(len(halted), len(challenge_rows) + len(halted))
        return {
            "windowSeconds": window_seconds,
            "passFailTrend": [
                {"minute": minute, "counts": dict(counter)}
                for minute, counter in sorted(trend.items(), reverse=True)
            ],
            "temporaryLockRate": temp_lock_rate,
        }

    def block_view(self, *, window_seconds: int = 300, now_ms: Optional[int] = None) -> dict[str, Any]:
        rows = self._window_rows(window_seconds=window_seconds, now_ms=now_ms)
        blocks = [
            row for row in self._canonical_rows(self._filter(rows, event_type="DEF_BLOCK_ENFORCED"))
            if not _is_duplicate(row)
        ]
        trend = Counter(_minute_bucket(int(row.get("tsMs", 0))) for row in blocks)
        return {
            "windowSeconds": window_seconds,
            "trend": [
                {"minute": minute, "count": count}
                for minute, count in sorted(trend.items(), reverse=True)
            ],
        }

    def policy_status(self) -> dict[str, Any]:
        rows = self._warehouse.query(limit=200)
        latest = rows[0] if rows else None
        return {
            "latestPolicyVersion": _nested(latest or {}, "serverDecision", "policyVersion"),
            "latestEventType": latest.get("eventType") if latest else None,
            "latestTsMs": latest.get("tsMs") if latest else None,
        }

    def _window_rows(self, *, window_seconds: int, now_ms: Optional[int]) -> list[dict[str, Any]]:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        cutoff = now - (max(window_seconds, 1) * 1000)
        rows = self._warehouse.read_all()
        return [row for row in rows if int(row.get("tsMs", 0)) >= cutoff]

    def _filter(self, rows: Iterable[dict[str, Any]], *, event_type: str) -> list[dict[str, Any]]:
        return [row for row in rows if row.get("eventType") == event_type]

    def _canonical_rows(self, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, int]] = set()
        out: list[dict[str, Any]] = []
        ordered = sorted(rows, key=lambda row: int(row.get("tsMs", 0)))
        for row in ordered:
            trace_id = str(row.get("traceId", ""))
            event_type = str(row.get("eventType", ""))
            bucket = int(int(row.get("tsMs", 0)) / 1000)
            key = (trace_id, event_type, bucket)
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out



def _distribution(
    rows: Iterable[dict[str, Any]],
    key_fn: Any,
    *,
    dedup_unique_trace: bool = False,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    seen_trace_reason: set[tuple[str, str]] = set()
    for row in rows:
        key = str(key_fn(row) or "UNKNOWN")
        if dedup_unique_trace:
            trace_id = str(row.get("traceId", ""))
            compound = (trace_id, key)
            if compound in seen_trace_reason:
                continue
            seen_trace_reason.add(compound)
        counts[key] += 1
    return dict(sorted(counts.items()))



def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)



def _avg(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)



def _percentile(values: list[int], p: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = int(math.ceil((p / 100.0) * len(ordered))) - 1
    rank = max(0, min(rank, len(ordered) - 1))
    return int(ordered[rank])



def _nested(data: Mapping[str, Any], *path: str) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return None
        cur = cur[key]
    return cur



def _is_duplicate(row: Mapping[str, Any]) -> bool:
    return bool(_nested(row, "dedup", "isDuplicate") or row.get("dedup_isDuplicate"))



def _minute_bucket(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M", time.localtime(max(ts_ms, 0) / 1000.0))



def _integrity_warnings(duplicate_rate: float, missing_feature_rate: float) -> list[str]:
    warnings: list[str] = []
    if duplicate_rate >= 0.05:
        warnings.append("dedup_duplicate_rate elevated")
    if missing_feature_rate >= 0.10:
        warnings.append("missing_feature_rate elevated")
    return warnings



def _state_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest_guard = next((row for row in rows if row.get("eventType") == "DEF_GUARD_SCORED"), None)
    latest_plan = next((row for row in rows if row.get("eventType") == "DEF_PLAN_COMPUTED"), None)
    latest_s3 = next((row for row in rows if row.get("eventType") == "S3_CHALLENGE_RESULT"), None)
    latest_throttle = next((row for row in rows if row.get("eventType") == "DEF_THROTTLE_APPLIED"), None)
    blocked = any(row.get("eventType") == "DEF_BLOCK_ENFORCED" for row in rows)
    latest = rows[0] if rows else None
    return {
        "flowState": latest.get("flowState") if latest else None,
        "riskTier": _nested(latest_guard or {}, "serverDecision", "riskTier"),
        "riskScore": _nested(latest_guard or {}, "guard", "rNew"),
        "latestAction": _nested(latest_plan or {}, "serverDecision", "action"),
        "latestS3Result": _nested(latest_s3 or {}, "challenge", "result"),
        "latestS3Attempts": _nested(latest_s3 or {}, "challenge", "attemptsInWindow"),
        "latestThrottleDelayMs": _nested(latest_throttle or {}, "throttle", "delayMs"),
        "blocked": blocked,
    }


__all__ = ["AdminDashboardService"]
