"""PostgreSQL repositories for policy control-plane authoritative storage."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING, Any, Mapping, Protocol, Sequence

from .policy_control_plane_models import (
    PolicyOptimizationRunRecord,
    PolicyRolloutEventRecord,
    PolicyRolloutStateRecord,
    PolicyVersionRecord,
    parse_policy_optimization_run_record,
    parse_policy_rollout_event_records,
    parse_policy_rollout_state_record,
    parse_policy_version_record,
    serialize_policy_optimization_run_record,
    serialize_policy_rollout_event_record,
    serialize_policy_rollout_state_record,
    serialize_policy_version_record,
)
from .repository import PkConflictPolicy

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection, Engine
else:
    Connection = Any
    Engine = Any

logger = logging.getLogger(__name__)

_POLICY_VERSION_COLUMNS = (
    "policy_version",
    "schema_version",
    "status",
    "source_type",
    "parent_policy_version",
    "document_json",
    "validation_result_json",
    "created_at",
    "validated_at",
    "activated_at",
)

_POLICY_ROLLOUT_STATE_COLUMNS = (
    "rollout_id",
    "stage",
    "base_policy_version",
    "candidate_policy_version",
    "ratio",
    "evaluation_window_seconds",
    "canary_duration_seconds",
    "expand_step_index",
    "stage_started_at_ms",
    "updated_at_ms",
    "current_status",
    "rollback_reason",
)

_POLICY_ROLLOUT_EVENT_COLUMNS = (
    "event_id",
    "rollout_id",
    "event_type",
    "base_policy_version",
    "candidate_policy_version",
    "stage_before",
    "stage_after",
    "ratio_before",
    "ratio_after",
    "reason_json",
    "metrics_snapshot_json",
    "created_at",
)

_POLICY_OPTIMIZATION_RUN_COLUMNS = (
    "run_id",
    "base_policy_version",
    "proposed_policy_version",
    "trigger_type",
    "metrics_snapshot_id",
    "window_start_ms",
    "window_end_ms",
    "metrics_snapshot_json",
    "proposal_json",
    "validation_result_json",
    "result_status",
    "created_at",
    "finished_at",
)

_INSERT_POLICY_VERSION_SQL = """
INSERT INTO policy_versions (
    policy_version,
    schema_version,
    status,
    source_type,
    parent_policy_version,
    document_json,
    validation_result_json,
    created_at,
    validated_at,
    activated_at
) VALUES (
    :policy_version,
    :schema_version,
    :status,
    :source_type,
    :parent_policy_version,
    :document_json,
    :validation_result_json,
    :created_at,
    :validated_at,
    :activated_at
)
"""

_UPSERT_POLICY_VERSION_SQL = """
INSERT INTO policy_versions (
    policy_version,
    schema_version,
    status,
    source_type,
    parent_policy_version,
    document_json,
    validation_result_json,
    created_at,
    validated_at,
    activated_at
) VALUES (
    :policy_version,
    :schema_version,
    :status,
    :source_type,
    :parent_policy_version,
    :document_json,
    :validation_result_json,
    :created_at,
    :validated_at,
    :activated_at
)
ON CONFLICT (policy_version) DO UPDATE SET
    schema_version = EXCLUDED.schema_version,
    status = EXCLUDED.status,
    source_type = EXCLUDED.source_type,
    parent_policy_version = EXCLUDED.parent_policy_version,
    document_json = EXCLUDED.document_json,
    validation_result_json = EXCLUDED.validation_result_json,
    validated_at = EXCLUDED.validated_at,
    activated_at = EXCLUDED.activated_at
"""

_SELECT_POLICY_VERSION_SQL = f"""
SELECT {", ".join(_POLICY_VERSION_COLUMNS)}
FROM policy_versions
WHERE policy_version = :policy_version
"""

_INSERT_POLICY_ROLLOUT_STATE_SQL = """
INSERT INTO policy_rollout_state (
    rollout_id,
    stage,
    base_policy_version,
    candidate_policy_version,
    ratio,
    evaluation_window_seconds,
    canary_duration_seconds,
    expand_step_index,
    stage_started_at_ms,
    updated_at_ms,
    current_status,
    rollback_reason
) VALUES (
    :rollout_id,
    :stage,
    :base_policy_version,
    :candidate_policy_version,
    :ratio,
    :evaluation_window_seconds,
    :canary_duration_seconds,
    :expand_step_index,
    :stage_started_at_ms,
    :updated_at_ms,
    :current_status,
    :rollback_reason
)
"""

_UPSERT_POLICY_ROLLOUT_STATE_SQL = """
INSERT INTO policy_rollout_state (
    rollout_id,
    stage,
    base_policy_version,
    candidate_policy_version,
    ratio,
    evaluation_window_seconds,
    canary_duration_seconds,
    expand_step_index,
    stage_started_at_ms,
    updated_at_ms,
    current_status,
    rollback_reason
) VALUES (
    :rollout_id,
    :stage,
    :base_policy_version,
    :candidate_policy_version,
    :ratio,
    :evaluation_window_seconds,
    :canary_duration_seconds,
    :expand_step_index,
    :stage_started_at_ms,
    :updated_at_ms,
    :current_status,
    :rollback_reason
)
ON CONFLICT (rollout_id) DO UPDATE SET
    stage = EXCLUDED.stage,
    base_policy_version = EXCLUDED.base_policy_version,
    candidate_policy_version = EXCLUDED.candidate_policy_version,
    ratio = EXCLUDED.ratio,
    evaluation_window_seconds = EXCLUDED.evaluation_window_seconds,
    canary_duration_seconds = EXCLUDED.canary_duration_seconds,
    expand_step_index = EXCLUDED.expand_step_index,
    stage_started_at_ms = EXCLUDED.stage_started_at_ms,
    updated_at_ms = EXCLUDED.updated_at_ms,
    current_status = EXCLUDED.current_status,
    rollback_reason = EXCLUDED.rollback_reason
"""

_SELECT_POLICY_ROLLOUT_STATE_SQL = f"""
SELECT {", ".join(_POLICY_ROLLOUT_STATE_COLUMNS)}
FROM policy_rollout_state
WHERE rollout_id = :rollout_id
"""

_INSERT_POLICY_ROLLOUT_EVENT_SQL = """
INSERT INTO policy_rollout_events (
    event_id,
    rollout_id,
    event_type,
    base_policy_version,
    candidate_policy_version,
    stage_before,
    stage_after,
    ratio_before,
    ratio_after,
    reason_json,
    metrics_snapshot_json,
    created_at
) VALUES (
    :event_id,
    :rollout_id,
    :event_type,
    :base_policy_version,
    :candidate_policy_version,
    :stage_before,
    :stage_after,
    :ratio_before,
    :ratio_after,
    :reason_json,
    :metrics_snapshot_json,
    :created_at
)
"""

_SELECT_POLICY_ROLLOUT_EVENTS_SQL = f"""
SELECT {", ".join(_POLICY_ROLLOUT_EVENT_COLUMNS)}
FROM policy_rollout_events
WHERE rollout_id = :rollout_id
ORDER BY created_at ASC, event_id ASC
"""

_INSERT_POLICY_OPTIMIZATION_RUN_SQL = """
INSERT INTO policy_optimization_runs (
    run_id,
    base_policy_version,
    proposed_policy_version,
    trigger_type,
    metrics_snapshot_id,
    window_start_ms,
    window_end_ms,
    metrics_snapshot_json,
    proposal_json,
    validation_result_json,
    result_status,
    created_at,
    finished_at
) VALUES (
    :run_id,
    :base_policy_version,
    :proposed_policy_version,
    :trigger_type,
    :metrics_snapshot_id,
    :window_start_ms,
    :window_end_ms,
    :metrics_snapshot_json,
    :proposal_json,
    :validation_result_json,
    :result_status,
    :created_at,
    :finished_at
)
"""

_UPSERT_POLICY_OPTIMIZATION_RUN_SQL = """
INSERT INTO policy_optimization_runs (
    run_id,
    base_policy_version,
    proposed_policy_version,
    trigger_type,
    metrics_snapshot_id,
    window_start_ms,
    window_end_ms,
    metrics_snapshot_json,
    proposal_json,
    validation_result_json,
    result_status,
    created_at,
    finished_at
) VALUES (
    :run_id,
    :base_policy_version,
    :proposed_policy_version,
    :trigger_type,
    :metrics_snapshot_id,
    :window_start_ms,
    :window_end_ms,
    :metrics_snapshot_json,
    :proposal_json,
    :validation_result_json,
    :result_status,
    :created_at,
    :finished_at
)
ON CONFLICT (run_id) DO UPDATE SET
    base_policy_version = EXCLUDED.base_policy_version,
    proposed_policy_version = EXCLUDED.proposed_policy_version,
    trigger_type = EXCLUDED.trigger_type,
    metrics_snapshot_id = EXCLUDED.metrics_snapshot_id,
    window_start_ms = EXCLUDED.window_start_ms,
    window_end_ms = EXCLUDED.window_end_ms,
    metrics_snapshot_json = EXCLUDED.metrics_snapshot_json,
    proposal_json = EXCLUDED.proposal_json,
    validation_result_json = EXCLUDED.validation_result_json,
    result_status = EXCLUDED.result_status,
    finished_at = EXCLUDED.finished_at
"""

_SELECT_POLICY_OPTIMIZATION_RUN_SQL = f"""
SELECT {", ".join(_POLICY_OPTIMIZATION_RUN_COLUMNS)}
FROM policy_optimization_runs
WHERE run_id = :run_id
"""


class PostgresControlPlaneWriteError(RuntimeError):
    """Raised when an authoritative PostgreSQL control-plane write fails."""

    def __init__(
        self,
        *,
        operation: str,
        table_name: str,
        record_key: str,
    ) -> None:
        self.operation = operation
        self.table_name = table_name
        self.record_key = record_key
        self.recovery_hint = (
            "Do not continue Redis projection or rollout application until the "
            "authoritative PostgreSQL write succeeds. Retry the same repository call."
        )
        super().__init__(
            "PostgreSQL control-plane write failed "
            f"(operation={operation}, table={table_name}, record_key={record_key}). "
            f"{self.recovery_hint}"
        )


class PolicyVersionRepository(Protocol):
    """Authoritative repository for persisted policy documents only."""

    def save_version(self, record: PolicyVersionRecord) -> None:
        """Insert or upsert one policy version row."""

    def get_version(self, policy_version: str) -> PolicyVersionRecord | None:
        """Read one policy version row."""


class PolicyRolloutStateRepository(Protocol):
    """Authoritative repository for current rollout state only."""

    def save_state(self, record: PolicyRolloutStateRecord) -> None:
        """Insert or upsert one rollout-state row."""

    def get_state(self, rollout_id: str) -> PolicyRolloutStateRecord | None:
        """Read one rollout-state row."""


class PolicyRolloutEventRepository(Protocol):
    """Append-only repository for rollout event history."""

    def append_event(self, record: PolicyRolloutEventRecord) -> None:
        """Append one immutable rollout event row."""

    def list_events(self, rollout_id: str) -> tuple[PolicyRolloutEventRecord, ...]:
        """Read rollout events for operator-side audit or projection input."""


class PolicyOptimizationRunRepository(Protocol):
    """Repository for optimization-run metadata only."""

    def save_run(self, record: PolicyOptimizationRunRecord) -> None:
        """Insert or upsert one optimization-run row."""

    def get_run(self, run_id: str) -> PolicyOptimizationRunRecord | None:
        """Read one optimization-run row."""


@dataclass(slots=True)
class PostgresPolicyVersionRepository:
    """PostgreSQL repository for `policy_versions`.

    Explicit non-goals kept here:
    - no runtime direct read path
    - no Redis projection repair
    - no policy semantic rewrite or validation decision logic
    """

    engine: Engine
    conflict_policy: PkConflictPolicy = PkConflictPolicy.UPSERT

    def save_version(self, record: PolicyVersionRecord) -> None:
        params = serialize_policy_version_record(record)
        try:
            with self.engine.begin() as connection:
                self._execute(connection, self._save_sql, params)
        except Exception as exc:
            logger.exception(
                "Authoritative PostgreSQL write failed for policy_versions policy_version=%s",
                record.policy_version,
            )
            raise PostgresControlPlaneWriteError(
                operation="save_version",
                table_name="policy_versions",
                record_key=record.policy_version,
            ) from exc

    def get_version(self, policy_version: str) -> PolicyVersionRecord | None:
        with self.engine.begin() as connection:
            row = self._fetch_one(
                connection,
                _SELECT_POLICY_VERSION_SQL,
                {"policy_version": policy_version},
            )
        if row is None:
            return None
        return parse_policy_version_record(row)

    @property
    def _save_sql(self) -> str:
        if self.conflict_policy is PkConflictPolicy.FAIL_FAST:
            return _INSERT_POLICY_VERSION_SQL
        return _UPSERT_POLICY_VERSION_SQL

    def _execute(self, connection: Connection, sql_text: str, params: dict[str, object]) -> None:
        _execute(connection, sql_text, params)

    def _fetch_one(
        self,
        connection: Connection,
        sql_text: str,
        params: dict[str, object],
    ) -> dict[str, object] | None:
        return _fetch_one(connection, sql_text, params)


@dataclass(slots=True)
class PostgresPolicyRolloutStateRepository:
    """PostgreSQL repository for `policy_rollout_state`."""

    engine: Engine
    conflict_policy: PkConflictPolicy = PkConflictPolicy.UPSERT

    def save_state(self, record: PolicyRolloutStateRecord) -> None:
        params = serialize_policy_rollout_state_record(record)
        try:
            with self.engine.begin() as connection:
                self._execute(connection, self._save_sql, params)
        except Exception as exc:
            logger.exception(
                "Authoritative PostgreSQL write failed for policy_rollout_state rollout_id=%s",
                record.rollout_id,
            )
            raise PostgresControlPlaneWriteError(
                operation="save_state",
                table_name="policy_rollout_state",
                record_key=record.rollout_id,
            ) from exc

    def get_state(self, rollout_id: str) -> PolicyRolloutStateRecord | None:
        with self.engine.begin() as connection:
            row = self._fetch_one(
                connection,
                _SELECT_POLICY_ROLLOUT_STATE_SQL,
                {"rollout_id": rollout_id},
            )
        if row is None:
            return None
        return parse_policy_rollout_state_record(row)

    @property
    def _save_sql(self) -> str:
        if self.conflict_policy is PkConflictPolicy.FAIL_FAST:
            return _INSERT_POLICY_ROLLOUT_STATE_SQL
        return _UPSERT_POLICY_ROLLOUT_STATE_SQL

    def _execute(self, connection: Connection, sql_text: str, params: dict[str, object]) -> None:
        _execute(connection, sql_text, params)

    def _fetch_one(
        self,
        connection: Connection,
        sql_text: str,
        params: dict[str, object],
    ) -> dict[str, object] | None:
        return _fetch_one(connection, sql_text, params)


@dataclass(slots=True)
class PostgresPolicyRolloutEventRepository:
    """PostgreSQL append-only repository for `policy_rollout_events`."""

    engine: Engine

    def append_event(self, record: PolicyRolloutEventRecord) -> None:
        params = serialize_policy_rollout_event_record(record)
        try:
            with self.engine.begin() as connection:
                self._execute(connection, _INSERT_POLICY_ROLLOUT_EVENT_SQL, params)
        except Exception as exc:
            logger.exception(
                "Authoritative PostgreSQL append failed for policy_rollout_events event_id=%s",
                record.event_id,
            )
            raise PostgresControlPlaneWriteError(
                operation="append_event",
                table_name="policy_rollout_events",
                record_key=record.event_id,
            ) from exc

    def list_events(self, rollout_id: str) -> tuple[PolicyRolloutEventRecord, ...]:
        with self.engine.begin() as connection:
            rows = self._fetch_all(
                connection,
                _SELECT_POLICY_ROLLOUT_EVENTS_SQL,
                {"rollout_id": rollout_id},
            )
        return parse_policy_rollout_event_records(rows)

    def _execute(self, connection: Connection, sql_text: str, params: dict[str, object]) -> None:
        _execute(connection, sql_text, params)

    def _fetch_all(
        self,
        connection: Connection,
        sql_text: str,
        params: dict[str, object],
    ) -> list[dict[str, object]]:
        return _fetch_all(connection, sql_text, params)


@dataclass(slots=True)
class PostgresPolicyOptimizationRunRepository:
    """PostgreSQL repository for `policy_optimization_runs`."""

    engine: Engine
    conflict_policy: PkConflictPolicy = PkConflictPolicy.UPSERT

    def save_run(self, record: PolicyOptimizationRunRecord) -> None:
        params = serialize_policy_optimization_run_record(record)
        try:
            with self.engine.begin() as connection:
                self._execute(connection, self._save_sql, params)
        except Exception as exc:
            logger.exception(
                "Authoritative PostgreSQL write failed for policy_optimization_runs run_id=%s",
                record.run_id,
            )
            raise PostgresControlPlaneWriteError(
                operation="save_run",
                table_name="policy_optimization_runs",
                record_key=record.run_id,
            ) from exc

    def get_run(self, run_id: str) -> PolicyOptimizationRunRecord | None:
        with self.engine.begin() as connection:
            row = self._fetch_one(
                connection,
                _SELECT_POLICY_OPTIMIZATION_RUN_SQL,
                {"run_id": run_id},
            )
        if row is None:
            return None
        return parse_policy_optimization_run_record(row)

    @property
    def _save_sql(self) -> str:
        if self.conflict_policy is PkConflictPolicy.FAIL_FAST:
            return _INSERT_POLICY_OPTIMIZATION_RUN_SQL
        return _UPSERT_POLICY_OPTIMIZATION_RUN_SQL

    def _execute(self, connection: Connection, sql_text: str, params: dict[str, object]) -> None:
        _execute(connection, sql_text, params)

    def _fetch_one(
        self,
        connection: Connection,
        sql_text: str,
        params: dict[str, object],
    ) -> dict[str, object] | None:
        return _fetch_one(connection, sql_text, params)


def _execute(connection: Connection, sql_text: str, params: dict[str, object]) -> None:
    try:
        from sqlalchemy import text
    except ImportError as exc:
        raise RuntimeError(
            "sqlalchemy is required to execute Backoffice Copilot PostgreSQL control-plane queries."
        ) from exc

    connection.execute(text(sql_text), _coerce_postgres_params(params))


def _fetch_one(
    connection: Connection,
    sql_text: str,
    params: dict[str, object],
) -> dict[str, object] | None:
    row = _execute_fetch(connection, sql_text, params).mappings().one_or_none()
    if row is None:
        return None
    return dict(row)


def _fetch_all(
    connection: Connection,
    sql_text: str,
    params: dict[str, object],
) -> list[dict[str, object]]:
    return [dict(row) for row in _execute_fetch(connection, sql_text, params).mappings().all()]


def _execute_fetch(connection: Connection, sql_text: str, params: dict[str, object]) -> Any:
    try:
        from sqlalchemy import text
    except ImportError as exc:
        raise RuntimeError(
            "sqlalchemy is required to execute Backoffice Copilot PostgreSQL control-plane queries."
        ) from exc

    return connection.execute(text(sql_text), _coerce_postgres_params(params))


def _coerce_postgres_params(params: dict[str, object]) -> dict[str, object]:
    return {key: _coerce_postgres_param_value(value) for key, value in params.items()}


def _coerce_postgres_param_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _wrap_jsonb(dict(value))
    if isinstance(value, (list, tuple)):
        return _wrap_jsonb(list(value))
    return value


def _wrap_jsonb(value: object) -> object:
    try:
        from psycopg.types.json import Jsonb
    except Exception:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return Jsonb(value)
