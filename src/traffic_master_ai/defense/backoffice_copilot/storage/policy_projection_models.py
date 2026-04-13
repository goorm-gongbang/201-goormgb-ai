"""Projection DTOs and serializers for PostgreSQL -> Redis policy runtime state."""

from __future__ import annotations

import time
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Sequence

from .policy_control_plane_models import PolicyRolloutStateRecord, PolicyVersionRecord
from .validators import StorageValidationError


@dataclass(slots=True, frozen=True)
class RedisProjectedPolicyDocument:
    """Runtime-readable policy document payload for one Redis version key."""

    schema_version: str
    parameters: Mapping[str, object]
    flags: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class RedisProjectedRolloutState:
    """Runtime-readable rollout payload for `tm:decision-policy:rollout-state`."""

    stage: str
    base_policy_version: str
    ratio: float
    updated_at_ms: int
    candidate_policy_version: str | None = None
    projection_refreshed_at_ms: int | None = None


@dataclass(slots=True, frozen=True)
class PolicyRuntimeProjectionInput:
    """Authoritative PostgreSQL rows required for one Redis projection apply."""

    policy_versions: tuple[PolicyVersionRecord, ...]
    rollout_state: PolicyRolloutStateRecord | None = None


@dataclass(slots=True, frozen=True)
class PolicyProjectionApplyResult:
    """Small apply result for logging, smoke checks, and future worker hooks."""

    projected_policy_versions: tuple[str, ...]
    version_index: tuple[str, ...]
    wrote_rollout_state: bool


def validate_policy_runtime_projection_input(
    projection_input: PolicyRuntimeProjectionInput,
) -> PolicyRuntimeProjectionInput:
    """Validate one projection apply input bundle."""

    if not projection_input.policy_versions and projection_input.rollout_state is None:
        raise StorageValidationError(
            "projection input must include at least one policy version or one rollout state."
        )

    seen_versions: set[str] = set()
    for index, record in enumerate(projection_input.policy_versions):
        if record.policy_version in seen_versions:
            raise StorageValidationError(
                f"policy_versions[{index}] duplicates policy_version {record.policy_version!r}."
            )
        seen_versions.add(record.policy_version)

    rollout_state = projection_input.rollout_state
    if rollout_state is not None:
        if rollout_state.base_policy_version not in seen_versions:
            raise StorageValidationError(
                "projection input must include the rollout state's base_policy_version document."
            )
        if (
            rollout_state.candidate_policy_version is not None
            and rollout_state.candidate_policy_version not in seen_versions
        ):
            raise StorageValidationError(
                "projection input must include the rollout state's candidate_policy_version document."
            )

    return projection_input


def build_redis_projected_policy_document(
    record: PolicyVersionRecord,
) -> RedisProjectedPolicyDocument:
    """Build the minimal runtime policy payload from one authoritative PG row."""

    document = deepcopy(dict(record.document_json))
    schema_version = document.get("schemaVersion")
    if not isinstance(schema_version, str) or not schema_version:
        raise StorageValidationError("document_json.schemaVersion must be a non-empty string.")

    parameters = document.get("parameters")
    if not isinstance(parameters, Mapping):
        raise StorageValidationError("document_json.parameters must be a mapping.")

    flags = document.get("flags", {})
    if not isinstance(flags, Mapping):
        raise StorageValidationError("document_json.flags must be a mapping when present.")

    return RedisProjectedPolicyDocument(
        schema_version=schema_version,
        parameters=deepcopy(dict(parameters)),
        flags=deepcopy(dict(flags)),
    )


def build_redis_projected_rollout_state(
    record: PolicyRolloutStateRecord,
    *,
    projection_refreshed_at_ms: int | None = None,
) -> RedisProjectedRolloutState:
    """Build the minimal runtime rollout payload from one authoritative PG row."""

    ratio = float(record.ratio)
    if ratio < 0.0 or ratio > 1.0:
        raise StorageValidationError("rollout_state.ratio must be between 0 and 1 inclusive.")

    return RedisProjectedRolloutState(
        stage=record.stage,
        base_policy_version=record.base_policy_version,
        candidate_policy_version=record.candidate_policy_version,
        ratio=ratio,
        updated_at_ms=record.updated_at_ms,
        projection_refreshed_at_ms=(
            _now_ms()
            if projection_refreshed_at_ms is None
            else projection_refreshed_at_ms
        ),
    )


def serialize_redis_projected_policy_document(
    payload: RedisProjectedPolicyDocument,
) -> dict[str, object]:
    """Serialize one runtime policy document payload for Redis JSON storage."""

    if not payload.schema_version:
        raise StorageValidationError("schema_version must be a non-empty string.")
    if not isinstance(payload.parameters, Mapping):
        raise StorageValidationError("parameters must be a mapping.")
    if not isinstance(payload.flags, Mapping):
        raise StorageValidationError("flags must be a mapping.")
    return {
        "schemaVersion": payload.schema_version,
        "parameters": deepcopy(dict(payload.parameters)),
        "flags": deepcopy(dict(payload.flags)),
    }


def serialize_redis_projected_rollout_state(
    payload: RedisProjectedRolloutState,
) -> dict[str, object]:
    """Serialize one runtime rollout-state payload for Redis JSON storage."""

    if not payload.stage:
        raise StorageValidationError("stage must be a non-empty string.")
    if not payload.base_policy_version:
        raise StorageValidationError("base_policy_version must be a non-empty string.")
    if payload.candidate_policy_version is not None and not payload.candidate_policy_version:
        raise StorageValidationError("candidate_policy_version must be None or a non-empty string.")
    if payload.ratio < 0.0 or payload.ratio > 1.0:
        raise StorageValidationError("ratio must be between 0 and 1 inclusive.")
    if not isinstance(payload.updated_at_ms, int) or isinstance(payload.updated_at_ms, bool):
        raise StorageValidationError("updated_at_ms must be an int.")
    if payload.projection_refreshed_at_ms is not None and (
        not isinstance(payload.projection_refreshed_at_ms, int)
        or isinstance(payload.projection_refreshed_at_ms, bool)
    ):
        raise StorageValidationError("projection_refreshed_at_ms must be None or an int.")
    return {
        "stage": payload.stage,
        "base_policy_version": payload.base_policy_version,
        "candidate_policy_version": payload.candidate_policy_version,
        "ratio": float(payload.ratio),
        "updated_at_ms": payload.updated_at_ms,
        "projection_refreshed_at_ms": payload.projection_refreshed_at_ms,
    }


def serialize_redis_projected_version_index(
    versions: Sequence[str],
) -> list[str]:
    """Serialize one projected version inventory array for Redis JSON storage."""

    deduped: set[str] = set()
    ordered: list[str] = []
    for index, version in enumerate(versions):
        if not isinstance(version, str) or not version:
            raise StorageValidationError(f"versions[{index}] must be a non-empty string.")
        if version in deduped:
            continue
        deduped.add(version)
        ordered.append(version)
    return sorted(ordered)


def derive_projected_version_index(
    *,
    existing_versions: Sequence[str],
    projection_input: PolicyRuntimeProjectionInput,
) -> tuple[str, ...]:
    """Derive the post-apply version index from existing Redis state and PG input."""

    validate_policy_runtime_projection_input(projection_input)
    combined = list(existing_versions)
    combined.extend(record.policy_version for record in projection_input.policy_versions)
    rollout_state = projection_input.rollout_state
    if rollout_state is not None:
        combined.append(rollout_state.base_policy_version)
        if rollout_state.candidate_policy_version is not None:
            combined.append(rollout_state.candidate_policy_version)
    return tuple(serialize_redis_projected_version_index(combined))


def decimal_to_projection_ratio(value: Decimal) -> float:
    """Expose the Decimal -> float conversion used by rollout payload projection."""

    return float(value)


def _now_ms() -> int:
    return int(time.time() * 1000)
