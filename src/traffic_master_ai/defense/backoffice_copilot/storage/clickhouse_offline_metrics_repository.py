from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from ...d0_mvp.observability.schemas import OPTIMIZER_INCLUDED_AUDIT_EVENT_TYPES
from .clickhouse_connection import DEFAULT_CLICKHOUSE_AUDIT_TABLE, ClickHouseSelectClient
from .clickhouse_read_models import (
    OfflineMetricsQuery,
    OfflineMetricsSnapshot,
    OfflineTraceSample,
    serialize_offline_metrics_query,
    validate_offline_metrics_snapshot,
    validate_offline_trace_sample,
)

_METRIC_EVENT_TYPES: tuple[str, ...] = tuple(sorted(OPTIMIZER_INCLUDED_AUDIT_EVENT_TYPES))
_MIN_ROLLOUT_GUARDRAIL_EVENTS_TOTAL = 30
_MIN_ROLLOUT_GUARDRAIL_UNIQUE_TRACES = 10


class ClickHouseOfflineMetricsReadRepository(Protocol):
    def read_metrics(
        self,
        query: OfflineMetricsQuery,
    ) -> OfflineMetricsSnapshot:
        ...

    def read_trace_samples(
        self,
        query: OfflineMetricsQuery,
    ) -> tuple[OfflineTraceSample, ...]:
        ...

    def read_rollout_guardrail_deltas(
        self,
        query: OfflineMetricsQuery,
        *,
        base_policy_version: str,
        candidate_policy_version: str,
    ) -> dict[str, float] | None:
        ...


@dataclass(slots=True)
class ClickHouseOfflineMetricsRepository:
    client: ClickHouseSelectClient
    table_name: str = DEFAULT_CLICKHOUSE_AUDIT_TABLE

    def read_metrics(
        self,
        query: OfflineMetricsQuery,
    ) -> OfflineMetricsSnapshot:
        params = serialize_offline_metrics_query(query)
        summary_row = _first_row(
            self.client.query(
                self.select_sql_for_summary(query),
                params,
            )
        )
        event_rows = self.client.query(
            self.select_sql_for_event_counts(query),
            params,
        )
        detail_rows = self.client.query(
            self.select_sql_for_metric_details(query),
            _with_event_types(params),
        )
        return self._snapshot_from_rows(
            query=query,
            summary_row=summary_row,
            event_rows=event_rows,
            detail_rows=detail_rows,
        )

    def read_metrics_for_policy_version(
        self,
        query: OfflineMetricsQuery,
        *,
        policy_version: str,
    ) -> OfflineMetricsSnapshot:
        params = serialize_offline_metrics_query(query)
        params["policy_version"] = policy_version
        summary_row = _first_row(
            self.client.query(
                self.select_sql_for_policy_summary(query),
                params,
            )
        )
        event_rows = self.client.query(
            self.select_sql_for_policy_event_counts(query),
            params,
        )
        detail_rows = self.client.query(
            self.select_sql_for_policy_metric_details(query),
            _with_event_types(params),
        )
        return self._snapshot_from_rows(
            query=query,
            summary_row=summary_row,
            event_rows=event_rows,
            detail_rows=detail_rows,
        )

    def read_rollout_guardrail_deltas(
        self,
        query: OfflineMetricsQuery,
        *,
        base_policy_version: str,
        candidate_policy_version: str,
    ) -> dict[str, float] | None:
        base = self.read_metrics_for_policy_version(
            query,
            policy_version=base_policy_version,
        )
        candidate = self.read_metrics_for_policy_version(
            query,
            policy_version=candidate_policy_version,
        )
        if _insufficient_rollout_metrics(base) or _insufficient_rollout_metrics(candidate):
            return None
        return {
            "s3_temp_lock_rate_pp": _rate_delta_pp(
                candidate.s3_temp_lock_rate,
                base.s3_temp_lock_rate,
            ),
            "block_rate_pp": _rate_delta_pp(candidate.block_rate, base.block_rate),
            "avg_throttle_delay_ms": round(
                candidate.avg_throttle_delay_ms - base.avg_throttle_delay_ms,
                2,
            ),
            "s3_fail_rate_pp": _rate_delta_pp(candidate.s3_fail_rate, base.s3_fail_rate),
            "dedup_duplicate_rate_pp": _rate_delta_pp(
                candidate.dedup_duplicate_rate,
                base.dedup_duplicate_rate,
            ),
            "internal_error_rate_pp": _rate_delta_pp(
                candidate.internal_error_rate,
                base.internal_error_rate,
            ),
        }

    def read_trace_samples(
        self,
        query: OfflineMetricsQuery,
    ) -> tuple[OfflineTraceSample, ...]:
        sample_limit = query.limit if query.limit is not None else 20
        params = serialize_offline_metrics_query(query)
        params["limit"] = max(sample_limit, 0)
        params["scan_limit"] = max(sample_limit * 10, 200)
        rows = self.client.query(
            self.select_sql_for_trace_samples(query),
            params,
        )
        details = tuple(_parse_metric_detail_row(row) for row in rows)
        blocked = [row for row in details if row["event_type"] == "DEF_BLOCK_ENFORCED"]
        s3_fail = [
            row
            for row in details
            if row["event_type"] == "S3_CHALLENGE_RESULT"
            and _nested_text(row["raw_payload"], "challenge", "result") == "FAIL"
        ]
        slow_throttle = sorted(
            [row for row in details if row["event_type"] == "DEF_THROTTLE_APPLIED"],
            key=lambda row: _nested_int(row["raw_payload"], "throttle", "delayMs") or 0,
            reverse=True,
        )
        samples: list[OfflineTraceSample] = []
        seen_trace_ids: set[str] = set()
        for group in (blocked, s3_fail, slow_throttle, list(details)):
            for row in group:
                trace_id = row.get("trace_id")
                if not isinstance(trace_id, str) or not trace_id or trace_id in seen_trace_ids:
                    continue
                seen_trace_ids.add(trace_id)
                samples.append(
                    validate_offline_trace_sample(
                        OfflineTraceSample(
                            ts_ms=row["ts_ms"],
                            trace_id=trace_id,
                            session_id=row.get("session_id"),
                            event_type=row.get("event_type"),
                            reason_code=row.get("reason_code")
                            or _nested_text(row["raw_payload"], "result", "reasonCode"),
                            policy_version=row.get("policy_version")
                            or _nested_text(row["raw_payload"], "server_decision", "policyVersion"),
                        )
                    )
                )
                if len(samples) >= sample_limit:
                    return tuple(samples)
        return tuple(samples)

    def select_sql_for_summary(self, query: OfflineMetricsQuery) -> str:
        del query
        return (
            f"SELECT {':window_start_ms'} AS window_start_ms, {':window_end_ms'} AS window_end_ms, "
            "count() AS events_total, "
            "uniqExact(session_id) AS unique_sessions, "
            "uniqExactIf(trace_id, isNotNull(trace_id) AND trace_id != '') AS unique_traces, "
            "uniqExactIf(trace_id, isNotNull(trace_id) AND trace_id != '' "
            "AND event_type = 'DEF_ORCH_EXECUTED') AS orch_trace_total, "
            "uniqExactIf(trace_id, isNotNull(trace_id) AND trace_id != '' "
            "AND reason_code = 'INTERNAL_ERROR') AS internal_error_trace_total, "
            "argMax(ifNull(policy_version, ''), ts_ms) AS latest_policy_version, "
            "countIf(position(raw_payload_json, '\"isDuplicate\":true') > 0) AS duplicate_count "
            f"FROM {self.table_name} "
            "WHERE ts_ms >= :window_start_ms AND ts_ms <= :window_end_ms"
        )

    def select_sql_for_event_counts(self, query: OfflineMetricsQuery) -> str:
        del query
        return (
            "SELECT event_type, count() AS event_count "
            f"FROM {self.table_name} "
            "WHERE ts_ms >= :window_start_ms AND ts_ms <= :window_end_ms "
            "GROUP BY event_type "
            "ORDER BY event_type ASC"
        )

    def select_sql_for_metric_details(self, query: OfflineMetricsQuery) -> str:
        del query
        return (
            "SELECT ts_ms, session_id, event_type, trace_id, risk_tier, action, reason_code, "
            "policy_version, raw_payload_json "
            f"FROM {self.table_name} "
            "WHERE ts_ms >= :window_start_ms AND ts_ms <= :window_end_ms "
            "AND event_type IN :event_types "
            "ORDER BY ts_ms DESC, event_type ASC"
        )

    def select_sql_for_trace_samples(self, query: OfflineMetricsQuery) -> str:
        del query
        return (
            "SELECT ts_ms, session_id, event_type, trace_id, reason_code, policy_version, raw_payload_json "
            f"FROM {self.table_name} "
            "WHERE ts_ms >= :window_start_ms AND ts_ms <= :window_end_ms "
            "AND isNotNull(trace_id) AND trace_id != '' "
            "ORDER BY ts_ms DESC, event_type ASC "
            "LIMIT :scan_limit"
        )

    def select_sql_for_policy_summary(self, query: OfflineMetricsQuery) -> str:
        return self.select_sql_for_summary(query) + " AND policy_version = :policy_version"

    def select_sql_for_policy_event_counts(self, query: OfflineMetricsQuery) -> str:
        del query
        return (
            "SELECT event_type, count() AS event_count "
            f"FROM {self.table_name} "
            "WHERE ts_ms >= :window_start_ms AND ts_ms <= :window_end_ms "
            "AND policy_version = :policy_version "
            "GROUP BY event_type "
            "ORDER BY event_type ASC"
        )

    def select_sql_for_policy_metric_details(self, query: OfflineMetricsQuery) -> str:
        del query
        return (
            "SELECT ts_ms, session_id, event_type, trace_id, risk_tier, action, reason_code, "
            "policy_version, raw_payload_json "
            f"FROM {self.table_name} "
            "WHERE ts_ms >= :window_start_ms AND ts_ms <= :window_end_ms "
            "AND policy_version = :policy_version "
            "AND event_type IN :event_types "
            "ORDER BY ts_ms DESC, event_type ASC"
        )

    def _snapshot_from_rows(
        self,
        *,
        query: OfflineMetricsQuery,
        summary_row: Mapping[str, object],
        event_rows: Sequence[Mapping[str, object]],
        detail_rows: Sequence[Mapping[str, object]],
    ) -> OfflineMetricsSnapshot:
        event_counts = _parse_event_counts(event_rows)
        details = tuple(_parse_metric_detail_row(row) for row in detail_rows)
        orch_rows = tuple(row for row in details if row["event_type"] == "DEF_ORCH_EXECUTED")
        throttle_rows = tuple(row for row in details if row["event_type"] == "DEF_THROTTLE_APPLIED")
        block_rows = tuple(row for row in details if row["event_type"] == "DEF_BLOCK_ENFORCED")
        challenge_rows = tuple(row for row in details if row["event_type"] == "S3_CHALLENGE_RESULT")
        halted_rows = tuple(row for row in details if row["event_type"] == "S3_CHALLENGE_HALTED")
        guard_rows = tuple(row for row in details if row["event_type"] == "DEF_GUARD_SCORED")

        orch_trace_total = len({row["trace_id"] for row in orch_rows if row["trace_id"]})
        throttle_trace_total = len({row["trace_id"] for row in throttle_rows if row["trace_id"]})
        block_trace_total = len({row["trace_id"] for row in block_rows if row["trace_id"]})
        require_s3_total = len(
            {
                row["trace_id"]
                for row in orch_rows
                if row["trace_id"] and row.get("action") == "REQUIRE_S3"
            }
        )

        challenge_distribution = _distribution_by_trace(
            challenge_rows,
            lambda row: _nested_text(row["raw_payload"], "challenge", "result") or "UNKNOWN",
        )
        challenge_total = sum(challenge_distribution.values())
        missing_feature_total = sum(
            1
            for row in guard_rows
            if _has_missing_features(row["raw_payload"])
        )
        throttle_delays = [
            value
            for value in (
                _nested_int(row["raw_payload"], "throttle", "delayMs") for row in throttle_rows
            )
            if value is not None
        ]
        snapshot = OfflineMetricsSnapshot(
            window_start_ms=query.window_start_ms,
            window_end_ms=query.window_end_ms,
            events_total=_coerce_int(summary_row.get("events_total"), 0),
            unique_sessions=_coerce_int(summary_row.get("unique_sessions"), 0),
            unique_traces=_coerce_int(summary_row.get("unique_traces"), 0),
            event_counts_by_type=event_counts,
            tier_distribution=_distribution_by_trace(
                orch_rows,
                lambda row: row.get("risk_tier") or "UNKNOWN",
            ),
            action_distribution=_distribution_by_trace(
                orch_rows,
                lambda row: row.get("action") or "UNKNOWN",
            ),
            block_rate=_safe_rate(block_trace_total, orch_trace_total),
            require_s3_rate=_safe_rate(require_s3_total, orch_trace_total),
            throttle_applied_rate=_safe_rate(throttle_trace_total, orch_trace_total),
            avg_throttle_delay_ms=_average(throttle_delays),
            s3_pass_rate=_safe_rate(challenge_distribution.get("PASS", 0), challenge_total),
            s3_fail_rate=_safe_rate(challenge_distribution.get("FAIL", 0), challenge_total),
            s3_temp_lock_rate=_safe_rate(len(halted_rows), len(challenge_rows) + len(halted_rows)),
            dedup_duplicate_rate=_safe_rate(
                _coerce_int(summary_row.get("duplicate_count"), 0),
                _coerce_int(summary_row.get("events_total"), 0),
            ),
            missing_feature_rate=_safe_rate(missing_feature_total, len(guard_rows)),
            internal_error_rate=_safe_rate(
                _coerce_int(summary_row.get("internal_error_trace_total"), 0),
                _coerce_int(summary_row.get("orch_trace_total"), 0) or orch_trace_total,
            ),
            latest_policy_version=_coerce_text(summary_row.get("latest_policy_version")),
        )
        return validate_offline_metrics_snapshot(snapshot)


def build_clickhouse_offline_metrics_repository(
    client: ClickHouseSelectClient,
    *,
    table_name: str = DEFAULT_CLICKHOUSE_AUDIT_TABLE,
) -> ClickHouseOfflineMetricsRepository:
    return ClickHouseOfflineMetricsRepository(
        client=client,
        table_name=table_name,
    )


def _parse_event_counts(rows: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        event_type = _coerce_text(row.get("event_type")) or "UNKNOWN"
        counts[event_type] = _coerce_int(row.get("event_count"), 0)
    return dict(sorted(counts.items()))


def _parse_metric_detail_row(row: Mapping[str, object]) -> dict[str, Any]:
    return {
        "ts_ms": _coerce_int(row.get("ts_ms"), 0),
        "session_id": _coerce_text(row.get("session_id")),
        "event_type": _coerce_text(row.get("event_type")) or "UNKNOWN",
        "trace_id": _coerce_text(row.get("trace_id")),
        "risk_tier": _coerce_text(row.get("risk_tier")),
        "action": _coerce_text(row.get("action")),
        "reason_code": _coerce_text(row.get("reason_code")),
        "policy_version": _coerce_text(row.get("policy_version")),
        "raw_payload": _parse_json_object(row.get("raw_payload_json")),
    }


def _distribution_by_trace(
    rows: Sequence[Mapping[str, Any]],
    selector: Any,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = str(selector(row) or "UNKNOWN")
        trace_id = str(row.get("trace_id") or "")
        compound = (trace_id, key)
        if trace_id and compound in seen:
            continue
        if trace_id:
            seen.add(compound)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _has_missing_features(payload: Mapping[str, Any]) -> bool:
    raw = _nested(payload, "guard", "missingFlags")
    return isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and len(raw) > 0


def _nested(payload: Mapping[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _nested_text(payload: Mapping[str, Any], *path: str) -> str | None:
    value = _nested(payload, *path)
    return _coerce_text(value)


def _nested_int(payload: Mapping[str, Any], *path: str) -> int | None:
    value = _nested(payload, *path)
    if value is None:
        return None
    return _coerce_int(value, 0)


def _parse_json_object(value: object) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, Mapping):
        return {}
    return {str(key): parsed[key] for key in parsed.keys()}


def _first_row(rows: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    if not rows:
        return {
            "window_start_ms": 0,
            "window_end_ms": 0,
            "events_total": 0,
            "unique_sessions": 0,
            "unique_traces": 0,
            "latest_policy_version": None,
            "duplicate_count": 0,
        }
    return rows[0]


def _coerce_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("-"):
            numeric = stripped[1:]
        else:
            numeric = stripped
        if numeric.isdigit():
            return int(stripped)
        return default
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    return value


def _average(values: Sequence[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _rate_delta_pp(candidate_rate: float, base_rate: float) -> float:
    return round((candidate_rate - base_rate) * 100.0, 4)


def _insufficient_rollout_metrics(snapshot: OfflineMetricsSnapshot) -> bool:
    return (
        snapshot.events_total < _MIN_ROLLOUT_GUARDRAIL_EVENTS_TOTAL
        or snapshot.unique_traces < _MIN_ROLLOUT_GUARDRAIL_UNIQUE_TRACES
    )


def _with_event_types(params: Mapping[str, object]) -> dict[str, object]:
    merged = dict(params)
    merged["event_types"] = _METRIC_EVENT_TYPES
    return merged

__all__ = [
    "ClickHouseOfflineMetricsReadRepository",
    "ClickHouseOfflineMetricsRepository",
    "build_clickhouse_offline_metrics_repository",
]
