"""Offline optimization pipeline built on decision_audit aggregates."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol
from uuid import uuid4

from ...backoffice_copilot.storage.policy_control_plane_models import (
    PolicyOptimizationRunRecord,
    PolicyRolloutEventRecord,
    PolicyRolloutStateRecord,
    PolicyVersionRecord,
)
from ..core.constants import OFFLINE_LLM_MAX_SAMPLE_TRACES, OFFLINE_OPT_AUDIT_FILENAME
from ..observability.dashboard import AdminDashboardService
from ..observability.warehouse import AuditWarehouse
from ..policy.loader import PolicyLoader, PolicyStore, snapshot_to_document
from ..policy.snapshot import PolicySnapshot
from .audit_summarizer import AuditSummarizer
from .effect_evaluator import EffectEvaluator
from .rollout import RolloutExecutor, RolloutState
from .validator import ProposalValidator, proposal_base_values_from_policy

_OFFLINE_OPTIMIZER_ROLLOUT_ID = "offline-optimizer-default"


class PolicyAuthorityService(Protocol):
    """Official control-plane write surface for optimizer/admin actions."""

    rollout_state_repository: Any

    def save_policy_version(
        self,
        record: PolicyVersionRecord,
        *,
        project_to_runtime: bool = False,
    ) -> Any:
        ...

    def save_rollout_state(
        self,
        record: PolicyRolloutStateRecord,
        *,
        additional_policy_versions: tuple[str, ...] | list[str] = (),
    ) -> Any:
        ...

    def append_rollout_event(self, record: PolicyRolloutEventRecord) -> None:
        ...

    def save_optimization_run(self, record: PolicyOptimizationRunRecord) -> None:
        ...


class OfflineOptimizer:
    """Collect -> propose -> validate -> rollout helper."""

    def __init__(
        self,
        *,
        warehouse: AuditWarehouse,
        policy_loader: PolicyLoader,
        validator: Optional[ProposalValidator] = None,
        effect_evaluator: Optional[EffectEvaluator] = None,
        rollout_executor: Optional[RolloutExecutor] = None,
        audit_summarizer: Optional[AuditSummarizer] = None,
        authority_service: PolicyAuthorityService | None = None,
        rollout_id: str = _OFFLINE_OPTIMIZER_ROLLOUT_ID,
        audit_file: str = OFFLINE_OPT_AUDIT_FILENAME,
    ) -> None:
        self._warehouse = warehouse
        self._dashboard = AdminDashboardService(warehouse)
        self._policy_loader = policy_loader
        self._validator = validator or ProposalValidator()
        self._effect_evaluator = effect_evaluator or EffectEvaluator(validator=self._validator)
        self._rollout = rollout_executor or RolloutExecutor()
        self._summarizer = audit_summarizer or AuditSummarizer()
        self._authority_service = authority_service
        self._rollout_id = rollout_id
        self._audit_path = Path(audit_file)
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def store(self) -> PolicyStore:
        return self._policy_loader.store

    def collect_metrics(self, *, window_seconds: int = 600, now_ms: Optional[int] = None) -> dict[str, Any]:
        rows = self._warehouse.read_all()
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        cutoff = now_ms - (window_seconds * 1000)
        window_rows = [row for row in rows if int(row.get("tsMs", 0)) >= cutoff]

        overview = self._dashboard.overview(window_seconds=window_seconds, now_ms=now_ms)
        integrity = self._dashboard.integrity(window_seconds=window_seconds, now_ms=now_ms)
        event_counts: dict[str, int] = {}
        unique_sessions: set[str] = set()
        unique_traces: set[str] = set()
        for row in window_rows:
            event_type = str(row.get("eventType", "UNKNOWN"))
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            session_id = row.get("sessionId")
            trace_id = row.get("traceId")
            if session_id:
                unique_sessions.add(str(session_id))
            if trace_id:
                unique_traces.add(str(trace_id))

        s3_total = sum(overview["s3PassFail"].values())
        s3_pass_rate = _safe_rate(overview["s3PassFail"].get("PASS", 0), s3_total)
        s3_fail_rate = _safe_rate(overview["s3PassFail"].get("FAIL", 0), s3_total)

        return {
            "window_start_ms": cutoff,
            "window_end_ms": now_ms,
            "policy_version": self._dashboard.policy_status().get("latestPolicyVersion") or PolicySnapshot().policy_version,
            "events_total": len(window_rows),
            "unique_sessions": len(unique_sessions),
            "unique_traces": len(unique_traces),
            "event_counts_by_type": event_counts,
            "tier_distribution": overview["tierDistribution"],
            "action_distribution": overview["actionDistribution"],
            "block_rate": overview["blockRate"],
            "require_s3_rate": overview["requireS3Rate"],
            "throttle_applied_rate": overview["throttleAppliedRate"],
            "avg_throttle_delay_ms": overview["throttleDelayMs"]["avg"],
            "s3_pass_rate": s3_pass_rate,
            "s3_fail_rate": s3_fail_rate,
            "s3_temp_lock_rate": self._dashboard.s3_view(window_seconds=window_seconds, now_ms=now_ms)["temporaryLockRate"],
            "dedup_duplicate_rate": integrity["dedupDuplicateRate"],
            "missing_feature_rate": integrity["missingFeatureRate"],
        }

    def run_once(self, *, session_id: str = "offline-optimizer", window_seconds: int = 600) -> dict[str, Any]:
        run_started_at = datetime.now(UTC)
        metrics = self.collect_metrics(window_seconds=window_seconds)
        base_policy = self._policy_loader.load(session_id=session_id)
        metrics_snapshot_id = _metrics_snapshot_id(metrics)
        self._append_audit_event(
            "OFFLINE_OPT_RUN_STARTED",
            base_policy_version=base_policy.policy_version,
            metrics_snapshot_id=metrics_snapshot_id,
            result="NO_CHANGE",
        )
        self._append_audit_event(
            "OFFLINE_OPT_METRICS_SNAPSHOT",
            base_policy_version=base_policy.policy_version,
            metrics_snapshot_id=metrics_snapshot_id,
            result="NO_CHANGE",
            metrics_snapshot=metrics,
        )

        proposal_raw = self._effect_evaluator.propose(
            metrics_snapshot=metrics,
            base_policy_version=base_policy.policy_version,
            base_policy=base_policy,
            metrics_snapshot_id=metrics_snapshot_id,
        )
        langsmith_link = (
            proposal_raw.get("langsmith")
            if proposal_raw is not None and isinstance(proposal_raw, dict)
            else None
        )
        sampled_traces = self._sample_traces(limit=OFFLINE_LLM_MAX_SAMPLE_TRACES)
        summary = self._summarizer.summarize(
            metrics_snapshot=metrics,
            sampled_traces=sampled_traces,
        )
        proposal: Optional[dict[str, Any]] = None
        rejection_errors: Optional[list[str]] = None
        if proposal_raw is not None:
            self._append_audit_event(
                "OFFLINE_OPT_PROPOSAL_CREATED",
                base_policy_version=base_policy.policy_version,
                metrics_snapshot_id=metrics_snapshot_id,
                proposal_id=str(proposal_raw.get("proposal_id", "")),
                patches=proposal_raw.get("patches"),
                result="NO_CHANGE",
                langsmith=langsmith_link,
            )
            validation = self._validator.validate(
                proposal_raw,
                expected_base_policy_version=base_policy.policy_version,
                base_values=proposal_base_values_from_policy(base_policy),
            )
            if validation.valid:
                proposal = validation.sanitized_proposal
                self._append_audit_event(
                    "OFFLINE_OPT_PROPOSAL_VALIDATED",
                    base_policy_version=base_policy.policy_version,
                    metrics_snapshot_id=metrics_snapshot_id,
                    proposal_id=str(proposal.get("proposal_id", "")),
                    patches=proposal.get("patches"),
                    result="NO_CHANGE",
                    langsmith=langsmith_link,
                )
            else:
                rejection_errors = list(validation.errors)
                self._append_audit_event(
                    "OFFLINE_POLICY_PROPOSAL_REJECTED",
                    base_policy_version=base_policy.policy_version,
                    metrics_snapshot_id=metrics_snapshot_id,
                    proposal_id=str(proposal_raw.get("proposal_id", "")),
                    patches=proposal_raw.get("patches"),
                    rollback_reason="; ".join(rejection_errors),
                    result="REJECTED",
                    errors=rejection_errors,
                    langsmith=langsmith_link,
                )
        result = {
            "metricsSnapshotId": metrics_snapshot_id,
            "metrics": metrics,
            "proposal": proposal,
            "proposalRejectedErrors": rejection_errors,
            "summary": summary.report_id if summary else None,
        }
        if langsmith_link:
            result["langsmith"] = langsmith_link
        self._append_audit_event(
            "OFFLINE_OPT_RUN_FINISHED",
            base_policy_version=base_policy.policy_version,
            metrics_snapshot_id=metrics_snapshot_id,
            proposal_id=str(proposal.get("proposal_id", "")) if proposal else None,
            result="REJECTED" if rejection_errors else "NO_CHANGE",
            summary_report_id=summary.report_id if summary else None,
            langsmith=langsmith_link,
        )
        self._persist_optimization_run(
            base_policy_version=base_policy.policy_version,
            metrics_snapshot_id=metrics_snapshot_id,
            metrics=metrics,
            proposal=proposal,
            rejection_errors=rejection_errors,
            created_at=run_started_at,
        )
        return result

    def start_canary(
        self,
        *,
        proposal: Mapping[str, Any],
        session_id: str = "offline-optimizer",
        ratio: float = 0.05,
    ) -> dict[str, Any]:
        base_policy = self._policy_loader.load(session_id=session_id)
        validated = self._validate_proposal(proposal=proposal, base_policy=base_policy)
        self._append_audit_event(
            "OFFLINE_OPT_PROPOSAL_VALIDATED",
            base_policy_version=base_policy.policy_version,
            proposal_id=str(validated["proposal_id"]),
            patches=validated.get("patches"),
            result="NO_CHANGE",
        )
        candidate_version, candidate_doc = self._candidate_document(
            base_policy=base_policy,
            proposal=validated,
        )
        rollout = self._rollout.start_canary(
            base_policy_version=base_policy.policy_version,
            candidate_policy_version=candidate_version,
            ratio=ratio,
        )
        rollout_state = _rollout_state_dict(rollout)
        self._save_candidate_policy_version(
            candidate_version=candidate_version,
            candidate_doc=candidate_doc,
            base_policy_version=base_policy.policy_version,
        )
        self._append_rollout_event_authoritative(
            event_type="OFFLINE_OPT_CANARY_STARTED",
            before_state=None,
            after_state=rollout,
            base_policy_version=base_policy.policy_version,
            candidate_policy_version=candidate_version,
            reason_json={"trigger": "offline_optimizer"},
        )
        self._save_rollout_state_authoritative(
            state=rollout,
            previous_state=None,
        )
        result = {
            "candidatePolicyVersion": candidate_version,
            "rolloutState": rollout_state,
        }
        self._append_audit_event(
            "OFFLINE_OPT_CANARY_STARTED",
            base_policy_version=base_policy.policy_version,
            new_policy_version=candidate_version,
            proposal_id=str(validated["proposal_id"]),
            patches=validated.get("patches"),
            result="APPLIED",
            rollout_state=rollout_state,
        )
        return result

    def expand_rollout(self, *, step_index: int) -> dict[str, Any]:
        current = self.current_rollout_state()
        if current is None:
            raise ValueError("no rollout state to expand")
        state = RolloutState(**current)
        if state.stage == "CANARY":
            self._append_audit_event(
                "OFFLINE_OPT_CANARY_FINISHED",
                base_policy_version=state.base_policy_version,
                new_policy_version=state.candidate_policy_version,
                result="APPLIED",
                rollout_state=_rollout_state_dict(state),
            )
        expanded = self._rollout.expand(state, step_index)
        payload = _rollout_state_dict(expanded)
        self._append_rollout_event_authoritative(
            event_type="OFFLINE_OPT_ROLLOUT_EXPANDED",
            before_state=state,
            after_state=expanded,
            base_policy_version=expanded.base_policy_version,
            candidate_policy_version=expanded.candidate_policy_version,
            reason_json={"trigger": "offline_optimizer", "step_index": step_index},
        )
        self._save_rollout_state_authoritative(
            state=expanded,
            previous_state=state,
        )
        self._append_audit_event(
            "OFFLINE_OPT_ROLLOUT_EXPANDED",
            base_policy_version=expanded.base_policy_version,
            new_policy_version=expanded.candidate_policy_version,
            result="APPLIED",
            rollout_state=payload,
        )
        return payload

    def rollback(self) -> dict[str, Any]:
        current = self.current_rollout_state()
        if current is None:
            raise ValueError("no rollout state to rollback")
        state = RolloutState(**current)
        rolled_back = self._rollout.rollback(state)
        payload = _rollout_state_dict(rolled_back)
        self._append_rollout_event_authoritative(
            event_type="OFFLINE_OPT_ROLLBACK_TRIGGERED",
            before_state=state,
            after_state=rolled_back,
            base_policy_version=state.base_policy_version,
            candidate_policy_version=state.candidate_policy_version,
            reason_json={
                "trigger": "offline_optimizer",
                "rollback_reason": "manual_or_guardrail",
            },
        )
        self._save_rollout_state_authoritative(
            state=rolled_back,
            previous_state=state,
            rollback_reason="manual_or_guardrail",
        )
        self._append_audit_event(
            "OFFLINE_OPT_ROLLBACK_TRIGGERED",
            base_policy_version=state.base_policy_version,
            new_policy_version=state.candidate_policy_version,
            result="ROLLED_BACK",
            rollback_reason="manual_or_guardrail",
            rollout_state=payload,
        )
        return payload

    def evaluate_guardrails(self, deltas: Mapping[str, float]) -> dict[str, Any]:
        should_rollback, reasons = self._rollout.should_rollback(deltas)
        result = {
            "shouldRollback": should_rollback,
            "reasons": reasons,
        }
        self._append_audit_event(
            "OFFLINE_OPT_GUARDRAILS_EVALUATED",
            base_policy_version=self._policy_loader.load(session_id="offline-optimizer").policy_version,
            result="ROLLED_BACK" if should_rollback else "NO_CHANGE",
            rollback_reason="; ".join(reasons) if reasons else None,
            guardrail_eval=result,
        )
        return result

    def current_rollout_state(self) -> Optional[dict[str, Any]]:
        if self._authority_service is not None:
            authoritative = self._authority_service.rollout_state_repository.get_state(
                self._rollout_id
            )
            if authoritative is None:
                return None
            return _rollout_state_from_authoritative_record(authoritative)
        rollout_state = self.store.get_rollout_state()
        if rollout_state is None:
            return None
        return _normalize_rollout_state_dict(rollout_state)

    def latest_summary(self) -> Optional[dict[str, Any]]:
        return self._summarizer.latest()

    def _sample_traces(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self._warehouse.query(limit=500)
        blocked = [row for row in rows if row.get("eventType") == "DEF_BLOCK_ENFORCED"]
        s3_fail = [
            row for row in rows
            if row.get("eventType") == "S3_CHALLENGE_RESULT"
            and _nested(row, "challenge", "result") == "FAIL"
        ]
        slow_throttle = sorted(
            [row for row in rows if row.get("eventType") == "DEF_THROTTLE_APPLIED"],
            key=lambda row: int(_nested(row, "throttle", "delayMs") or 0),
            reverse=True,
        )
        sampled: list[dict[str, Any]] = []
        for group in (blocked, s3_fail, slow_throttle, rows):
            for row in group:
                trace_id = row.get("traceId")
                if not trace_id:
                    continue
                if any(existing.get("traceId") == trace_id for existing in sampled):
                    continue
                sampled.append(
                    {
                        "traceId": trace_id,
                        "sessionId": row.get("sessionId"),
                        "eventType": row.get("eventType"),
                        "reasonCode": _nested(row, "result", "reasonCode"),
                        "policyVersion": _nested(row, "serverDecision", "policyVersion"),
                    }
                )
                if len(sampled) >= limit:
                    return sampled
        return sampled

    def _candidate_document(
        self,
        *,
        base_policy: PolicySnapshot,
        proposal: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        document = snapshot_to_document(base_policy)
        for patch in proposal["patches"]:
            _apply_patch(document, patch)
        ts_suffix = int(time.time())
        candidate_version = f"{base_policy.policy_version}-opt-{ts_suffix}"
        return candidate_version, document

    def _validate_proposal(
        self,
        *,
        proposal: Mapping[str, Any],
        base_policy: PolicySnapshot,
    ) -> dict[str, Any]:
        validation = self._validator.validate(
            proposal,
            expected_base_policy_version=base_policy.policy_version,
            base_values=proposal_base_values_from_policy(base_policy),
        )
        if validation.valid:
            return validation.sanitized_proposal
        errors = list(validation.errors)
        self._append_audit_event(
            "OFFLINE_POLICY_PROPOSAL_REJECTED",
            base_policy_version=base_policy.policy_version,
            proposal_id=str(proposal.get("proposal_id", "")),
            patches=proposal.get("patches"),
            rollback_reason="; ".join(errors),
            result="REJECTED",
            errors=errors,
        )
        raise ValueError("invalid proposal: " + "; ".join(errors))

    def _append_audit_event(
        self,
        event_type: str,
        *,
        base_policy_version: str,
        result: str,
        new_policy_version: Optional[str] = None,
        proposal_id: Optional[str] = None,
        metrics_snapshot_id: Optional[str] = None,
        rollback_reason: Optional[str] = None,
        patches: Optional[Any] = None,
        metrics_snapshot: Optional[Mapping[str, Any]] = None,
        rollout_state: Optional[Mapping[str, Any]] = None,
        errors: Optional[list[str]] = None,
        summary_report_id: Optional[str] = None,
        guardrail_eval: Optional[Mapping[str, Any]] = None,
        langsmith: Optional[Mapping[str, str]] = None,
    ) -> None:
        payload = {
            "tsMs": int(time.time() * 1000),
            "eventType": event_type,
            "base_policy_version": base_policy_version,
            "result": result,
        }
        if new_policy_version is not None:
            payload["new_policy_version"] = new_policy_version
        if proposal_id is not None:
            payload["proposal_id"] = proposal_id
        if metrics_snapshot_id is not None:
            payload["metrics_snapshot_id"] = metrics_snapshot_id
        if rollback_reason is not None:
            payload["rollback_reason"] = rollback_reason
        if patches is not None:
            payload["patches"] = patches
        if metrics_snapshot is not None:
            payload["metrics_snapshot"] = dict(metrics_snapshot)
        if rollout_state is not None:
            payload["rollout_state"] = dict(rollout_state)
        if errors is not None:
            payload["errors"] = list(errors)
        if summary_report_id is not None:
            payload["summary_report_id"] = summary_report_id
        if guardrail_eval is not None:
            payload["guardrail_eval"] = dict(guardrail_eval)
        if langsmith is not None:
            payload["langsmith"] = dict(langsmith)
        with self._audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _save_candidate_policy_version(
        self,
        *,
        candidate_version: str,
        candidate_doc: Mapping[str, Any],
        base_policy_version: str,
    ) -> None:
        if self._authority_service is None:
            self.store.save_policy_version(candidate_version, dict(candidate_doc))
            return
        created_at = datetime.now(UTC)
        self._authority_service.save_policy_version(
            PolicyVersionRecord(
                policy_version=candidate_version,
                schema_version=str(candidate_doc.get("schemaVersion", "policy.v1")),
                status="CANDIDATE",
                source_type="OFFLINE_OPTIMIZER",
                document_json=dict(candidate_doc),
                created_at=created_at,
                parent_policy_version=base_policy_version,
                validation_result_json={"status": "validated"},
                validated_at=created_at,
            ),
            project_to_runtime=False,
        )

    def _save_rollout_state_authoritative(
        self,
        *,
        state: RolloutState,
        previous_state: RolloutState | None,
        rollback_reason: str | None = None,
    ) -> None:
        payload = _rollout_state_dict(state)
        if self._authority_service is None:
            self.store.set_rollout_state(payload)
            return
        self._authority_service.save_rollout_state(
            PolicyRolloutStateRecord(
                rollout_id=self._rollout_id,
                stage=state.stage,
                base_policy_version=state.base_policy_version,
                candidate_policy_version=state.candidate_policy_version,
                ratio=_ratio_decimal(state.ratio),
                evaluation_window_seconds=state.evaluation_window_seconds,
                canary_duration_seconds=state.canary_duration_seconds,
                expand_step_index=state.expand_step_index,
                stage_started_at_ms=state.stage_started_at_ms,
                updated_at_ms=state.updated_at_ms,
                current_status=_rollout_current_status(state.stage),
                rollback_reason=rollback_reason,
            ),
            additional_policy_versions=_projection_versions_for_transition(
                previous_state,
                state,
            ),
        )

    def _append_rollout_event_authoritative(
        self,
        *,
        event_type: str,
        before_state: RolloutState | None,
        after_state: RolloutState,
        base_policy_version: str,
        candidate_policy_version: str | None,
        reason_json: Mapping[str, Any] | None = None,
    ) -> None:
        if self._authority_service is None:
            return
        self._authority_service.append_rollout_event(
            PolicyRolloutEventRecord(
                event_id=f"evt-{uuid4().hex}",
                rollout_id=self._rollout_id,
                event_type=event_type,
                base_policy_version=base_policy_version,
                candidate_policy_version=candidate_policy_version,
                stage_before=None if before_state is None else before_state.stage,
                stage_after=after_state.stage,
                ratio_before=None if before_state is None else _ratio_decimal(before_state.ratio),
                ratio_after=_ratio_decimal(after_state.ratio),
                reason_json=None if reason_json is None else dict(reason_json),
                created_at=datetime.now(UTC),
            )
        )

    def _persist_optimization_run(
        self,
        *,
        base_policy_version: str,
        metrics_snapshot_id: str,
        metrics: Mapping[str, Any],
        proposal: Mapping[str, Any] | None,
        rejection_errors: list[str] | None,
        created_at: datetime,
    ) -> None:
        if self._authority_service is None:
            return
        result_status = "REJECTED" if rejection_errors else "NO_CHANGE"
        if proposal is not None and not rejection_errors:
            result_status = "PROPOSED"
        self._authority_service.save_optimization_run(
            PolicyOptimizationRunRecord(
                run_id=f"opt-{uuid4().hex}",
                base_policy_version=base_policy_version,
                proposed_policy_version=None,
                trigger_type="OFFLINE_OPTIMIZER",
                metrics_snapshot_id=metrics_snapshot_id,
                window_start_ms=int(metrics.get("window_start_ms", 0)),
                window_end_ms=int(metrics.get("window_end_ms", 0)),
                metrics_snapshot_json=dict(metrics),
                proposal_json=None if proposal is None else dict(proposal),
                validation_result_json={"errors": list(rejection_errors or [])},
                result_status=result_status,
                created_at=created_at,
                finished_at=datetime.now(UTC),
            )
        )



def _apply_patch(document: dict[str, Any], patch: Mapping[str, Any]) -> None:
    path = str(patch.get("path", ""))
    op = str(patch.get("op", ""))
    value = float(patch.get("value", 0.0))
    target = _resolve_path(document, path)
    if target is None:
        raise ValueError(f"unknown patch path: {path}")
    parent, key = target
    current_raw = parent[key]
    current = float(current_raw)
    if op == "set":
        result = value
    elif op == "inc":
        result = current + value
    elif op == "dec":
        result = current - value
    else:
        raise ValueError(f"invalid patch op: {op}")
    if isinstance(current_raw, int) and not isinstance(current_raw, bool):
        parent[key] = int(result)
    else:
        parent[key] = result


def _rollout_current_status(stage: str) -> str:
    if stage == "ROLLED_BACK":
        return "ROLLED_BACK"
    if stage == "FULL":
        return "PROMOTED"
    return "ACTIVE"


def _ratio_decimal(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.00001"))


def _projection_versions_for_transition(
    before_state: RolloutState | None,
    after_state: RolloutState,
) -> tuple[str, ...]:
    versions: list[str] = []
    for value in (
        None if before_state is None else before_state.base_policy_version,
        None if before_state is None else before_state.candidate_policy_version,
        after_state.base_policy_version,
        after_state.candidate_policy_version,
    ):
        if value and value not in versions:
            versions.append(value)
    return tuple(versions)


def _normalize_rollout_state_dict(rollout_state: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    required = {
        "stage",
        "base_policy_version",
        "candidate_policy_version",
        "ratio",
        "updated_at_ms",
    }
    if not required.issubset(rollout_state.keys()):
        return None
    return {
        "stage": str(rollout_state["stage"]),
        "base_policy_version": str(rollout_state["base_policy_version"]),
        "candidate_policy_version": (
            str(rollout_state["candidate_policy_version"])
            if rollout_state.get("candidate_policy_version")
            else None
        ),
        "ratio": float(rollout_state["ratio"]),
        "updated_at_ms": int(rollout_state["updated_at_ms"]),
        "stage_duration_seconds": int(rollout_state.get("stage_duration_seconds", 0)),
        "evaluation_window_seconds": int(rollout_state.get("evaluation_window_seconds", 60)),
        "canary_duration_seconds": int(rollout_state.get("canary_duration_seconds", 120)),
        "expand_step_index": (
            int(rollout_state["expand_step_index"])
            if rollout_state.get("expand_step_index") is not None
            else None
        ),
        "stage_started_at_ms": int(rollout_state.get("stage_started_at_ms", rollout_state["updated_at_ms"])),
        "canary_completed_at_ms": (
            int(rollout_state["canary_completed_at_ms"])
            if rollout_state.get("canary_completed_at_ms") is not None
            else None
        ),
        "rollout_finished_at_ms": (
            int(rollout_state["rollout_finished_at_ms"])
            if rollout_state.get("rollout_finished_at_ms") is not None
            else None
        ),
    }


def _rollout_state_from_authoritative_record(
    record: PolicyRolloutStateRecord,
) -> dict[str, Any]:
    stage_duration_seconds = record.canary_duration_seconds if record.stage == "CANARY" else 0
    return {
        "stage": record.stage,
        "base_policy_version": record.base_policy_version,
        "candidate_policy_version": record.candidate_policy_version,
        "ratio": float(record.ratio),
        "updated_at_ms": record.updated_at_ms,
        "stage_duration_seconds": stage_duration_seconds,
        "evaluation_window_seconds": record.evaluation_window_seconds,
        "canary_duration_seconds": record.canary_duration_seconds,
        "expand_step_index": record.expand_step_index,
        "stage_started_at_ms": record.stage_started_at_ms,
        "canary_completed_at_ms": None,
        "rollout_finished_at_ms": record.updated_at_ms if record.stage in {"FULL", "ROLLED_BACK"} else None,
    }



def _resolve_path(document: dict[str, Any], path: str) -> Optional[tuple[dict[str, Any], str]]:
    mapping = {
        "risk.alpha": ("parameters", "risk", "ewma", "alpha"),
        "risk.probation_seconds": (
            "parameters",
            "risk",
            "probation",
            "probation_seconds_after_s3_pass",
        ),
        "tier.thresholds.T0_max": ("parameters", "tiering", "thresholds", "T0_max"),
        "tier.thresholds.T1_max": ("parameters", "tiering", "thresholds", "T1_max"),
        "tier.thresholds.T2_max": ("parameters", "tiering", "thresholds", "T2_max"),
        "tier.hysteresis.margin": ("parameters", "tiering", "hysteresis", "margin"),
        "planner.throttle_delay_ms.T1": ("parameters", "throttle", "delay_ms", "T1"),
        "planner.throttle_delay_ms.T2": ("parameters", "throttle", "delay_ms", "T2"),
        "challenge.max_attempts": (
            "parameters",
            "challenge",
            "failure_policy",
            "max_attempts_per_window",
        ),
        "challenge.cooldown_ms.first": (
            "parameters",
            "challenge",
            "failure_policy",
            "cooldown_ms",
            "first_fail",
        ),
        "challenge.cooldown_ms.second": (
            "parameters",
            "challenge",
            "failure_policy",
            "cooldown_ms",
            "second_fail",
        ),
        "challenge.halt_seconds": (
            "parameters",
            "challenge",
            "failure_policy",
            "on_exceed_max_attempts",
            "temporary_lock",
            "halt_seconds",
        ),
    }
    parts = mapping.get(path)
    if parts is None:
        return None
    cur: dict[str, Any] = document
    for key in parts[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            raise ValueError(f"non-object path segment: {path}")
        cur = nxt
    return cur, parts[-1]



def _nested(data: Mapping[str, Any], *path: str) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, Mapping) or key not in cur:
            return None
        cur = cur[key]
    return cur



def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)



def _rollout_state_dict(state: RolloutState) -> dict[str, Any]:
    return {
        "stage": state.stage,
        "base_policy_version": state.base_policy_version,
        "candidate_policy_version": state.candidate_policy_version,
        "ratio": state.ratio,
        "updated_at_ms": state.updated_at_ms,
        "stage_duration_seconds": state.stage_duration_seconds,
        "evaluation_window_seconds": state.evaluation_window_seconds,
        "canary_duration_seconds": state.canary_duration_seconds,
        "expand_step_index": state.expand_step_index,
        "stage_started_at_ms": state.stage_started_at_ms,
        "canary_completed_at_ms": state.canary_completed_at_ms,
        "rollout_finished_at_ms": state.rollout_finished_at_ms,
    }


def _metrics_snapshot_id(metrics: Mapping[str, Any]) -> str:
    return "metrics-{start}-{end}".format(
        start=int(metrics.get("window_start_ms", 0) or 0),
        end=int(metrics.get("window_end_ms", 0) or 0),
    )


__all__ = ["OfflineOptimizer"]
