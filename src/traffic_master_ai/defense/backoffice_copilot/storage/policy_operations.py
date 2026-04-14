"""Operational policy bootstrap and projection resync commands."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, Sequence

from ...d0_mvp.policy.loader import snapshot_to_document
from ...d0_mvp.policy.snapshot import PolicySnapshot
from .connection import build_postgres_engine_from_env
from .policy_control_plane_models import PolicyRolloutStateRecord, PolicyVersionRecord
from .policy_control_plane_repository import (
    PolicyRolloutStateRepository,
    PolicyVersionRepository,
    PostgresPolicyRolloutStateRepository,
    PostgresPolicyVersionRepository,
)
from .policy_projection_models import PolicyProjectionApplyResult
from .policy_projection_repository import (
    PostgresStrictPolicyAuthorityService,
    project_policy_version_activation,
)

DEFAULT_POLICY_BOOTSTRAP_ROLLOUT_ID = "offline-optimizer-default"
_LOGGER = logging.getLogger(__name__)


class PolicyBootstrapRepositoryBundle(Protocol):
    version_repository: PolicyVersionRepository
    rollout_state_repository: PolicyRolloutStateRepository


@dataclass(slots=True, frozen=True)
class PolicyBootstrapResult:
    policy_version: str
    rollout_id: str
    policy_action: str
    rollout_action: str
    wrote_policy_version: bool
    wrote_rollout_state: bool
    dry_run: bool


def bootstrap_baseline_policy(
    *,
    repositories: PolicyBootstrapRepositoryBundle,
    rollout_id: str,
    dry_run: bool = False,
    snapshot: PolicySnapshot | None = None,
) -> PolicyBootstrapResult:
    baseline = snapshot or PolicySnapshot()
    policy_version = baseline.policy_version
    existing_policy = repositories.version_repository.get_version(policy_version)
    existing_rollout = repositories.rollout_state_repository.get_state(rollout_id)
    wrote_policy_version = existing_policy is None
    wrote_rollout_state = existing_rollout is None
    policy_action = "create" if wrote_policy_version else "skip_existing"
    rollout_action = "create" if wrote_rollout_state else "skip_existing"
    _LOGGER.info(
        "policy_bootstrap_plan rollout_id=%s policy_version=%s dry_run=%s "
        "policy_action=%s rollout_action=%s",
        rollout_id,
        policy_version,
        dry_run,
        policy_action,
        rollout_action,
    )
    if dry_run:
        return PolicyBootstrapResult(
            policy_version=policy_version,
            rollout_id=rollout_id,
            policy_action=policy_action,
            rollout_action=rollout_action,
            wrote_policy_version=False,
            wrote_rollout_state=False,
            dry_run=True,
        )
    if wrote_policy_version:
        repositories.version_repository.save_version(_build_baseline_policy_record(baseline))
    if wrote_rollout_state:
        repositories.rollout_state_repository.save_state(
            _build_baseline_rollout_state_record(
                rollout_id=rollout_id,
                baseline_version=policy_version,
            )
        )
    _LOGGER.info(
        "policy_bootstrap_complete rollout_id=%s policy_version=%s "
        "wrote_policy_version=%s wrote_rollout_state=%s",
        rollout_id,
        policy_version,
        wrote_policy_version,
        wrote_rollout_state,
    )
    return PolicyBootstrapResult(
        policy_version=policy_version,
        rollout_id=rollout_id,
        policy_action=policy_action,
        rollout_action=rollout_action,
        wrote_policy_version=wrote_policy_version,
        wrote_rollout_state=wrote_rollout_state,
        dry_run=False,
    )


def run_policy_bootstrap(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="tm-ai-policy-bootstrap",
        description="Seed baseline policy and rollout rows in PostgreSQL only.",
    )
    parser.add_argument(
        "--rollout-id",
        default=_load_policy_bootstrap_rollout_id_from_env(),
        help=(
            "PostgreSQL policy_rollout_state.rollout_id to seed. "
            "Defaults to TM_POLICY_BOOTSTRAP_ROLLOUT_ID, "
            "TM_POLICY_OPTIMIZER_ROLLOUT_ID, then offline-optimizer-default."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read PostgreSQL state and print the seed plan without writing rows.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
    _configure_logging()
    started = time.monotonic()
    repositories: _PostgresPolicyBootstrapRepositoryBundle | None = None
    try:
        repositories = _build_bootstrap_repositories_from_env()
        result = bootstrap_baseline_policy(
            repositories=repositories,
            rollout_id=args.rollout_id,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        summary = _build_policy_bootstrap_summary(
            rollout_id=args.rollout_id,
            policy_version=None,
            policy_action="failed",
            rollout_action="failed",
            wrote_policy_version=False,
            wrote_rollout_state=False,
            dry_run=args.dry_run,
            started_at_monotonic=started,
            error=f"{type(exc).__name__}: {exc}",
        )
        _log_command_summary("policy_bootstrap_summary", summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1) from exc
    finally:
        if repositories is not None:
            _dispose_if_supported(repositories)
    action = "planned" if result.dry_run else "applied"
    print(
        f"{action} policy_bootstrap policy_version={result.policy_version} "
        f"rollout_id={result.rollout_id} "
        f"policy_action={result.policy_action} "
        f"rollout_action={result.rollout_action} "
        f"wrote_policy_version={str(result.wrote_policy_version).lower()} "
        f"wrote_rollout_state={str(result.wrote_rollout_state).lower()}"
    )
    summary = _build_policy_bootstrap_summary(
        rollout_id=result.rollout_id,
        policy_version=result.policy_version,
        policy_action=result.policy_action,
        rollout_action=result.rollout_action,
        wrote_policy_version=result.wrote_policy_version,
        wrote_rollout_state=result.wrote_rollout_state,
        dry_run=result.dry_run,
        started_at_monotonic=started,
    )
    _log_command_summary("policy_bootstrap_summary", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def run_policy_projection_resync(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="tm-ai-policy-projection-resync",
        description="Resync Redis runtime policy projection from PostgreSQL rows.",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--current",
        action="store_true",
        help="Resync the active rollout row, falling back to the latest row.",
    )
    target.add_argument(
        "--rollout-id",
        help="Resync one specific policy_rollout_state row and its referenced versions.",
    )
    target.add_argument(
        "--policy-version",
        help="Resync one specific policy_versions document without writing rollout state.",
    )
    parser.add_argument(
        "--additional-policy-version",
        action="append",
        default=[],
        help="Extra policy version to include in rollout resync. Repeatable.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
    _configure_logging()
    started = time.monotonic()
    scope = _projection_resync_scope(
        current=bool(args.current or (not args.rollout_id and not args.policy_version)),
        rollout_id=args.rollout_id,
        policy_version=args.policy_version,
    )
    service: PostgresStrictPolicyAuthorityService | None = None
    try:
        service = PostgresStrictPolicyAuthorityService.from_env()
        result = _run_policy_projection_resync(
            service=service,
            current=bool(args.current or (not args.rollout_id and not args.policy_version)),
            rollout_id=args.rollout_id,
            policy_version=args.policy_version,
            additional_policy_versions=tuple(args.additional_policy_version),
        )
    except Exception as exc:
        summary = _build_policy_projection_resync_summary(
            scope=scope,
            result=None,
            started_at_monotonic=started,
            error=f"{type(exc).__name__}: {exc}",
        )
        _log_command_summary("policy_projection_resync_summary", summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1) from exc
    finally:
        if service is not None:
            _dispose_if_supported(service)
    print(
        "applied policy_projection_resync "
        f"projected_policy_versions={','.join(result.projected_policy_versions)} "
        f"version_index={','.join(result.version_index)} "
        f"wrote_rollout_state={str(result.wrote_rollout_state).lower()}"
    )
    summary = _build_policy_projection_resync_summary(
        scope=scope,
        result=result,
        started_at_monotonic=started,
    )
    _log_command_summary("policy_projection_resync_summary", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _run_policy_projection_resync(
    *,
    service: PostgresStrictPolicyAuthorityService,
    current: bool,
    rollout_id: str | None,
    policy_version: str | None,
    additional_policy_versions: Sequence[str] = (),
) -> PolicyProjectionApplyResult:
    if policy_version is not None:
        _LOGGER.info(
            "policy_projection_resync_start scope=policy_version policy_version=%s",
            policy_version,
        )
        result = project_policy_version_activation(
            policy_version=policy_version,
            version_repository=service.version_repository,
            projection_repository=service.projection_repository,
            retry_policy=service.projection_retry_policy,
        )
        _log_projection_result(scope=f"policy_version:{policy_version}", result=result)
        return result
    if rollout_id is not None:
        _LOGGER.info(
            "policy_projection_resync_start scope=rollout rollout_id=%s "
            "additional_policy_versions=%s",
            rollout_id,
            ",".join(additional_policy_versions),
        )
        result = service.resync_runtime_projection(
            rollout_id=rollout_id,
            additional_policy_versions=additional_policy_versions,
        )
        _log_projection_result(scope=f"rollout_id:{rollout_id}", result=result)
        return result
    if current:
        _LOGGER.info(
            "policy_projection_resync_start scope=current additional_policy_versions=%s",
            ",".join(additional_policy_versions),
        )
        result = service.refresh_current_runtime_projection(
            additional_policy_versions=additional_policy_versions,
        )
        _log_projection_result(scope="current", result=result)
        return result
    raise ValueError("projection resync target must be current, rollout_id, or policy_version.")


def _build_bootstrap_repositories_from_env() -> _PostgresPolicyBootstrapRepositoryBundle:
    engine = build_postgres_engine_from_env()
    return _PostgresPolicyBootstrapRepositoryBundle(
        engine=engine,
        version_repository=PostgresPolicyVersionRepository(engine),
        rollout_state_repository=PostgresPolicyRolloutStateRepository(engine),
    )


@dataclass(slots=True)
class _PostgresPolicyBootstrapRepositoryBundle:
    engine: Any
    version_repository: PolicyVersionRepository
    rollout_state_repository: PolicyRolloutStateRepository

    def dispose(self) -> None:
        self.engine.dispose()


def _dispose_if_supported(resource: object) -> None:
    dispose = getattr(resource, "dispose", None)
    if callable(dispose):
        dispose()


def _build_baseline_policy_record(snapshot: PolicySnapshot) -> PolicyVersionRecord:
    now = datetime.now(UTC)
    document = snapshot_to_document(snapshot)
    return PolicyVersionRecord(
        policy_version=snapshot.policy_version,
        schema_version=str(document.get("schemaVersion", "policy.v1")),
        status="ACTIVE",
        source_type="BASELINE_BOOTSTRAP",
        document_json=document,
        validation_result_json={"errors": []},
        created_at=now,
        validated_at=now,
        activated_at=now,
    )


def _build_baseline_rollout_state_record(
    *,
    rollout_id: str,
    baseline_version: str,
) -> PolicyRolloutStateRecord:
    now_ms = int(time.time() * 1000)
    return PolicyRolloutStateRecord(
        rollout_id=rollout_id,
        stage="FULL",
        base_policy_version=baseline_version,
        candidate_policy_version=None,
        ratio=Decimal("0.00000"),
        evaluation_window_seconds=60,
        canary_duration_seconds=120,
        expand_step_index=None,
        stage_started_at_ms=now_ms,
        updated_at_ms=now_ms,
        current_status="ACTIVE",
        rollback_reason=None,
    )


def _load_policy_bootstrap_rollout_id_from_env() -> str:
    for env_name in ("TM_POLICY_BOOTSTRAP_ROLLOUT_ID", "TM_POLICY_OPTIMIZER_ROLLOUT_ID"):
        raw = os.getenv(env_name)
        if raw is not None and raw.strip():
            return raw.strip()
    return DEFAULT_POLICY_BOOTSTRAP_ROLLOUT_ID


def _log_projection_result(*, scope: str, result: PolicyProjectionApplyResult) -> None:
    _LOGGER.info(
        "policy_projection_resync_complete scope=%s projected_policy_versions=%s "
        "version_index=%s wrote_rollout_state=%s",
        scope,
        ",".join(result.projected_policy_versions),
        ",".join(result.version_index),
        result.wrote_rollout_state,
    )


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def _projection_resync_scope(
    *,
    current: bool,
    rollout_id: str | None,
    policy_version: str | None,
) -> str:
    if policy_version is not None:
        return f"policy_version:{policy_version}"
    if rollout_id is not None:
        return f"rollout_id:{rollout_id}"
    if current:
        return "current"
    return "unknown"


def _build_policy_bootstrap_summary(
    *,
    rollout_id: str,
    policy_version: str | None,
    policy_action: str,
    rollout_action: str,
    wrote_policy_version: bool,
    wrote_rollout_state: bool,
    dry_run: bool,
    started_at_monotonic: float,
    error: str | None = None,
) -> dict[str, object]:
    output_count = int(wrote_policy_version) + int(wrote_rollout_state)
    skipped_count = int(policy_action == "skip_existing") + int(rollout_action == "skip_existing")
    if error is not None:
        status = "failed"
        output_count = 0
        skipped_count = 0
    elif dry_run:
        status = "dry_run"
    elif output_count == 0:
        status = "skip"
    else:
        status = "success"
    summary: dict[str, object] = {
        "command": "tm-ai-policy-bootstrap",
        "mode": "dry_run" if dry_run else "apply",
        "status": status,
        "rollout_id": rollout_id,
        "policy_version": policy_version,
        "input_count": 2,
        "output_count": output_count,
        "skipped_count": skipped_count,
        "error_count": 1 if error is not None else 0,
        "duration_ms": max(int((time.monotonic() - started_at_monotonic) * 1000), 0),
        "dry_run": dry_run,
        "policy_action": policy_action,
        "rollout_action": rollout_action,
    }
    if error is not None:
        summary["error"] = error
    return summary


def _build_policy_projection_resync_summary(
    *,
    scope: str,
    result: PolicyProjectionApplyResult | None,
    started_at_monotonic: float,
    error: str | None = None,
) -> dict[str, object]:
    projected = result.projected_policy_versions if result is not None else ()
    summary: dict[str, object] = {
        "command": "tm-ai-policy-projection-resync",
        "mode": "apply",
        "status": "failed" if error is not None else "success",
        "scope": scope,
        "input_count": 1,
        "output_count": len(projected) + int(bool(result and result.wrote_rollout_state)),
        "skipped_count": 0,
        "error_count": 1 if error is not None else 0,
        "duration_ms": max(int((time.monotonic() - started_at_monotonic) * 1000), 0),
        "dry_run": False,
        "projected_policy_versions": tuple(projected),
        "wrote_rollout_state": bool(result and result.wrote_rollout_state),
    }
    if error is not None:
        summary["error"] = error
    return summary


def _log_command_summary(event_name: str, summary: dict[str, object]) -> None:
    _LOGGER.info(
        "%s mode=%s status=%s target=%s input_count=%s output_count=%s "
        "skipped_count=%s error_count=%s duration_ms=%s dry_run=%s",
        event_name,
        summary["mode"],
        summary["status"],
        summary.get("scope") or summary.get("rollout_id"),
        summary["input_count"],
        summary["output_count"],
        summary["skipped_count"],
        summary["error_count"],
        summary["duration_ms"],
        summary["dry_run"],
    )
