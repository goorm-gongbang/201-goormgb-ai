"""Thin runtime read adapter over Redis policy projection keys."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ..state.keyspace import POLICY_ROLLOUT_STATE_KEY, POLICY_VERSION_KEY_PREFIX

logger = logging.getLogger(__name__)


class RuntimeProjectionDecodeError(ValueError):
    """Raised when a Redis runtime projection payload cannot be decoded."""


class RuntimeProjectionNotFoundError(LookupError):
    """Raised when one required Redis runtime projection payload is missing."""


class RuntimeProjectionStaleError(RuntimeError):
    """Raised when a runtime rollout-state projection is older than the allowed age."""

    def __init__(self, *, updated_at_ms: int, now_ms: int, max_staleness_ms: int) -> None:
        self.updated_at_ms = updated_at_ms
        self.now_ms = now_ms
        self.max_staleness_ms = max_staleness_ms
        self.repair_hint = (
            "Refresh Redis projection from PostgreSQL authoritative rows via "
            "reconcile_policy_runtime_projection(...)."
        )
        super().__init__(
            "Runtime rollout-state projection is stale "
            f"(updated_at_ms={updated_at_ms}, now_ms={now_ms}, max_staleness_ms={max_staleness_ms}). "
            f"{self.repair_hint}"
        )


class RuntimePolicyReadStore(Protocol):
    """Minimal store contract consumed by the runtime read adapter."""

    def fetch_policy_by_version(self, version: str) -> dict[str, Any] | None:
        """Read one policy document from the configured runtime store."""

    def get_rollout_state(self) -> dict[str, Any] | None:
        """Read the current rollout-state payload from the configured runtime store."""


@dataclass(slots=True, frozen=True)
class RuntimeProjectedPolicyDocument:
    """Decoded runtime policy projection payload."""

    schema_version: str
    parameters: Mapping[str, object]
    flags: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class RuntimeProjectedRolloutState:
    """Decoded runtime rollout-state projection payload."""

    stage: str
    base_policy_version: str
    ratio: float
    updated_at_ms: int
    candidate_policy_version: str | None = None


@dataclass(slots=True)
class RuntimePolicyReadAdapter:
    """Read-only adapter for Redis policy projection payloads.

    Explicit non-goals:
    - no PostgreSQL direct read
    - no projection repair/write
    - no rollout mutation
    """

    store: RuntimePolicyReadStore

    def fetch_projected_policy_document(
        self,
        policy_version: str,
    ) -> RuntimeProjectedPolicyDocument | None:
        """Read and decode one runtime policy document projection."""

        raw = self._fetch_primary_policy_payload(policy_version)
        if raw is None:
            return None
        try:
            return decode_runtime_projected_policy_document(raw)
        except ValueError:
            logger.warning(
                "Invalid runtime policy projection payload for key %s%s; using default policy.",
                POLICY_VERSION_KEY_PREFIX,
                policy_version,
            )
            return None

    def get_projected_rollout_state(self) -> RuntimeProjectedRolloutState | None:
        """Read and decode the current runtime rollout-state projection."""

        raw = self._fetch_primary_rollout_state_payload()
        if raw is None:
            return None
        try:
            return decode_runtime_projected_rollout_state(raw)
        except ValueError:
            logger.warning(
                "Invalid runtime rollout-state projection payload for key %s; using baseline policy.",
                POLICY_ROLLOUT_STATE_KEY,
            )
            return None

    def require_projected_policy_document(
        self,
        policy_version: str,
    ) -> RuntimeProjectedPolicyDocument:
        """Read one runtime policy document and fail explicitly when missing/invalid."""

        raw = self._fetch_primary_policy_payload(policy_version)
        if raw is None:
            raise RuntimeProjectionNotFoundError(
                f"Runtime policy projection missing for key {POLICY_VERSION_KEY_PREFIX}{policy_version}."
            )
        return decode_runtime_projected_policy_document(raw)

    def require_projected_rollout_state(
        self,
        *,
        max_staleness_ms: int | None = None,
        now_ms: int | None = None,
    ) -> RuntimeProjectedRolloutState:
        """Read one runtime rollout-state projection and fail explicitly when missing/invalid."""

        raw = self._fetch_primary_rollout_state_payload()
        if raw is None:
            raise RuntimeProjectionNotFoundError(
                f"Runtime rollout-state projection missing for key {POLICY_ROLLOUT_STATE_KEY}."
            )
        projected = decode_runtime_projected_rollout_state(raw)
        if max_staleness_ms is not None:
            ensure_runtime_rollout_state_is_fresh(
                projected,
                max_staleness_ms=max_staleness_ms,
                now_ms=now_ms,
            )
        return projected

    def get_projected_rollout_state_with_staleness_check(
        self,
        *,
        max_staleness_ms: int,
        now_ms: int | None = None,
    ) -> RuntimeProjectedRolloutState | None:
        """Read rollout-state projection and drop it when explicit staleness guard fails."""

        try:
            return self.require_projected_rollout_state(
                max_staleness_ms=max_staleness_ms,
                now_ms=now_ms,
            )
        except RuntimeProjectionNotFoundError:
            return None
        except RuntimeProjectionStaleError:
            logger.warning(
                "Stale runtime rollout-state projection detected for key %s; using baseline policy and requiring projection repair.",
                POLICY_ROLLOUT_STATE_KEY,
            )
            return None
        except ValueError:
            logger.warning(
                "Invalid runtime rollout-state projection payload for key %s; using baseline policy.",
                POLICY_ROLLOUT_STATE_KEY,
            )
            return None

    def _fetch_primary_policy_payload(self, policy_version: str) -> dict[str, Any] | None:
        fetch_primary = getattr(self.store, "fetch_primary_policy_by_version", None)
        if callable(fetch_primary):
            return fetch_primary(policy_version)
        return self.store.fetch_policy_by_version(policy_version)

    def _fetch_primary_rollout_state_payload(self) -> dict[str, Any] | None:
        get_primary = getattr(self.store, "get_primary_rollout_state", None)
        if callable(get_primary):
            return get_primary()
        return self.store.get_rollout_state()


def decode_runtime_projected_policy_document(
    payload: Mapping[str, object],
) -> RuntimeProjectedPolicyDocument:
    """Decode the Task 12 Redis policy document payload contract."""

    schema_version = payload.get("schemaVersion")
    if not isinstance(schema_version, str) or not schema_version:
        raise RuntimeProjectionDecodeError("schemaVersion must be a non-empty string.")

    parameters = payload.get("parameters")
    if not isinstance(parameters, Mapping):
        raise RuntimeProjectionDecodeError("parameters must be a mapping.")

    flags = payload.get("flags", {})
    if not isinstance(flags, Mapping):
        raise RuntimeProjectionDecodeError("flags must be a mapping when present.")

    return RuntimeProjectedPolicyDocument(
        schema_version=schema_version,
        parameters=dict(parameters),
        flags=dict(flags),
    )


def decode_runtime_projected_rollout_state(
    payload: Mapping[str, object],
) -> RuntimeProjectedRolloutState:
    """Decode the Task 12 Redis rollout-state payload contract."""

    stage = payload.get("stage")
    if not isinstance(stage, str) or not stage:
        raise RuntimeProjectionDecodeError("stage must be a non-empty string.")

    base_policy_version = payload.get("base_policy_version")
    if not isinstance(base_policy_version, str) or not base_policy_version:
        raise RuntimeProjectionDecodeError("base_policy_version must be a non-empty string.")

    candidate_policy_version = payload.get("candidate_policy_version")
    if candidate_policy_version is not None and (
        not isinstance(candidate_policy_version, str) or not candidate_policy_version
    ):
        raise RuntimeProjectionDecodeError(
            "candidate_policy_version must be None or a non-empty string."
        )

    ratio = payload.get("ratio")
    try:
        parsed_ratio = float(ratio)
    except (TypeError, ValueError) as exc:
        raise RuntimeProjectionDecodeError("ratio must be numeric.") from exc
    if parsed_ratio < 0.0 or parsed_ratio > 1.0:
        raise RuntimeProjectionDecodeError("ratio must be between 0 and 1 inclusive.")

    updated_at_ms = payload.get("updated_at_ms")
    if not isinstance(updated_at_ms, int) or isinstance(updated_at_ms, bool):
        raise RuntimeProjectionDecodeError("updated_at_ms must be an int.")

    return RuntimeProjectedRolloutState(
        stage=stage,
        base_policy_version=base_policy_version,
        candidate_policy_version=candidate_policy_version,
        ratio=parsed_ratio,
        updated_at_ms=updated_at_ms,
    )


def ensure_runtime_rollout_state_is_fresh(
    payload: RuntimeProjectedRolloutState,
    *,
    max_staleness_ms: int,
    now_ms: int | None = None,
) -> None:
    """Raise when one decoded rollout-state projection is older than the allowed age."""

    if max_staleness_ms < 0:
        raise ValueError("max_staleness_ms must be >= 0.")
    current_now_ms = now_ms if now_ms is not None else _now_ms()
    if current_now_ms - payload.updated_at_ms > max_staleness_ms:
        raise RuntimeProjectionStaleError(
            updated_at_ms=payload.updated_at_ms,
            now_ms=current_now_ms,
            max_staleness_ms=max_staleness_ms,
        )


def serialize_runtime_projected_policy_document(
    payload: RuntimeProjectedPolicyDocument,
) -> dict[str, object]:
    """Convert one decoded runtime policy payload back to loader-compatible dict."""

    return {
        "schemaVersion": payload.schema_version,
        "parameters": dict(payload.parameters),
        "flags": dict(payload.flags),
    }


def serialize_runtime_projected_rollout_state(
    payload: RuntimeProjectedRolloutState,
) -> dict[str, object]:
    """Convert one decoded runtime rollout payload back to resolve-compatible dict."""

    return {
        "stage": payload.stage,
        "base_policy_version": payload.base_policy_version,
        "candidate_policy_version": payload.candidate_policy_version,
        "ratio": payload.ratio,
        "updated_at_ms": payload.updated_at_ms,
    }


def parse_runtime_projected_payload(raw: Any) -> dict[str, Any] | None:
    """Parse one raw Redis JSON payload into a mapping or return None."""

    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return dict(parsed)
        return None
    if isinstance(raw, dict):
        return dict(raw)
    return None


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


__all__ = [
    "RuntimePolicyReadAdapter",
    "RuntimePolicyReadStore",
    "RuntimeProjectionDecodeError",
    "RuntimeProjectionNotFoundError",
    "RuntimeProjectedPolicyDocument",
    "RuntimeProjectedRolloutState",
    "RuntimeProjectionStaleError",
    "decode_runtime_projected_policy_document",
    "decode_runtime_projected_rollout_state",
    "ensure_runtime_rollout_state_is_fresh",
    "parse_runtime_projected_payload",
    "serialize_runtime_projected_policy_document",
    "serialize_runtime_projected_rollout_state",
]
