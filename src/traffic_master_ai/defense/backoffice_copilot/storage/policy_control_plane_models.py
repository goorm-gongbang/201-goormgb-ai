"""Persistence DTOs and serializers for PostgreSQL policy control-plane storage."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from .validators import StorageValidationError


@dataclass(slots=True, frozen=True)
class PolicyVersionRecord:
    """Minimal authoritative row contract for `policy_versions`."""

    policy_version: str
    schema_version: str
    status: str
    source_type: str
    document_json: Mapping[str, object]
    created_at: datetime
    parent_policy_version: str | None = None
    validation_result_json: Mapping[str, object] | None = None
    validated_at: datetime | None = None
    activated_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class PolicyRolloutStateRecord:
    """Minimal authoritative row contract for `policy_rollout_state`."""

    rollout_id: str
    stage: str
    base_policy_version: str
    ratio: Decimal
    evaluation_window_seconds: int
    canary_duration_seconds: int
    stage_started_at_ms: int
    updated_at_ms: int
    current_status: str
    candidate_policy_version: str | None = None
    expand_step_index: int | None = None
    rollback_reason: str | None = None


@dataclass(slots=True, frozen=True)
class PolicyRolloutEventRecord:
    """Minimal append-only row contract for `policy_rollout_events`."""

    event_id: str
    rollout_id: str
    event_type: str
    base_policy_version: str
    created_at: datetime
    candidate_policy_version: str | None = None
    stage_before: str | None = None
    stage_after: str | None = None
    ratio_before: Decimal | None = None
    ratio_after: Decimal | None = None
    reason_json: Mapping[str, object] | None = None
    metrics_snapshot_json: Mapping[str, object] | None = None


@dataclass(slots=True, frozen=True)
class PolicyOptimizationRunRecord:
    """Minimal read/write contract for `policy_optimization_runs`."""

    run_id: str
    base_policy_version: str
    trigger_type: str
    result_status: str
    created_at: datetime
    proposed_policy_version: str | None = None
    metrics_snapshot_id: str | None = None
    window_start_ms: int | None = None
    window_end_ms: int | None = None
    metrics_snapshot_json: Mapping[str, object] | None = None
    proposal_json: Mapping[str, object] | None = None
    validation_result_json: Mapping[str, object] | None = None
    finished_at: datetime | None = None


def validate_policy_version_record(record: PolicyVersionRecord) -> PolicyVersionRecord:
    """Validate one `policy_versions` record."""

    _ensure_required_text(record.policy_version, "policy_version")
    _ensure_required_text(record.schema_version, "schema_version")
    _ensure_required_text(record.status, "status")
    _ensure_required_text(record.source_type, "source_type")
    _ensure_nullable_text(record.parent_policy_version, "parent_policy_version")
    _ensure_mapping(record.document_json, "document_json")
    _ensure_mapping_or_none(record.validation_result_json, "validation_result_json")
    _ensure_datetime(record.created_at, "created_at")
    _ensure_datetime_or_none(record.validated_at, "validated_at")
    _ensure_datetime_or_none(record.activated_at, "activated_at")
    return record


def validate_policy_rollout_state_record(
    record: PolicyRolloutStateRecord,
) -> PolicyRolloutStateRecord:
    """Validate one `policy_rollout_state` row."""

    _ensure_required_text(record.rollout_id, "rollout_id")
    _ensure_required_text(record.stage, "stage")
    _ensure_required_text(record.base_policy_version, "base_policy_version")
    _ensure_nullable_text(record.candidate_policy_version, "candidate_policy_version")
    ratio = _ensure_ratio(record.ratio, "ratio")
    if ratio == Decimal("1.00000") and record.candidate_policy_version is not None:
        raise StorageValidationError(
            "candidate_policy_version must be None after full promotion state is stored."
        )
    _ensure_non_negative_int(record.evaluation_window_seconds, "evaluation_window_seconds")
    _ensure_non_negative_int(record.canary_duration_seconds, "canary_duration_seconds")
    _ensure_nullable_int(record.expand_step_index, "expand_step_index")
    _ensure_non_negative_int(record.stage_started_at_ms, "stage_started_at_ms")
    _ensure_non_negative_int(record.updated_at_ms, "updated_at_ms")
    if record.stage_started_at_ms > record.updated_at_ms:
        raise StorageValidationError("stage_started_at_ms must be less than or equal to updated_at_ms.")
    _ensure_required_text(record.current_status, "current_status")
    _ensure_nullable_text(record.rollback_reason, "rollback_reason")
    return record


def validate_policy_rollout_event_record(
    record: PolicyRolloutEventRecord,
) -> PolicyRolloutEventRecord:
    """Validate one append-only rollout event row."""

    _ensure_required_text(record.event_id, "event_id")
    _ensure_required_text(record.rollout_id, "rollout_id")
    _ensure_required_text(record.event_type, "event_type")
    _ensure_required_text(record.base_policy_version, "base_policy_version")
    _ensure_nullable_text(record.candidate_policy_version, "candidate_policy_version")
    _ensure_nullable_text(record.stage_before, "stage_before")
    _ensure_nullable_text(record.stage_after, "stage_after")
    _ensure_ratio_or_none(record.ratio_before, "ratio_before")
    _ensure_ratio_or_none(record.ratio_after, "ratio_after")
    _ensure_mapping_or_none(record.reason_json, "reason_json")
    _ensure_mapping_or_none(record.metrics_snapshot_json, "metrics_snapshot_json")
    _ensure_datetime(record.created_at, "created_at")
    return record


def validate_policy_optimization_run_record(
    record: PolicyOptimizationRunRecord,
) -> PolicyOptimizationRunRecord:
    """Validate one optimization-run row."""

    _ensure_required_text(record.run_id, "run_id")
    _ensure_required_text(record.base_policy_version, "base_policy_version")
    _ensure_nullable_text(record.proposed_policy_version, "proposed_policy_version")
    _ensure_required_text(record.trigger_type, "trigger_type")
    _ensure_nullable_text(record.metrics_snapshot_id, "metrics_snapshot_id")
    _ensure_nullable_int(record.window_start_ms, "window_start_ms")
    _ensure_nullable_int(record.window_end_ms, "window_end_ms")
    if record.window_start_ms is not None and record.window_end_ms is not None:
        if record.window_start_ms > record.window_end_ms:
            raise StorageValidationError(
                "window_start_ms must be less than or equal to window_end_ms."
            )
    _ensure_mapping_or_none(record.metrics_snapshot_json, "metrics_snapshot_json")
    _ensure_mapping_or_none(record.proposal_json, "proposal_json")
    _ensure_mapping_or_none(record.validation_result_json, "validation_result_json")
    _ensure_required_text(record.result_status, "result_status")
    _ensure_datetime(record.created_at, "created_at")
    _ensure_datetime_or_none(record.finished_at, "finished_at")
    if record.finished_at is not None and record.finished_at < record.created_at:
        raise StorageValidationError("finished_at must be greater than or equal to created_at.")
    return record


def serialize_policy_version_record(record: PolicyVersionRecord) -> dict[str, object]:
    """Validate and serialize one `policy_versions` record."""

    validate_policy_version_record(record)
    return {
        "policy_version": record.policy_version,
        "schema_version": record.schema_version,
        "status": record.status,
        "source_type": record.source_type,
        "parent_policy_version": record.parent_policy_version,
        "document_json": _copy_mapping(record.document_json),
        "validation_result_json": _copy_mapping_or_none(record.validation_result_json),
        "created_at": record.created_at,
        "validated_at": record.validated_at,
        "activated_at": record.activated_at,
    }


def serialize_policy_rollout_state_record(
    record: PolicyRolloutStateRecord,
) -> dict[str, object]:
    """Validate and serialize one `policy_rollout_state` row."""

    validate_policy_rollout_state_record(record)
    return {
        "rollout_id": record.rollout_id,
        "stage": record.stage,
        "base_policy_version": record.base_policy_version,
        "candidate_policy_version": record.candidate_policy_version,
        "ratio": _ensure_ratio(record.ratio, "ratio"),
        "evaluation_window_seconds": record.evaluation_window_seconds,
        "canary_duration_seconds": record.canary_duration_seconds,
        "expand_step_index": record.expand_step_index,
        "stage_started_at_ms": record.stage_started_at_ms,
        "updated_at_ms": record.updated_at_ms,
        "current_status": record.current_status,
        "rollback_reason": record.rollback_reason,
    }


def serialize_policy_rollout_event_record(
    record: PolicyRolloutEventRecord,
) -> dict[str, object]:
    """Validate and serialize one `policy_rollout_events` row."""

    validate_policy_rollout_event_record(record)
    return {
        "event_id": record.event_id,
        "rollout_id": record.rollout_id,
        "event_type": record.event_type,
        "base_policy_version": record.base_policy_version,
        "candidate_policy_version": record.candidate_policy_version,
        "stage_before": record.stage_before,
        "stage_after": record.stage_after,
        "ratio_before": _ensure_ratio_or_none(record.ratio_before, "ratio_before"),
        "ratio_after": _ensure_ratio_or_none(record.ratio_after, "ratio_after"),
        "reason_json": _copy_mapping_or_none(record.reason_json),
        "metrics_snapshot_json": _copy_mapping_or_none(record.metrics_snapshot_json),
        "created_at": record.created_at,
    }


def serialize_policy_optimization_run_record(
    record: PolicyOptimizationRunRecord,
) -> dict[str, object]:
    """Validate and serialize one `policy_optimization_runs` row."""

    validate_policy_optimization_run_record(record)
    return {
        "run_id": record.run_id,
        "base_policy_version": record.base_policy_version,
        "proposed_policy_version": record.proposed_policy_version,
        "trigger_type": record.trigger_type,
        "metrics_snapshot_id": record.metrics_snapshot_id,
        "window_start_ms": record.window_start_ms,
        "window_end_ms": record.window_end_ms,
        "metrics_snapshot_json": _copy_mapping_or_none(record.metrics_snapshot_json),
        "proposal_json": _copy_mapping_or_none(record.proposal_json),
        "validation_result_json": _copy_mapping_or_none(record.validation_result_json),
        "result_status": record.result_status,
        "created_at": record.created_at,
        "finished_at": record.finished_at,
    }


def parse_policy_version_record(row: Mapping[str, object]) -> PolicyVersionRecord:
    """Parse one database row into `PolicyVersionRecord`."""

    return validate_policy_version_record(
        PolicyVersionRecord(
            policy_version=_ensure_required_text(row.get("policy_version"), "policy_version"),
            schema_version=_ensure_required_text(row.get("schema_version"), "schema_version"),
            status=_ensure_required_text(row.get("status"), "status"),
            source_type=_ensure_required_text(row.get("source_type"), "source_type"),
            parent_policy_version=_ensure_nullable_text(
                row.get("parent_policy_version"),
                "parent_policy_version",
            ),
            document_json=_ensure_mapping(row.get("document_json"), "document_json"),
            validation_result_json=_ensure_mapping_or_none(
                row.get("validation_result_json"),
                "validation_result_json",
            ),
            created_at=_ensure_datetime(row.get("created_at"), "created_at"),
            validated_at=_ensure_datetime_or_none(row.get("validated_at"), "validated_at"),
            activated_at=_ensure_datetime_or_none(row.get("activated_at"), "activated_at"),
        )
    )


def parse_policy_rollout_state_record(row: Mapping[str, object]) -> PolicyRolloutStateRecord:
    """Parse one database row into `PolicyRolloutStateRecord`."""

    return validate_policy_rollout_state_record(
        PolicyRolloutStateRecord(
            rollout_id=_ensure_required_text(row.get("rollout_id"), "rollout_id"),
            stage=_ensure_required_text(row.get("stage"), "stage"),
            base_policy_version=_ensure_required_text(
                row.get("base_policy_version"),
                "base_policy_version",
            ),
            candidate_policy_version=_ensure_nullable_text(
                row.get("candidate_policy_version"),
                "candidate_policy_version",
            ),
            ratio=_ensure_ratio(row.get("ratio"), "ratio"),
            evaluation_window_seconds=_ensure_non_negative_int(
                row.get("evaluation_window_seconds"),
                "evaluation_window_seconds",
            ),
            canary_duration_seconds=_ensure_non_negative_int(
                row.get("canary_duration_seconds"),
                "canary_duration_seconds",
            ),
            expand_step_index=_ensure_nullable_int(
                row.get("expand_step_index"),
                "expand_step_index",
            ),
            stage_started_at_ms=_ensure_non_negative_int(
                row.get("stage_started_at_ms"),
                "stage_started_at_ms",
            ),
            updated_at_ms=_ensure_non_negative_int(row.get("updated_at_ms"), "updated_at_ms"),
            current_status=_ensure_required_text(row.get("current_status"), "current_status"),
            rollback_reason=_ensure_nullable_text(row.get("rollback_reason"), "rollback_reason"),
        )
    )


def parse_policy_rollout_event_record(row: Mapping[str, object]) -> PolicyRolloutEventRecord:
    """Parse one database row into `PolicyRolloutEventRecord`."""

    return validate_policy_rollout_event_record(
        PolicyRolloutEventRecord(
            event_id=_ensure_required_text(row.get("event_id"), "event_id"),
            rollout_id=_ensure_required_text(row.get("rollout_id"), "rollout_id"),
            event_type=_ensure_required_text(row.get("event_type"), "event_type"),
            base_policy_version=_ensure_required_text(
                row.get("base_policy_version"),
                "base_policy_version",
            ),
            candidate_policy_version=_ensure_nullable_text(
                row.get("candidate_policy_version"),
                "candidate_policy_version",
            ),
            stage_before=_ensure_nullable_text(row.get("stage_before"), "stage_before"),
            stage_after=_ensure_nullable_text(row.get("stage_after"), "stage_after"),
            ratio_before=_ensure_ratio_or_none(row.get("ratio_before"), "ratio_before"),
            ratio_after=_ensure_ratio_or_none(row.get("ratio_after"), "ratio_after"),
            reason_json=_ensure_mapping_or_none(row.get("reason_json"), "reason_json"),
            metrics_snapshot_json=_ensure_mapping_or_none(
                row.get("metrics_snapshot_json"),
                "metrics_snapshot_json",
            ),
            created_at=_ensure_datetime(row.get("created_at"), "created_at"),
        )
    )


def parse_policy_rollout_event_records(
    rows: Sequence[Mapping[str, object]],
) -> tuple[PolicyRolloutEventRecord, ...]:
    """Parse a batch of event rows."""

    return tuple(parse_policy_rollout_event_record(row) for row in rows)


def parse_policy_optimization_run_record(
    row: Mapping[str, object],
) -> PolicyOptimizationRunRecord:
    """Parse one database row into `PolicyOptimizationRunRecord`."""

    return validate_policy_optimization_run_record(
        PolicyOptimizationRunRecord(
            run_id=_ensure_required_text(row.get("run_id"), "run_id"),
            base_policy_version=_ensure_required_text(
                row.get("base_policy_version"),
                "base_policy_version",
            ),
            proposed_policy_version=_ensure_nullable_text(
                row.get("proposed_policy_version"),
                "proposed_policy_version",
            ),
            trigger_type=_ensure_required_text(row.get("trigger_type"), "trigger_type"),
            metrics_snapshot_id=_ensure_nullable_text(
                row.get("metrics_snapshot_id"),
                "metrics_snapshot_id",
            ),
            window_start_ms=_ensure_nullable_int(row.get("window_start_ms"), "window_start_ms"),
            window_end_ms=_ensure_nullable_int(row.get("window_end_ms"), "window_end_ms"),
            metrics_snapshot_json=_ensure_mapping_or_none(
                row.get("metrics_snapshot_json"),
                "metrics_snapshot_json",
            ),
            proposal_json=_ensure_mapping_or_none(row.get("proposal_json"), "proposal_json"),
            validation_result_json=_ensure_mapping_or_none(
                row.get("validation_result_json"),
                "validation_result_json",
            ),
            result_status=_ensure_required_text(row.get("result_status"), "result_status"),
            created_at=_ensure_datetime(row.get("created_at"), "created_at"),
            finished_at=_ensure_datetime_or_none(row.get("finished_at"), "finished_at"),
        )
    )


def _copy_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return deepcopy(dict(value))


def _copy_mapping_or_none(value: Mapping[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    return _copy_mapping(value)


def _ensure_required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StorageValidationError(f"{field_name} must be a non-empty string.")
    return value


def _ensure_nullable_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_required_text(value, field_name)


def _ensure_mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise StorageValidationError(f"{field_name} must be a mapping.")
    return deepcopy(dict(value))


def _ensure_mapping_or_none(value: object, field_name: str) -> dict[str, object] | None:
    if value is None:
        return None
    return _ensure_mapping(value, field_name)


def _ensure_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise StorageValidationError(f"{field_name} must be a datetime.")
    return value


def _ensure_datetime_or_none(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _ensure_datetime(value, field_name)


def _ensure_non_negative_int(value: object, field_name: str) -> int:
    parsed = _ensure_int(value, field_name)
    if parsed < 0:
        raise StorageValidationError(f"{field_name} must be greater than or equal to zero.")
    return parsed


def _ensure_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise StorageValidationError(f"{field_name} must be an int.")
    return value


def _ensure_nullable_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _ensure_int(value, field_name)


def _ensure_ratio(value: object, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise StorageValidationError(f"{field_name} must be a decimal-compatible number.") from exc
    if parsed < Decimal("0") or parsed > Decimal("1"):
        raise StorageValidationError(f"{field_name} must be between 0 and 1 inclusive.")
    return parsed.quantize(Decimal("0.00001"))


def _ensure_ratio_or_none(value: object, field_name: str) -> Decimal | None:
    if value is None:
        return None
    return _ensure_ratio(value, field_name)
