"""Runtime wiring for D0-MVP evaluate/check/challenge endpoints.

Integrates all pipeline stages (Guard→Analyzer→Planner→Orchestrator)
and emits mandatory audit events at each stage.

Ref: L2/obs_opt/defense_observability_ssot.yaml#mandatory_events
     annex/orchestrator_spec.yaml#execution_order.E5
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Optional

from ...storage_env import (
    load_runtime_policy_config_from_env,
    validate_runtime_policy_env_for_prod,
)
from ...auth_guard import AuthGuardBlockService, UserBlocker
from ..actuators.block import BlockActuator
from ..actuators.challenge import ChallengeActuator
from ..actuators.throttle import ThrottleActuator
from ..brain.analyzer import (
    Analyzer,
    AnalyzerOutput,
    EvidenceSummaryForPlanner,
    EvidenceUpdate,
)
from ..brain.guard import Guard, GuardOutput
from ..brain.planner import Planner, PlannerPlan
from ..brain.turnstile import TurnstileHandler, TurnstileVerdict
from ..core.enums import DefenseAction, DefenseTier, FlowState, ReasonCode
from ..core.models import (
    CheckRequest,
    DefenseDecision,
    EvaluateRequest,
    EvaluateRequestContext,
    EvaluateRequestEvent,
    SessionState,
)
from ..events.catalog import (
    API_CATEGORY_ENUM,
    API_METHOD_ENUM,
    DEF_ANALYZER_EVIDENCE_UPDATED,
    DEF_BLOCK_DECIDED,
    DEF_BLOCK_ENFORCED,
    DEFENSE_UNAVAILABLE,
    DEF_GUARD_SCORED,
    DEF_INVALID_TRANSITION,
    DEF_ORCH_EXECUTED,
    DEF_PLAN_COMPUTED,
    DEF_THROTTLE_APPLIED,
    S3_CHALLENGE_HALTED,
    S3_CHALLENGE_ISSUED,
    S3_CHALLENGE_RESULT,
    TURNSTILE_TRIGGERED,
    TURNSTILE_VERIFIED,
)
from ..events.common import RuntimeEvent
from ..observability.audit_logger import AuditLogger
from ..observability.collector import AuditCollector
from ..observability.dashboard import AdminDashboardService
from ..observability.schemas import AuditEntry
from ..observability.warehouse import AuditWarehouse
from ..optimizer.audit_summarizer import AuditSummarizer
from ..optimizer.pipeline import OfflineOptimizer
from ..orchestrator.engine import Orchestrator, OrchestratorResult
from ..policy.loader import (
    FilePolicyStore,
    PolicyLoader,
    RedisPolicyStore,
    RuntimePolicyAuthorityError,
    snapshot_to_document,
)
from ..policy.snapshot import PolicySnapshot
from ..state.keyspace import DEDUP_KEY_PREFIX
from ..state.block_state import BlockStateManager
from ..state.dedup import DedupChecker
from ..state.redis_client import InMemoryRedis, RedisLike, build_runtime_redis_from_env
from ..state.session_state import SessionStateManager

if TYPE_CHECKING:
    from ...backoffice_copilot.storage.policy_projection_repository import (
        PostgresStrictPolicyAuthorityService,
    )

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class EvaluatePipelineResult:
    """Evaluate pipeline result bundle."""

    orchestrator_result: OrchestratorResult
    guard_output: GuardOutput
    analyzer_output: AnalyzerOutput
    planner_plan: PlannerPlan
    policy: PolicySnapshot
    turnstile_verdict: Optional[TurnstileVerdict] = None


class RuntimeAPIError(Exception):
    """Typed API-facing runtime error with SSOT-aligned status and reason code."""

    def __init__(
        self,
        *,
        status_code: int,
        message: str,
        reason_code: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.reason_code = reason_code
        self.detail = detail

    def to_error_body(self) -> dict[str, Any]:
        body = {
            "status": "FAIL",
            "reasonCode": self.reason_code or ReasonCode.INTERNAL_ERROR.value,
            "message": self.message,
        }
        if self.detail:
            body["detail"] = self.detail
        return body


def _find_policy_authority_error(error: Exception) -> RuntimePolicyAuthorityError | None:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, RuntimePolicyAuthorityError):
            return current
        current = current.__cause__ or current.__context__
    return None


def _runtime_policy_unavailable_api_error(
    error: RuntimePolicyAuthorityError,
) -> RuntimeAPIError:
    return RuntimeAPIError(
        status_code=503,
        reason_code=ReasonCode.INTERNAL_ERROR.value,
        message="Runtime policy projection is unavailable.",
        detail={
            "authority": "redis_projection",
            "repairHint": error.repair_hint,
        },
    )


class DefenseRuntime:
    """Runtime composition root for D0-MVP phases 2~7.

    Integrates AuditLogger for mandatory event emission (Phase 8).
    Ref: L2/obs_opt/defense_observability_ssot.yaml#mandatory_events
    """

    def __init__(
        self,
        *,
        redis: Optional[RedisLike] = None,
        policy_loader: Optional[PolicyLoader] = None,
        policy_authority_service: Optional["PostgresStrictPolicyAuthorityService"] = None,
        audit_logger: Optional[AuditLogger] = None,
        audit_warehouse: Optional[AuditWarehouse] = None,
        user_blocker: Optional[UserBlocker] = None,
        close_redis_on_close: bool = False,
    ) -> None:
        runtime_policy_config = load_runtime_policy_config_from_env()
        if policy_loader is None:
            validate_runtime_policy_env_for_prod()
        if redis is None:
            self.redis, redis_backend = build_runtime_redis_from_env()
            self._close_redis_on_close = close_redis_on_close or redis_backend == "redis"
        else:
            self.redis = redis
            self._close_redis_on_close = close_redis_on_close
        allow_local_policy_fallback = runtime_policy_config.allow_local_fallback or isinstance(
            self.redis, InMemoryRedis
        )
        if policy_loader is not None:
            self.policy_store = policy_loader.store
            self.policy_loader = policy_loader
        else:
            self.policy_store = RedisPolicyStore(
                self.redis,
                fallback=(
                    FilePolicyStore(file_path=runtime_policy_config.store_path)
                    if allow_local_policy_fallback
                    else None
                ),
            )
            self.policy_loader = PolicyLoader(
                store=self.policy_store,
                rollout_salt=runtime_policy_config.rollout_salt,
                cache_seconds=runtime_policy_config.cache_seconds,
                projection_max_staleness_ms=runtime_policy_config.projection_max_staleness_ms,
                strict_authority=not allow_local_policy_fallback,
            )
        if not self.policy_loader.strict_authority:
            self._bootstrap_policy_authority()
        self.audit_logger = audit_logger or AuditLogger.from_env()
        self.audit_warehouse = audit_warehouse or AuditWarehouse.from_env()
        self.audit_collector = AuditCollector(
            audit_logger=self.audit_logger,
            warehouse=self.audit_warehouse,
        )
        self._dashboard: Optional[AdminDashboardService] = None
        self._audit_summarizer: Optional[AuditSummarizer] = None
        self._offline_optimizer: Optional[OfflineOptimizer] = None
        self._policy_authority_service = policy_authority_service
        self._user_blocker = user_blocker or AuthGuardBlockService.from_env()

        self.session_state = SessionStateManager(self.redis)
        self.block_state = BlockStateManager(self.redis)

        self.guard_dedup = DedupChecker(self.redis, key_prefix=f"{DEDUP_KEY_PREFIX}guard:")
        self.analyzer_dedup = DedupChecker(self.redis, key_prefix=f"{DEDUP_KEY_PREFIX}analyzer:")
        self.turnstile_dedup = DedupChecker(self.redis, key_prefix=f"{DEDUP_KEY_PREFIX}turnstile:")

        self.guard = Guard(dedup=self.guard_dedup)
        self.turnstile = TurnstileHandler(
            redis=self.redis,
            dedup=self.turnstile_dedup,
        )
        self.analyzer = Analyzer(
            redis=self.redis,
            session_state=self.session_state,
            dedup=self.analyzer_dedup,
        )
        self.planner = Planner()
        self.orchestrator = Orchestrator(
            session_state=self.session_state,
            block_state=self.block_state,
        )

        self.challenge = ChallengeActuator(
            redis=self.redis,
            session_state=self.session_state,
        )
        self.throttle = ThrottleActuator()
        self.block = BlockActuator(self.block_state)

    def close(self) -> None:
        if self._close_redis_on_close:
            redis_close = getattr(self.redis, "close", None)
            if callable(redis_close):
                redis_close()
        close = getattr(self._user_blocker, "close", None)
        if callable(close):
            close()

    def _bootstrap_policy_authority(self) -> None:
        """Ensure Redis policy store has one active baseline policy doc.

        Redis is runtime authority. This bootstrap is local-only and never runs in strict mode.
        """
        try:
            default_snapshot = PolicySnapshot()
            version = default_snapshot.policy_version
            doc = self.policy_store.fetch_policy_by_version(version)
            self.policy_store.save_policy_version(
                version,
                doc if isinstance(doc, dict) else snapshot_to_document(default_snapshot),
            )
            primary_rollout_state = (
                self.policy_store.get_primary_rollout_state()
                if isinstance(self.policy_store, RedisPolicyStore)
                else self.policy_store.get_rollout_state()
            )
            if primary_rollout_state is None:
                now_ms = int(time.time() * 1000)
                rollout_state = self.policy_store.get_rollout_state()
                if isinstance(rollout_state, dict):
                    rollout_state = {
                        **rollout_state,
                        "projection_refreshed_at_ms": now_ms,
                    }
                self.policy_store.set_rollout_state(
                    rollout_state
                    if isinstance(rollout_state, dict)
                    else {
                        "stage": "FULL",
                        "base_policy_version": version,
                        "candidate_policy_version": None,
                        "ratio": 0.0,
                        "updated_at_ms": now_ms,
                        "projection_refreshed_at_ms": now_ms,
                    }
                )
        except Exception:  # noqa: BLE001 - bootstrap should not break startup
            logger.exception("Failed to bootstrap policy authority")

    def _load_policy_or_raise_runtime_unavailable(self, *, session_id: str) -> PolicySnapshot:
        try:
            return self.policy_loader.load(session_id=session_id)
        except RuntimePolicyAuthorityError as exc:
            raise RuntimeAPIError(
                status_code=503,
                reason_code=ReasonCode.INTERNAL_ERROR.value,
                message="Runtime policy projection is unavailable.",
                detail={
                    "authority": "redis_projection",
                    "repairHint": exc.repair_hint,
                },
            ) from exc

    def dashboard_service(self) -> AdminDashboardService:
        """Lazily create admin dashboard service.

        Keep online path light by not wiring admin-only services until requested.
        """
        if self._dashboard is None:
            self._dashboard = AdminDashboardService(self.audit_warehouse)
        return self._dashboard

    def offline_optimizer_service(self) -> OfflineOptimizer:
        """Lazily create offline optimizer service.

        Offline optimization is not required for online request handling.
        """
        if self._offline_optimizer is None:
            from ...backoffice_copilot.storage import (
                build_clickhouse_offline_metrics_repository,
                build_clickhouse_read_model_config_from_env,
                build_clickhouse_select_client,
                get_clickhouse_audit_table_from_env,
            )

            if self._audit_summarizer is None:
                self._audit_summarizer = AuditSummarizer()
            read_config = build_clickhouse_read_model_config_from_env()
            if not read_config.url:
                raise RuntimeError(
                    "OfflineOptimizer requires TM_CLICKHOUSE_URL because production truth is defense_audit_events."
                )
            metrics_repository = build_clickhouse_offline_metrics_repository(
                build_clickhouse_select_client(read_config),
                table_name=get_clickhouse_audit_table_from_env(),
            )
            self._offline_optimizer = OfflineOptimizer(
                metrics_repository=metrics_repository,
                policy_loader=self.policy_loader,
                audit_summarizer=self._audit_summarizer,
                authority_service=self._get_policy_authority_service(),
            )
        return self._offline_optimizer

    def policy_authority_service(self) -> Optional["PostgresStrictPolicyAuthorityService"]:
        return self._get_policy_authority_service()

    def _get_policy_authority_service(self):
        if self._policy_authority_service is not None:
            return self._policy_authority_service
        if not self.policy_loader.strict_authority:
            return None
        from ...backoffice_copilot.storage import PostgresStrictPolicyAuthorityService

        self._policy_authority_service = PostgresStrictPolicyAuthorityService.from_env(
            redis_client=self.redis
        )
        return self._policy_authority_service

    def evaluate(self, request: EvaluateRequest) -> EvaluatePipelineResult:
        with self.session_state.session_lock(request.session_id):
            return self._evaluate_unlocked(request)

    def _evaluate_unlocked(self, request: EvaluateRequest) -> EvaluatePipelineResult:
        """Run Guard -> Analyzer -> Planner -> Orchestrator pipeline.

        Emits mandatory audit events at each stage.
        Ref: L2/obs_opt/defense_observability_ssot.yaml#mandatory_events
        """
        policy = self.policy_loader.load(session_id=request.session_id)
        state = self.session_state.get_or_create(
            request.session_id,
            policy_version=policy.policy_version,
        )

        event = _to_runtime_event(request)
        errors = event.validate()
        if errors:
            raise ValueError("invalid runtime event: " + "; ".join(errors))

        if self.block_state.is_blocked(request.session_id):
            return self._evaluate_persisted_block(
                request=request,
                event=event,
                state=state,
                policy=policy,
            )

        if state.flow_state == FlowState.SX:
            return self._evaluate_terminal_sx(
                request=request,
                event=event,
                state=state,
                policy=policy,
            )

        features = request.context.features or {}

        # --- Optional external score channel ---
        # Turnstile is only one possible producer in the direct D0 runtime path.
        turnstile_verdict: Optional[TurnstileVerdict] = None
        external_score = _extract_external_score(event=event, features=features)
        turnstile_token = _extract_turnstile_token(request)

        trigger_id = _resolve_turnstile_trigger(event, policy=policy)
        if policy.turnstile_enabled and trigger_id is not None:
            if self.turnstile.should_trigger(
                session_id=request.session_id,
                ts_ms=event.ts_ms,
                max_runs_per_session=policy.turnstile_max_runs_per_session,
                cooldown_seconds=policy.turnstile_cooldown_seconds,
            ):
                self.turnstile.mark_triggered(
                    session_id=request.session_id,
                    ts_ms=event.ts_ms,
                    cooldown_seconds=policy.turnstile_cooldown_seconds,
                    cache_ttl_s=policy.turnstile_cache_ttl_s,
                )
                self._emit_audit(
                    event_type=TURNSTILE_TRIGGERED,
                    request=request,
                    event=event,
                    policy=policy,
                    decision_tier=state.defense_tier.value,
                    decision_action="NONE",
                    result_status="OK",
                    turnstile={
                        "triggerId": trigger_id,
                    },
                )
                turnstile_verdict = self.turnstile.verify(
                    session_id=request.session_id,
                    trace_id=request.trace_id,
                    trigger_id=trigger_id,
                    ts_ms=event.ts_ms,
                    token=turnstile_token,
                    timeout_ms=policy.turnstile_verify_timeout_ms,
                    max_retries=policy.turnstile_verify_max_retries,
                    retry_backoff_ms=policy.turnstile_verify_backoff_ms,
                    cache_ttl_s=policy.turnstile_cache_ttl_s,
                    fail_open_score=policy.turnstile_external_score_on_failure,
                )
                external_score = turnstile_verdict.external_score
                # Emit TURNSTILE_VERIFIED audit event
                self._emit_audit(
                    event_type=TURNSTILE_VERIFIED,
                    request=request,
                    event=event,
                    policy=policy,
                    decision_tier="T0",
                    decision_action="NONE",
                    result_status="OK",
                    turnstile={
                        "triggerId": trigger_id,
                        "externalScore": turnstile_verdict.external_score,
                        "verifyStatus": turnstile_verdict.verify_status,
                        "verifyLatencyMs": turnstile_verdict.verify_latency_ms,
                        "cached": turnstile_verdict.cached,
                    },
                    dedup={
                        "isDuplicate": turnstile_verdict.is_duplicate,
                        "dedupKey": turnstile_verdict.dedup_key,
                    },
                )

        # --- Guard ---
        guard_output = self.guard.score(
            trace_id=request.trace_id,
            event=event,
            state=state,
            policy=policy,
            features=features,
            external_score=external_score,
        )
        self.guard.persist(
            state_manager=self.session_state,
            session_id=request.session_id,
            ts_ms=event.ts_ms,
            output=guard_output,
        )

        # Emit DEF_GUARD_SCORED audit event
        self._emit_audit(
            event_type=DEF_GUARD_SCORED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=guard_output.tier.value,
            decision_action="NONE",
            result_status="OK",
            guard={
                "sInt": guard_output.s_int,
                "sExt": guard_output.s_ext_botlikeness,
                "sT": guard_output.s_t,
                "rPrev": guard_output.r_prev,
                "rNew": guard_output.r_new,
                "ruleHits": list(guard_output.rule_hits),
                "missingFlags": list(guard_output.missing_flags),
            },
            dedup={
                "isDuplicate": guard_output.is_duplicate,
                "dedupKey": guard_output.dedup_key,
            },
        )

        # update local snapshot for next stages
        state.risk_score = guard_output.r_new
        state.defense_tier = guard_output.tier

        # --- Analyzer ---
        analyzer_output = self.analyzer.analyze(
            session_id=request.session_id,
            trace_id=request.trace_id,
            event=event,
            state=state,
            policy=policy,
        )

        # Emit DEF_ANALYZER_EVIDENCE_UPDATED audit event
        self._emit_audit(
            event_type=DEF_ANALYZER_EVIDENCE_UPDATED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=guard_output.tier.value,
            decision_action="NONE",
            result_status="OK",
            analyzer={
                "ruleHits": list(analyzer_output.evidence_update.rule_hits),
                "countersSnapshot": analyzer_output.evidence_update.counters_snapshot,
            },
            dedup={
                "isDuplicate": analyzer_output.is_duplicate,
                "dedupKey": analyzer_output.dedup_key,
            },
        )

        # --- Planner ---
        latest_state = self.session_state.get_or_create(
            request.session_id,
            policy_version=policy.policy_version,
        )
        is_blocked = self.block_state.is_blocked(request.session_id)
        planner_plan = self.planner.plan(
            flow_state=event.flow_state,
            tier=guard_output.tier,
            s3_passed=latest_state.s3_passed,
            blocked=is_blocked,
            policy=policy,
            evidence_summary=analyzer_output.evidence_summary_for_planner,
            policy_version=policy.policy_version,
        )

        # Emit DEF_PLAN_COMPUTED audit event
        self._emit_audit(
            event_type=DEF_PLAN_COMPUTED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=planner_plan.tier.value,
            decision_action=planner_plan.action.value,
            result_status="OK",
            planner={
                "planReason": planner_plan.reason,
            },
        )

        if planner_plan.action == DefenseAction.BLOCK:
            self._emit_audit(
                event_type=DEF_BLOCK_DECIDED,
                request=request,
                event=event,
                policy=policy,
                decision_tier=planner_plan.tier.value,
                decision_action="BLOCK",
                result_status="FAIL",
                result_http_status=policy.block_http_status,
                result_reason_code=policy.block_reason_code,
                block={
                    "ttlSeconds": policy.block_ttl_seconds,
                    "reasonInternal": planner_plan.reason,
                },
            )

        # --- Orchestrator ---
        orchestrator_result = self.orchestrator.execute(
            session_id=request.session_id,
            state=latest_state,
            event=event,
            plan=planner_plan,
            policy=policy,
        )

        # Emit DEF_ORCH_EXECUTED audit event (E5)
        # Ref: annex/orchestrator_spec.yaml#execution_order.E5
        orch_result_status = "OK" if orchestrator_result.allow else "FAIL"
        self._emit_audit(
            event_type=DEF_ORCH_EXECUTED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=orchestrator_result.decision.tier.value,
            decision_action=orchestrator_result.decision.action.value,
            result_status=orch_result_status,
            result_http_status=orchestrator_result.http_status,
            result_reason_code=(
                orchestrator_result.reason_code.value
                if orchestrator_result.reason_code
                else None
            ),
            orchestrator={
                "transition": {
                    "from": orchestrator_result.state_from.value,
                    "to": (
                        orchestrator_result.state_to.value
                        if orchestrator_result.state_to
                        else None
                    ),
                    "applied": orchestrator_result.transition_applied,
                },
            },
        )

        if orchestrator_result.reason_code and (
            orchestrator_result.reason_code.value == "INVALID_TRANSITION"
        ):
            self._emit_audit(
                event_type=DEF_INVALID_TRANSITION,
                request=request,
                event=event,
                policy=policy,
                decision_tier=orchestrator_result.decision.tier.value,
                decision_action=orchestrator_result.decision.action.value,
                result_status="FAIL",
                result_http_status=orchestrator_result.http_status,
                result_reason_code=orchestrator_result.reason_code.value,
                orchestrator={
                    "transition": {
                        "from": orchestrator_result.state_from.value,
                        "to": (
                            orchestrator_result.state_to.value
                            if orchestrator_result.state_to
                            else None
                        ),
                        "applied": orchestrator_result.transition_applied,
                    },
                },
            )

        # Emit DEF_BLOCK_ENFORCED if block decided
        if orchestrator_result.decision.action == DefenseAction.BLOCK:
            self._emit_audit(
                event_type=DEF_BLOCK_ENFORCED,
                request=request,
                event=event,
                policy=policy,
                decision_tier=orchestrator_result.decision.tier.value,
                decision_action="BLOCK",
                result_status="FAIL",
                result_http_status=403,
                result_reason_code="BLOCKED",
                block={
                    "ttlSeconds": orchestrator_result.decision.block_ttl_seconds,
                    "reasonInternal": orchestrator_result.decision.reason,
                },
            )
            self._sync_block_to_auth_guard(
                request=request,
                trigger="d0_runtime_enforced_block",
            )

        return EvaluatePipelineResult(
            orchestrator_result=orchestrator_result,
            guard_output=guard_output,
            analyzer_output=analyzer_output,
            planner_plan=planner_plan,
            policy=policy,
            turnstile_verdict=turnstile_verdict,
        )

    def _evaluate_persisted_block(
        self,
        *,
        request: EvaluateRequest,
        event: RuntimeEvent,
        state: SessionState,
        policy: PolicySnapshot,
    ) -> EvaluatePipelineResult:
        blocked_tier = DefenseTier.T3
        planner_plan = self.planner.plan(
            flow_state=event.flow_state,
            tier=blocked_tier,
            s3_passed=state.s3_passed,
            blocked=True,
            policy=policy,
            evidence_summary=None,
            policy_version=policy.policy_version,
        )
        self._emit_audit(
            event_type=DEF_PLAN_COMPUTED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=planner_plan.tier.value,
            decision_action=planner_plan.action.value,
            result_status="OK",
            planner={
                "planReason": planner_plan.reason,
            },
        )
        self._emit_audit(
            event_type=DEF_BLOCK_DECIDED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=planner_plan.tier.value,
            decision_action="BLOCK",
            result_status="FAIL",
            result_http_status=policy.block_http_status,
            result_reason_code=policy.block_reason_code,
            block={
                "ttlSeconds": policy.block_ttl_seconds,
                "reasonInternal": planner_plan.reason,
            },
        )
        orchestrator_result = self.orchestrator.execute(
            session_id=request.session_id,
            state=state,
            event=event,
            plan=planner_plan,
            policy=policy,
        )
        self._emit_audit(
            event_type=DEF_ORCH_EXECUTED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=orchestrator_result.decision.tier.value,
            decision_action=orchestrator_result.decision.action.value,
            result_status="FAIL",
            result_http_status=orchestrator_result.http_status,
            result_reason_code=(
                orchestrator_result.reason_code.value
                if orchestrator_result.reason_code
                else None
            ),
            orchestrator={
                "transition": {
                    "from": orchestrator_result.state_from.value,
                    "to": (
                        orchestrator_result.state_to.value
                        if orchestrator_result.state_to
                        else None
                    ),
                    "applied": orchestrator_result.transition_applied,
                },
            },
        )
        self._emit_audit(
            event_type=DEF_BLOCK_ENFORCED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=orchestrator_result.decision.tier.value,
            decision_action="BLOCK",
            result_status="FAIL",
            result_http_status=orchestrator_result.http_status or 403,
            result_reason_code="BLOCKED",
            block={
                "ttlSeconds": orchestrator_result.decision.block_ttl_seconds,
                "reasonInternal": orchestrator_result.decision.reason,
            },
        )
        self._sync_block_to_auth_guard(
            request=request,
            trigger="d0_runtime_persisted_block",
        )
        return EvaluatePipelineResult(
            orchestrator_result=orchestrator_result,
            guard_output=_blocked_guard_output(state=state, tier=blocked_tier),
            analyzer_output=_blocked_analyzer_output(
                state=state,
                tier=blocked_tier,
                ts_ms=event.ts_ms,
            ),
            planner_plan=planner_plan,
            policy=policy,
            turnstile_verdict=None,
        )

    def _evaluate_terminal_sx(
        self,
        *,
        request: EvaluateRequest,
        event: RuntimeEvent,
        state: SessionState,
        policy: PolicySnapshot,
    ) -> EvaluatePipelineResult:
        planner_plan = self.planner.plan(
            flow_state=FlowState.SX,
            tier=state.defense_tier,
            s3_passed=state.s3_passed,
            blocked=False,
            policy=policy,
            evidence_summary=None,
            policy_version=policy.policy_version,
        )
        self._emit_audit(
            event_type=DEF_PLAN_COMPUTED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=planner_plan.tier.value,
            decision_action=planner_plan.action.value,
            result_status="OK",
            planner={
                "planReason": planner_plan.reason,
            },
        )
        orchestrator_result = self.orchestrator.execute(
            session_id=request.session_id,
            state=state,
            event=event,
            plan=planner_plan,
            policy=policy,
        )
        self._emit_audit(
            event_type=DEF_ORCH_EXECUTED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=orchestrator_result.decision.tier.value,
            decision_action=orchestrator_result.decision.action.value,
            result_status="OK",
            result_http_status=orchestrator_result.http_status,
            orchestrator={
                "transition": {
                    "from": orchestrator_result.state_from.value,
                    "to": (
                        orchestrator_result.state_to.value
                        if orchestrator_result.state_to
                        else None
                    ),
                    "applied": orchestrator_result.transition_applied,
                },
            },
        )
        return EvaluatePipelineResult(
            orchestrator_result=orchestrator_result,
            guard_output=_blocked_guard_output(state=state, tier=state.defense_tier),
            analyzer_output=_blocked_analyzer_output(
                state=state,
                tier=state.defense_tier,
                ts_ms=event.ts_ms,
            ),
            planner_plan=planner_plan,
            policy=policy,
            turnstile_verdict=None,
        )

    def fail_open_on_unavailable(
        self,
        *,
        request: EvaluateRequest,
        error: Exception,
    ) -> EvaluatePipelineResult:
        """Return allow-path fallback and emit DEFENSE_UNAVAILABLE audit."""
        policy_authority_error = _find_policy_authority_error(error)
        if self.policy_loader.strict_authority and policy_authority_error is not None:
            raise _runtime_policy_unavailable_api_error(policy_authority_error)
        try:
            policy = self.policy_loader.load(session_id=request.session_id)
        except RuntimePolicyAuthorityError as exc:
            if self.policy_loader.strict_authority:
                raise _runtime_policy_unavailable_api_error(exc) from exc
            policy = PolicySnapshot()
        except Exception:
            policy = PolicySnapshot()
        state = self.session_state.get(request.session_id) or SessionState(
            policy_version=policy.policy_version
        )
        event = _to_runtime_event(request)
        decision = DefenseDecision(
            tier=DefenseTier.T0,
            action=DefenseAction.NONE,
            policy_version=policy.policy_version,
            reason="defense_unavailable_fail_open",
        )
        orchestrator_result = OrchestratorResult(
            allow=True,
            decision=decision,
            http_status=None,
            error=None,
            headers=decision.to_headers(),
            state_from=state.flow_state,
            state_to=state.flow_state,
            transition_applied=False,
            reason_code=None,
        )
        planner_plan = PlannerPlan(
            action=DefenseAction.NONE,
            reason="defense_unavailable_fail_open",
            tier=DefenseTier.T0,
            decision=decision,
        )
        self._emit_audit(
            event_type=DEFENSE_UNAVAILABLE,
            request=request,
            event=event,
            policy=policy,
            decision_tier=decision.tier.value,
            decision_action=decision.action.value,
            result_status="OK",
            result_reason_code="DEFENSE_UNAVAILABLE",
            orchestrator={
                "mode": "FAIL_OPEN",
                "errorClass": error.__class__.__name__,
            },
        )
        return EvaluatePipelineResult(
            orchestrator_result=orchestrator_result,
            guard_output=_blocked_guard_output(state=state, tier=decision.tier),
            analyzer_output=_blocked_analyzer_output(
                state=state,
                tier=decision.tier,
                ts_ms=event.ts_ms,
            ),
            planner_plan=planner_plan,
            policy=policy,
            turnstile_verdict=None,
        )

    def issue_challenge(
        self,
        *,
        session_id: str,
        trace_id: str,
        requested_flow_state: Optional[FlowState] = None,
        client_viewport: Optional[Mapping[str, Any]] = None,
        request_meta: Optional[Mapping[str, Any]] = None,
    ):
        """Issue one S3 challenge and emit S3_CHALLENGE_ISSUED audit."""
        with self.session_state.session_lock(session_id):
            policy = self._load_policy_or_raise_runtime_unavailable(session_id=session_id)
            state = self.session_state.get_or_create(
                session_id,
                policy_version=policy.policy_version,
            )
            state = self._prepare_challenge_issue(
                session_id=session_id,
                state=state,
                policy=policy,
                requested_flow_state=requested_flow_state,
            )
            issue = self.challenge.issue(
                session_id=session_id,
                trace_id=trace_id,
                policy=policy,
                client_viewport=client_viewport,
            )
        request = EvaluateRequest(
            session_id=session_id,
            trace_id=trace_id,
            event=EvaluateRequestEvent(
                event_type="S3_RESULT",
                ts_ms=issue.issued_at_ms,
                flow_state=state.flow_state,
                s3_result=None,
            ),
            context=EvaluateRequestContext(
                policy_version=policy.policy_version,
                features=None,
                meta=dict(request_meta or {}) or None,
            ),
        )
        event = RuntimeEvent(
            event_type="S3_RESULT",
            ts_ms=issue.issued_at_ms,
            flow_state=state.flow_state,
            session_id=session_id,
            trace_id=trace_id,
            payload={},
        )
        self._emit_audit(
            event_type=S3_CHALLENGE_ISSUED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=state.defense_tier.value,
            decision_action=state.last_decision_action or "NONE",
            result_status="OK",
            challenge={
                "challengeId": issue.challenge_id,
                "gameId": issue.game_id,
            },
        )
        return issue

    def verify_challenge(
        self,
        *,
        session_id: str,
        trace_id: str,
        challenge_id: str,
        client_answer: Mapping[str, Any],
        request_meta: Optional[Mapping[str, Any]] = None,
        request_user_id: Optional[str] = None,
    ):
        """Verify one S3 challenge and emit result/halt audit events."""
        _validate_challenge_client_answer(client_answer)
        feature_summary = _extract_challenge_feature_summary(client_answer)
        with self.session_state.session_lock(session_id):
            policy = self._load_policy_or_raise_runtime_unavailable(session_id=session_id)
            state = self.session_state.get_or_create(
                session_id,
                policy_version=policy.policy_version,
            )
            if state.flow_state != FlowState.S3:
                raise RuntimeAPIError(
                    status_code=409,
                    reason_code=ReasonCode.INVALID_TRANSITION.value,
                    message="S3 단계에서만 challenge verify를 수행할 수 있습니다.",
                    detail={
                        "currentFlowState": state.flow_state.value,
                    },
                )
            result = self.challenge.verify(
                session_id=session_id,
                trace_id=trace_id,
                challenge_id=challenge_id,
                client_answer=client_answer,
                policy=policy,
            )
            latest_state = self.session_state.get_or_create(
                session_id,
                policy_version=policy.policy_version,
            )
        ts_ms = int(time.time() * 1000)
        request = EvaluateRequest(
            session_id=session_id,
            trace_id=trace_id,
            user_id=request_user_id,
            event=EvaluateRequestEvent(
                event_type="S3_RESULT",
                ts_ms=ts_ms,
                flow_state=latest_state.flow_state,
                s3_result=result.result,
            ),
            context=EvaluateRequestContext(
                policy_version=policy.policy_version,
                features=feature_summary,
                meta=dict(request_meta or {}) or None,
            ),
        )
        try:
            pipeline_out = self.evaluate(request)
        except Exception as exc:  # noqa: BLE001 - preserve challenge response path
            pipeline_out = self.fail_open_on_unavailable(request=request, error=exc)
        latest_state = self.session_state.get_or_create(
            session_id,
            policy_version=policy.policy_version,
        )
        decision_tier = pipeline_out.orchestrator_result.decision.tier.value
        decision_action = pipeline_out.orchestrator_result.decision.action.value
        event = RuntimeEvent(
            event_type="S3_RESULT",
            ts_ms=ts_ms,
            flow_state=latest_state.flow_state,
            session_id=session_id,
            trace_id=trace_id,
            payload={
                "result": result.result,
                "reasonCode": result.reason_code,
            },
        )
        result_status = "OK" if result.result == "PASS" else "FAIL"
        self._emit_audit(
            event_type=S3_CHALLENGE_RESULT,
            request=request,
            event=event,
            policy=policy,
            decision_tier=decision_tier,
            decision_action=decision_action,
            result_status=result_status,
            result_http_status=result.http_status,
            result_reason_code=result.reason_code,
            challenge={
                "challengeId": result.challenge_id,
                "gameId": result.game_id,
                "result": result.result,
                "reasonCode": result.reason_code,
                "attemptsInWindow": result.attempts_in_window,
                "cooldownMs": result.cooldown_ms,
                "verifyLatencyMs": result.verify_latency_ms,
                "featureKeys": sorted(feature_summary.keys()) if feature_summary else [],
            },
        )
        if result.http_status == 429 or result.reason_code == "CHALLENGE_TEMPORARILY_LOCKED":
            self._emit_audit(
                event_type=S3_CHALLENGE_HALTED,
                request=request,
                event=event,
                policy=policy,
                decision_tier=decision_tier,
                decision_action=decision_action,
                result_status="FAIL",
                result_http_status=result.http_status,
                result_reason_code=result.reason_code,
                challenge={
                    "challengeId": result.challenge_id,
                    "gameId": result.game_id,
                    "result": result.result,
                    "reasonCode": result.reason_code,
                    "attemptsInWindow": result.attempts_in_window,
                    "cooldownMs": result.cooldown_ms,
                    "verifyLatencyMs": result.verify_latency_ms,
                    "featureKeys": sorted(feature_summary.keys()) if feature_summary else [],
                },
            )
        return result

    def _prepare_challenge_issue(
        self,
        *,
        session_id: str,
        state: SessionState,
        policy: PolicySnapshot,
        requested_flow_state: Optional[FlowState],
    ) -> SessionState:
        now_ms = int(time.time() * 1000)
        grace_until_ms = now_ms + (policy.s3_grace_ttl_seconds * 1000)
        if requested_flow_state is not None and requested_flow_state != FlowState.S3:
            raise RuntimeAPIError(
                status_code=400,
                reason_code=ReasonCode.VALIDATION_ERROR.value,
                message="challenge issue flowState는 S3만 허용됩니다.",
                detail={"requestedFlowState": requested_flow_state.value},
            )
        retry_gate = self.challenge.current_retry_gate(
            session_id=session_id,
            policy=policy,
            now_ms=now_ms,
        )
        if retry_gate["cooldown_until_ms"] is not None:
            self.session_state.set_s3_grace(
                session_id,
                grace_until_ms=grace_until_ms,
                attempts=retry_gate["attempts_in_window"],
            )
            raise RuntimeAPIError(
                status_code=429,
                reason_code=ReasonCode.CHALLENGE_TEMPORARILY_LOCKED.value,
                message="챌린지 재시도가 잠시 제한되었습니다.",
                detail={
                    "cooldownUntilMs": retry_gate["cooldown_until_ms"],
                    "attemptsInWindow": retry_gate["attempts_in_window"],
                },
            )
        if state.challenge_halt_until_ms is not None and now_ms < state.challenge_halt_until_ms:
            self.session_state.set_s3_grace(
                session_id,
                grace_until_ms=grace_until_ms,
                halt_until_ms=state.challenge_halt_until_ms,
            )
            raise RuntimeAPIError(
                status_code=429,
                reason_code=ReasonCode.CHALLENGE_TEMPORARILY_LOCKED.value,
                message="챌린지 재시도가 잠시 제한되었습니다.",
                detail={"haltUntilMs": state.challenge_halt_until_ms},
            )
        if state.flow_state == FlowState.S3:
            return state
        if state.flow_state != FlowState.S2:
            raise RuntimeAPIError(
                status_code=409,
                reason_code=ReasonCode.INVALID_TRANSITION.value,
                message="S2 -> S3 진입 시점에서만 challenge issue를 수행할 수 있습니다.",
                detail={"currentFlowState": state.flow_state.value},
            )
        self.session_state.update_by_role(
            "orchestrator",
            session_id,
            {
                "flowState": FlowState.S3.value,
                "lastDecisionAction": DefenseAction.REQUIRE_S3.value,
            },
            is_allow=True,
        )
        state.flow_state = FlowState.S3
        state.last_decision_action = DefenseAction.REQUIRE_S3.value
        return state

    def emit_throttle_audit(
        self,
        *,
        request: EvaluateRequest,
        event: RuntimeEvent,
        policy: PolicySnapshot,
        tier: str,
        delay_ms: int,
        request_path: Optional[str] = None,
        request_method: Optional[str] = None,
    ) -> None:
        """Emit DEF_THROTTLE_APPLIED audit event.

        Called from /check adapter after throttle delay is applied.
        Ref: annex/throttle_spec.yaml#observability
        """
        self._emit_audit(
            event_type=DEF_THROTTLE_APPLIED,
            request=request,
            event=event,
            policy=policy,
            decision_tier=tier,
            decision_action="THROTTLE",
            result_status="OK",
            throttle={
                "applied": True,
                "delayMs": delay_ms,
                "endpointPath": request_path,
                "endpointMethod": request_method,
            },
        )

    def _emit_audit(
        self,
        *,
        event_type: str,
        request: EvaluateRequest,
        event: RuntimeEvent,
        policy: PolicySnapshot,
        decision_tier: str,
        decision_action: str,
        result_status: str,
        result_http_status: Optional[int] = None,
        result_reason_code: Optional[str] = None,
        dedup: Optional[dict[str, Any]] = None,
        throttle: Optional[dict[str, Any]] = None,
        block: Optional[dict[str, Any]] = None,
        challenge: Optional[dict[str, Any]] = None,
        turnstile: Optional[dict[str, Any]] = None,
        guard: Optional[dict[str, Any]] = None,
        analyzer: Optional[dict[str, Any]] = None,
        planner: Optional[dict[str, Any]] = None,
        orchestrator: Optional[dict[str, Any]] = None,
    ) -> None:
        """Build and append one canonical audit row to the JSONL log."""
        result: dict[str, Any] = {"status": result_status}
        if result_http_status is not None:
            result["httpStatus"] = result_http_status
        if result_reason_code is not None:
            result["reasonCode"] = result_reason_code
        terminal_reason = _infer_terminal_reason(
            reason_code=result_reason_code,
            action=decision_action,
            flow_state=event.flow_state.value,
            result_status=result_status,
        )
        if terminal_reason:
            result["terminalReason"] = terminal_reason

        server_decision: dict[str, Any] = {
            "riskTier": decision_tier,
            "action": decision_action,
            "policyVersion": policy.policy_version,
        }
        requested_policy_version = request.context.policy_version
        if requested_policy_version:
            server_decision["requestedPolicyVersion"] = requested_policy_version
            if requested_policy_version != policy.policy_version:
                server_decision["policyVersionMismatch"] = True

        request_meta = _extract_request_meta(request)
        challenge_id = None
        if isinstance(challenge, Mapping):
            challenge_id = challenge.get("challengeId") or challenge.get("challenge_id")

        entry = AuditEntry(
            ts_ms=event.ts_ms,
            session_id=request.session_id,
            event_type=event_type,
            raw_payload={
                "request_meta": request_meta,
                "server_decision": server_decision,
                "result": result,
                "dedup": dedup or {},
                "throttle": throttle or {},
                "block": block or {},
                "challenge": challenge or {},
                "turnstile": turnstile or {},
                "guard": guard or {},
                "analyzer": analyzer or {},
                "planner": planner or {},
                "orchestrator": orchestrator or {},
            },
            trace_id=request.trace_id,
            request_id=request.trace_id,
            correlation_id=request_meta.get("correlationId") if isinstance(request_meta.get("correlationId"), str) else None,
            challenge_id=challenge_id if isinstance(challenge_id, str) and challenge_id else None,
            flow_state=event.flow_state.value,
            risk_tier=decision_tier,
            action=decision_action,
            reason_code=result_reason_code,
            policy_version=policy.policy_version,
        )
        try:
            self.audit_logger.append(entry)
            self.audit_collector.ingest_entry(entry)
        except Exception:
            logger.exception("Failed to append audit entry: %s", event_type)

    def check_request_to_evaluate(self, request: CheckRequest) -> EvaluateRequest:
        """Convert /check contract into /evaluate contract."""
        now_ms = int(time.time() * 1000)
        policy = self._load_policy_or_raise_runtime_unavailable(session_id=request.session_id)
        event = EvaluateRequestEvent(
            event_type="API_CALL_OBS",
            ts_ms=now_ms,
            flow_state=request.flow_state,
            request_path=request.upstream_path,
            request_method=request.upstream_method,
            payload={
                key: value
                for key, value in {
                    "category": request.category,
                    "statusCode": request.status_code,
                }.items()
                if value is not None
            }
            or None,
        )
        context = EvaluateRequestContext(
            policy_version=policy.policy_version,
            features=None,
            meta={
                "original_query": request.original_query,
                "client_ip_hash": request.client_ip_hash,
                "turnstile_token": request.turnstile_token,
            },
        )
        return EvaluateRequest(
            session_id=request.session_id,
            trace_id=request.trace_id,
            user_id=request.user_id,
            event=event,
            context=context,
        )

    def _sync_block_to_auth_guard(
        self,
        *,
        request: EvaluateRequest,
        trigger: str,
    ) -> None:
        self._user_blocker.block_user(
            user_id=request.user_id or "",
            session_id=request.session_id,
            trace_id=request.trace_id,
            trigger=trigger,
        )


def build_evaluate_request(
    *,
    session_id: str,
    trace_id: str,
    body: Mapping[str, Any],
) -> EvaluateRequest:
    """Parse dict request body into EvaluateRequest dataclass."""
    event_raw = body.get("event")
    if not isinstance(event_raw, Mapping):
        raise ValueError("event is required")
    context_raw = body.get("context")
    if not isinstance(context_raw, Mapping):
        raise ValueError("context is required")
    policy_version = _required_non_empty_str(
        context_raw.get("policyVersion"),
        field_name="context.policyVersion",
    )
    if not policy_version:
        raise ValueError("context.policyVersion is required")
    event_type = _required_non_empty_str(
        event_raw.get("eventType"),
        field_name="event.eventType",
    )
    ts_ms = _required_non_negative_int(event_raw.get("tsMs"), field_name="event.tsMs")
    flow_state_raw = _required_non_empty_str(
        event_raw.get("flowState"),
        field_name="event.flowState",
    )
    try:
        flow_state = FlowState(flow_state_raw)
    except ValueError as exc:
        raise ValueError("event.flowState must be a valid FlowState") from exc
    event = EvaluateRequestEvent(
        event_type=event_type,
        ts_ms=ts_ms,
        flow_state=flow_state,
        request_path=_optional_str(event_raw.get("requestPath"), field_name="event.requestPath"),
        request_method=_optional_str(event_raw.get("requestMethod"), field_name="event.requestMethod"),
        s3_result=_optional_str(event_raw.get("s3Result"), field_name="event.s3Result"),
        source=_optional_str(event_raw.get("source"), field_name="event.source"),
        payload=_build_event_payload(event_type=event_type, event_raw=event_raw),
    )
    context = EvaluateRequestContext(
        policy_version=policy_version,
        features=_to_optional_dict_or_raise(
            context_raw.get("features"),
            field_name="context.features",
        ),
        meta=_to_optional_dict_or_raise(
            context_raw.get("meta"),
            field_name="context.meta",
        ),
    )
    user_id = _resolve_optional_user_id(
        context_raw.get("userId"),
        context_raw.get("user_id"),
        context.meta,
    )
    return EvaluateRequest(
        session_id=session_id,
        trace_id=trace_id,
        user_id=user_id,
        event=event,
        context=context,
    )


def build_check_request(
    *,
    session_id: str,
    trace_id: str,
    body: Mapping[str, Any],
) -> CheckRequest:
    """Parse /check request body into CheckRequest."""
    upstream_path = _opt_str(body.get("upstreamPath"))
    if not upstream_path:
        raise ValueError("upstreamPath is required")

    upstream_method = _opt_str(body.get("upstreamMethod"))
    if not upstream_method:
        raise ValueError("upstreamMethod is required")
    upstream_method = upstream_method.upper()
    if upstream_method not in API_METHOD_ENUM:
        raise ValueError("upstreamMethod must be one of GET, POST, PUT, DELETE, PATCH")

    category = _opt_str(body.get("category"))
    if category is not None:
        category = category.upper()
        if category not in API_CATEGORY_ENUM:
            raise ValueError("category must be one of READ, WRITE, HIGH_VALUE")

    status_raw = body.get("statusCode")
    status_code = _opt_int(status_raw)
    if status_raw is not None and status_code is None:
        raise ValueError("statusCode must be int")
    flow_state_raw = body.get("flowState")
    if flow_state_raw is None:
        raise ValueError("flowState is required")
    if not isinstance(flow_state_raw, str) or not flow_state_raw:
        raise ValueError("flowState must be non-empty string")
    try:
        flow_state = FlowState(flow_state_raw)
    except ValueError as exc:
        raise ValueError("flowState must be a valid FlowState") from exc

    return CheckRequest(
        session_id=session_id,
        trace_id=trace_id,
        user_id=_resolve_optional_user_id(
            body.get("userId"),
            body.get("user_id"),
            None,
        ),
        upstream_path=upstream_path,
        upstream_method=upstream_method,
        flow_state=flow_state,
        original_query=_opt_str(body.get("original_query")),
        client_ip_hash=_opt_str(body.get("client_ip_hash")),
        turnstile_token=_opt_str(body.get("turnstile_token")),
        category=category,
        status_code=status_code,
    )


def _to_runtime_event(request: EvaluateRequest) -> RuntimeEvent:
    payload: dict[str, Any] = dict(request.event.payload or {})
    if request.event.event_type == "S3_RESULT" and request.event.s3_result:
        payload["result"] = request.event.s3_result
    if request.event.event_type == "API_CALL_OBS":
        if request.event.request_path:
            payload["path"] = request.event.request_path
        if request.event.request_method:
            payload["method"] = request.event.request_method
    return RuntimeEvent(
        event_type=request.event.event_type,
        ts_ms=request.event.ts_ms,
        flow_state=request.event.flow_state,
        session_id=request.session_id,
        trace_id=request.trace_id,
        request_path=request.event.request_path,
        request_method=request.event.request_method,
        source=request.event.source,
        payload=payload,
    )


def _extract_external_score(*, event: RuntimeEvent, features: Mapping[str, Any]) -> Optional[float]:
    if event.external_score is not None:
        return event.external_score
    val = features.get("external_score")
    if val is None:
        # Legacy fallback for older callers that still send turnstile_score.
        val = features.get("turnstile_score")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _extract_turnstile_token(request: EvaluateRequest) -> Optional[str]:
    """Extract turnstile token from request context.meta.

    Ref: annex/turnstile_spec.yaml — token can be in context.meta or features.
    """
    meta = request.context.meta
    if meta and isinstance(meta, Mapping):
        token = meta.get("turnstile_token")
        if token and isinstance(token, str):
            return token
    return None


def _resolve_optional_user_id(
    primary: Any,
    secondary: Any,
    meta: Optional[Mapping[str, Any]],
) -> Optional[str]:
    resolved = _optional_str(primary, field_name="userId")
    if resolved is not None:
        return resolved
    resolved = _optional_str(secondary, field_name="user_id")
    if resolved is not None:
        return resolved
    if meta is None:
        return None
    resolved = _optional_str(meta.get("userId"), field_name="context.meta.userId")
    if resolved is not None:
        return resolved
    return _optional_str(meta.get("user_id"), field_name="context.meta.user_id")


def _resolve_turnstile_trigger(
    event: RuntimeEvent,
    *,
    policy: PolicySnapshot,
) -> Optional[str]:
    """Resolve turnstile trigger ID based on current event and policy.

    Ref: annex/turnstile_spec.yaml#triggers
    """
    if event.flow_state == FlowState.S1:
        return "S1_ENTRY_CLICKED"
    if event.flow_state == FlowState.S3 and policy.turnstile_secondary_trigger_enabled:
        return "S2_TO_S3_PRECHECK"
    if event.flow_state in {FlowState.S6, FlowState.SX}:
        return None
    return None


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _opt_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _required_non_empty_str(value: Any, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _optional_str(value: Any, *, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be string")
    return value


def _required_non_negative_int(value: Any, *, field_name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative int")
    return value


def _to_optional_dict_or_raise(value: Any, *, field_name: str) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be object")
    return dict(value)


def _build_event_payload(
    *,
    event_type: str,
    event_raw: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    payload: dict[str, Any] = {}
    if event_type == "FLOW_STATE_TRANSITION":
        if event_raw.get("fromState") is not None:
            payload["fromState"] = str(event_raw.get("fromState"))
        if event_raw.get("toState") is not None:
            payload["toState"] = str(event_raw.get("toState"))
        if event_raw.get("transitionCause") is not None:
            payload["transitionCause"] = str(event_raw.get("transitionCause"))
    elif event_type == "HIGH_VALUE_CLICK":
        if event_raw.get("tag") is not None:
            payload["tag"] = str(event_raw.get("tag"))
        if event_raw.get("targetId") is not None:
            payload["targetId"] = str(event_raw.get("targetId"))
    elif event_type == "S3_RESULT":
        if event_raw.get("reasonCode") is not None:
            payload["reasonCode"] = _required_non_empty_str(
                event_raw.get("reasonCode"),
                field_name="event.reasonCode",
            )
    elif event_type == "API_CALL_OBS":
        if event_raw.get("category") is not None:
            payload["category"] = str(event_raw.get("category"))
        if event_raw.get("statusCode") is not None:
            status_code = _opt_int(event_raw.get("statusCode"))
            if status_code is None:
                raise ValueError("event.statusCode must be int")
            payload["statusCode"] = status_code
    elif event_type == "TURNSTILE_TRIGGERED":
        if event_raw.get("triggerId") is not None:
            payload["triggerId"] = str(event_raw.get("triggerId"))
        if event_raw.get("widgetMode") is not None:
            payload["widgetMode"] = str(event_raw.get("widgetMode"))
    elif event_type == "TURNSTILE_VERIFIED":
        if event_raw.get("externalScore") is not None:
            try:
                payload["externalScore"] = float(event_raw.get("externalScore"))
            except (TypeError, ValueError):
                raise ValueError("event.externalScore must be float in [0,1]") from None
        if event_raw.get("verifyStatus") is not None:
            payload["verifyStatus"] = str(event_raw.get("verifyStatus"))
        if event_raw.get("verifyLatencyMs") is not None:
            verify_latency = _opt_int(event_raw.get("verifyLatencyMs"))
            if verify_latency is None:
                raise ValueError("event.verifyLatencyMs must be int")
            payload["verifyLatencyMs"] = verify_latency
        if event_raw.get("cached") is not None:
            if not isinstance(event_raw.get("cached"), bool):
                raise ValueError("event.cached must be bool")
            payload["cached"] = event_raw.get("cached")
    return payload or None


def _extract_challenge_feature_summary(client_answer: Mapping[str, Any]) -> Optional[dict[str, float]]:
    raw_features = client_answer.get("features")
    if raw_features is None:
        return None
    if not isinstance(raw_features, Mapping):
        raise RuntimeAPIError(
            status_code=400,
            reason_code=ReasonCode.VALIDATION_ERROR.value,
            message="client_answer.features must be object",
        )
    allowed_keys = {
        "tremorStdDev",
        "linearityRatio",
        "avgVelocity",
        "dwellTime",
        "pathRatio",
    }
    features: dict[str, float] = {}
    for key, value in raw_features.items():
        if key not in allowed_keys:
            raise RuntimeAPIError(
                status_code=400,
                reason_code=ReasonCode.VALIDATION_ERROR.value,
                message=f"client_answer.features.{key} is not allowed",
            )
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise RuntimeAPIError(
                status_code=400,
                reason_code=ReasonCode.VALIDATION_ERROR.value,
                message=f"client_answer.features.{key} must be finite number",
            )
        features[key] = float(value)
    return features or None


def _validate_challenge_client_answer(client_answer: Mapping[str, Any]) -> None:
    catch_ts_ms = client_answer.get("catch_ts_ms")
    if catch_ts_ms is not None and not isinstance(catch_ts_ms, int):
        raise RuntimeAPIError(
            status_code=400,
            reason_code=ReasonCode.VALIDATION_ERROR.value,
            message="client_answer.catch_ts_ms must be int",
        )

    catch_triggered = client_answer.get("catch_triggered")
    if catch_triggered is not None and not isinstance(catch_triggered, bool):
        raise RuntimeAPIError(
            status_code=400,
            reason_code=ReasonCode.VALIDATION_ERROR.value,
            message="client_answer.catch_triggered must be bool",
        )

    glove_pos_norm = client_answer.get("glove_pos_norm")
    if glove_pos_norm is not None:
        if not isinstance(glove_pos_norm, Mapping):
            raise RuntimeAPIError(
                status_code=400,
                reason_code=ReasonCode.VALIDATION_ERROR.value,
                message="client_answer.glove_pos_norm must be object",
            )
        for axis in ("x", "y"):
            axis_val = glove_pos_norm.get(axis)
            if axis_val is None:
                continue
            if not isinstance(axis_val, (int, float)) or not math.isfinite(float(axis_val)):
                raise RuntimeAPIError(
                    status_code=400,
                    reason_code=ReasonCode.VALIDATION_ERROR.value,
                    message=f"client_answer.glove_pos_norm.{axis} must be finite number",
                )

    client_viewport = client_answer.get("client_viewport")
    if client_viewport is not None:
        if not isinstance(client_viewport, Mapping):
            raise RuntimeAPIError(
                status_code=400,
                reason_code=ReasonCode.VALIDATION_ERROR.value,
                message="client_answer.client_viewport must be object",
            )
        for key in ("w", "h"):
            viewport_val = client_viewport.get(key)
            if viewport_val is None:
                continue
            if not isinstance(viewport_val, int) or viewport_val <= 0:
                raise RuntimeAPIError(
                    status_code=400,
                    reason_code=ReasonCode.VALIDATION_ERROR.value,
                    message=f"client_answer.client_viewport.{key} must be positive int",
                )


def _extract_request_meta(request: EvaluateRequest) -> dict[str, Any]:
    meta = request.context.meta or {}
    if not isinstance(meta, Mapping):
        return {}
    request_meta: dict[str, Any] = {}
    correlation_id = meta.get("correlationId")
    if isinstance(correlation_id, str) and correlation_id:
        request_meta["correlationId"] = correlation_id
    if "testMode" in meta:
        request_meta["testMode"] = bool(meta.get("testMode"))
    return request_meta


def _infer_terminal_reason(
    *,
    reason_code: Optional[str],
    action: str,
    flow_state: str,
    result_status: str,
) -> Optional[str]:
    if reason_code == ReasonCode.BLOCKED.value or action == DefenseAction.BLOCK.value:
        return "BLOCKED"
    if flow_state == FlowState.SX.value and result_status == "OK":
        return "DONE"
    if reason_code in {
        ReasonCode.INVALID_TRANSITION.value,
        ReasonCode.INTERNAL_ERROR.value,
        ReasonCode.CHALLENGE_VERIFY_UNAVAILABLE.value,
    }:
        return "ABORT"
    return None


def _blocked_guard_output(
    *,
    state: SessionState,
    tier: DefenseTier,
) -> GuardOutput:
    return GuardOutput(
        s_int=0.0,
        s_ext_botlikeness=0.0,
        s_t=0.0,
        r_prev=state.risk_score,
        r_new=state.risk_score,
        tier=tier,
        rule_hits=(),
        missing_flags=(),
        is_duplicate=False,
        dedup_key=None,
    )


def _blocked_analyzer_output(
    *,
    state: SessionState,
    tier: DefenseTier,
    ts_ms: int,
) -> AnalyzerOutput:
    return AnalyzerOutput(
        evidence_update=EvidenceUpdate(
            rule_hits=(),
            missing_flags=(),
            derived_signals={
                "rapid_high_value_click": False,
                "excessive_read_scanning": False,
                "s3_fail_burst": False,
            },
            counters_snapshot={
                "challengeFailCount": state.challenge_fail_count,
                "seatTakenStreak": state.seat_taken_streak,
                "holdFailStreak": state.hold_fail_streak,
            },
        ),
        evidence_summary_for_planner=EvidenceSummaryForPlanner(
            flow_state=state.flow_state.value,
            tier=tier.value,
            in_probation=bool(
                state.probation_until_ms is not None and ts_ms < state.probation_until_ms
            ),
            s3_passed=state.s3_passed,
            s3_failed_recently=False,
            scan_pressure="LOW",
            hv_click_pressure="LOW",
            counters={
                "challengeFailCount": state.challenge_fail_count,
                "holdFailStreak": state.hold_fail_streak,
            },
        ),
        is_duplicate=False,
        dedup_key=None,
    )


__all__ = [
    "DefenseRuntime",
    "EvaluatePipelineResult",
    "RuntimeAPIError",
    "build_evaluate_request",
    "build_check_request",
]
