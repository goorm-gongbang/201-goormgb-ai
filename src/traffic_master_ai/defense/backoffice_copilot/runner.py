"""Operational CLI for Backoffice Copilot Post-Review."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from . import (
    BackofficeCopilotWorkflowDependencies,
    PostReviewRunInput,
    build_backoffice_copilot_workflow,
    build_openai_review_adapter,
    build_openai_summary_adapter,
)
from .analysis.fallback import DecisionAuditRowProvider
from .core.models import DefenseAuditEventRow, PostReviewRunRecord, PostReviewSessionResultRecord
from .core.state import AnalysisInput
from .ingest import load_analysis_input, load_defense_audit_events
from .storage import (
    BackofficeClickHouseReadModelInput,
    ClickHousePostReviewCandidateRow,
    ClickHouseSessionRollupRow,
    PkConflictPolicy,
    PostgresPostReviewWriteRepository,
    build_clickhouse_post_review_candidate_reader_repository,
    build_clickhouse_read_model_config_from_env,
    build_clickhouse_select_client,
    build_clickhouse_session_rollup_reader_repository,
    load_backoffice_clickhouse_read_model_input,
)
from .storage.connection import build_postgres_engine_from_env
from .storage.repository import PostReviewWriteRepository

DEFAULT_POST_REVIEW_LIMIT = 1000
DEFAULT_POST_REVIEW_WINDOW_SECONDS = 600
DEFAULT_OFFLINE_LLM_MODEL = "gpt-4o-mini"
DEFAULT_OFFLINE_LLM_TIMEOUT_MS = 15000

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class PostReviewExecutionConfig:
    match_id: str
    window_start_ms: int
    window_end_ms: int
    limit: int = DEFAULT_POST_REVIEW_LIMIT
    dry_run: bool = False
    conflict_policy: PkConflictPolicy = PkConflictPolicy.UPSERT
    use_raw_audit_fallback: bool = False
    fixture_jsonl_path: Path | None = None
    require_llm: bool = False
    export_dir: Path | None = None
    session_analysis_max_workers: int = 4
    review_max_workers: int = 4


@dataclass(slots=True, frozen=True)
class PostReviewCliResult:
    status: str
    final_status: str | None
    match_id: str
    window_start_ms: int
    window_end_ms: int
    dry_run: bool
    input_source: str
    input_count: int
    candidate_count: int
    output_count: int
    suspicious_count: int
    skipped_count: int
    warning_count: int
    error_count: int
    duration_ms: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


@dataclass(slots=True)
class DryRunPostReviewWriteRepository:
    saved_runs: list[PostReviewRunRecord]
    saved_session_results: list[tuple[PostReviewSessionResultRecord, ...]]

    def __init__(self) -> None:
        self.saved_runs = []
        self.saved_session_results = []

    def save_run(self, run_record: PostReviewRunRecord) -> None:
        self.saved_runs.append(run_record)

    def save_session_results(
        self,
        session_records: Sequence[PostReviewSessionResultRecord],
    ) -> None:
        self.saved_session_results.append(tuple(session_records))

    def save_bundle(
        self,
        run_record: PostReviewRunRecord,
        session_records: Sequence[PostReviewSessionResultRecord],
    ) -> None:
        self.saved_runs.append(run_record)
        self.saved_session_results.append(tuple(session_records))


def run_post_review(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")
    started = time.monotonic()
    config: PostReviewExecutionConfig | None = None
    try:
        config = _config_from_args(args)
        analysis_input, input_source, input_count = load_post_review_analysis_input(config)
        result = execute_post_review(
            config=config,
            analysis_input=analysis_input,
            input_source=input_source,
            input_count=input_count,
            started_at_monotonic=started,
        )
    except Exception as exc:
        failed_config = config or PostReviewExecutionConfig(
            match_id=args.match_id or "unknown",
            window_start_ms=args.window_start_ms or 0,
            window_end_ms=args.window_end_ms or 0,
            dry_run=bool(args.dry_run),
        )
        duration_ms = _duration_ms(started)
        summary = PostReviewCliResult(
            status="failed",
            final_status="FAILED",
            match_id=failed_config.match_id,
            window_start_ms=failed_config.window_start_ms,
            window_end_ms=failed_config.window_end_ms,
            dry_run=failed_config.dry_run,
            input_source="unknown",
            input_count=0,
            candidate_count=0,
            output_count=0,
            suspicious_count=0,
            skipped_count=0,
            warning_count=0,
            error_count=1,
            duration_ms=duration_ms,
        )
        LOGGER.exception(
            "post_review_summary mode=%s status=failed match_id=%s window_start_ms=%s "
            "window_end_ms=%s input_count=0 output_count=0 skipped_count=0 error_count=1 "
            "duration_ms=%s dry_run=%s error=%s",
            _post_review_mode(failed_config),
            failed_config.match_id,
            failed_config.window_start_ms,
            failed_config.window_end_ms,
            duration_ms,
            failed_config.dry_run,
            f"{type(exc).__name__}: {exc}",
        )
        print(summary.to_json())
        raise SystemExit(1) from exc

    print(result.to_json())
    if result.status == "failed" or result.final_status == "FAILED":
        raise SystemExit(1)


def load_post_review_analysis_input(
    config: PostReviewExecutionConfig,
) -> tuple[AnalysisInput, str, int]:
    run_input = _run_input_from_config(config)
    if config.fixture_jsonl_path is not None:
        analysis_input = load_analysis_input(config.fixture_jsonl_path, run_input=run_input)
        return analysis_input, "fixture_jsonl", len(analysis_input.defense_audit_events)

    read_model_input = _load_clickhouse_read_model_input(config)
    analysis_input = build_analysis_input_from_clickhouse_read_models(read_model_input)
    return analysis_input, "clickhouse_read_model", len(read_model_input.candidate_rows)


def execute_post_review(
    *,
    config: PostReviewExecutionConfig,
    analysis_input: AnalysisInput,
    input_source: str,
    input_count: int,
    repository: PostReviewWriteRepository | None = None,
    started_at_monotonic: float | None = None,
) -> PostReviewCliResult:
    started = time.monotonic() if started_at_monotonic is None else started_at_monotonic
    LOGGER.info(
        "post_review_start match_id=%s window_start_ms=%s window_end_ms=%s "
        "input_source=%s input_count=%s dry_run=%s",
        config.match_id,
        config.window_start_ms,
        config.window_end_ms,
        input_source,
        input_count,
        config.dry_run,
    )
    if input_count == 0:
        result = PostReviewCliResult(
            status="no_input",
            final_status=None,
            match_id=config.match_id,
            window_start_ms=config.window_start_ms,
            window_end_ms=config.window_end_ms,
            dry_run=config.dry_run,
            input_source=input_source,
            input_count=0,
            candidate_count=0,
            output_count=0,
            suspicious_count=0,
            skipped_count=1,
            warning_count=0,
            error_count=0,
            duration_ms=_duration_ms(started),
        )
        _log_post_review_summary(config=config, result=result)
        return result

    owned_engine = None
    try:
        selected_repository = repository
        if config.dry_run:
            selected_repository = DryRunPostReviewWriteRepository()
        elif selected_repository is None:
            owned_engine = build_postgres_engine_from_env()
            selected_repository = PostgresPostReviewWriteRepository(
                engine=owned_engine,
                conflict_policy=config.conflict_policy,
            )

        raw_fallback_provider = _build_raw_fallback_provider(config)
        review_adapter, summary_adapter = _build_llm_adapters_from_env(config.require_llm)
        workflow = build_backoffice_copilot_workflow(
            BackofficeCopilotWorkflowDependencies(
                audit_events_jsonl_path=None,
                analysis_input_provider=lambda _: analysis_input,
                repository=selected_repository,
                conflict_policy=config.conflict_policy,
                llm_review_adapter=review_adapter,
                summary_adapter=summary_adapter,
                export_dir=config.export_dir,
                session_analysis_max_workers=config.session_analysis_max_workers,
                review_max_workers=config.review_max_workers,
                raw_fallback_provider=raw_fallback_provider,
                repository_ready=True,
            )
        )
        workflow_result = workflow.invoke(_run_input_from_config(config))
        candidate_count = len(workflow_result.state.candidate_sessions)
        output_count = len(workflow_result.state.post_review_session_result_rows)
        suspicious_count = (
            workflow_result.state.post_review_runs_row.suspicious_count
            if workflow_result.state.post_review_runs_row is not None
            else 0
        )
        result = PostReviewCliResult(
            status="completed" if workflow_result.final_status != "FAILED" else "failed",
            final_status=workflow_result.final_status,
            match_id=config.match_id,
            window_start_ms=config.window_start_ms,
            window_end_ms=config.window_end_ms,
            dry_run=config.dry_run,
            input_source=input_source,
            input_count=input_count,
            candidate_count=candidate_count,
            output_count=output_count,
            suspicious_count=suspicious_count,
            skipped_count=max(input_count - candidate_count, 0),
            warning_count=len(workflow_result.state.warnings),
            error_count=len(workflow_result.state.errors),
            duration_ms=_duration_ms(started),
        )
        _log_post_review_summary(config=config, result=result)
        return result
    finally:
        if owned_engine is not None:
            owned_engine.dispose()


def build_analysis_input_from_clickhouse_read_models(
    read_model_input: BackofficeClickHouseReadModelInput,
) -> AnalysisInput:
    rollups_by_session_id = {row.session_id: row for row in read_model_input.session_rollups}
    rows = tuple(
        _candidate_row_to_audit_events(
            candidate,
            rollups_by_session_id.get(candidate.session_id),
        )
        for candidate in read_model_input.candidate_rows
    )
    return AnalysisInput(
        defense_audit_events=tuple(event for group in rows for event in group),
        raw_audit_available=False,
    )


def _candidate_row_to_audit_events(
    candidate: ClickHousePostReviewCandidateRow,
    rollup: ClickHouseSessionRollupRow | None,
) -> tuple[DefenseAuditEventRow, ...]:
    first_ts_ms = rollup.first_ts_ms if rollup is not None else candidate.first_ts_ms
    last_ts_ms = rollup.last_ts_ms if rollup is not None else candidate.last_ts_ms
    latest_action = candidate.latest_action or (
        rollup.latest_action if rollup is not None else None
    )
    latest_tier = candidate.latest_risk_tier or (
        rollup.latest_risk_tier if rollup is not None else None
    )
    latest_reason_code = candidate.latest_reason_code or (
        rollup.latest_reason_code if rollup is not None else None
    )
    latest_policy_version = candidate.latest_policy_version or (
        rollup.latest_policy_version if rollup is not None else None
    )
    latest_flow_state = rollup.latest_flow_state if rollup is not None else None
    block_action_count = max(
        candidate.block_action_count,
        rollup.block_action_count if rollup else 0,
    )
    throttle_action_count = max(
        candidate.throttle_action_count,
        rollup.throttle_action_count if rollup else 0,
    )
    challenge_issue_count = max(
        candidate.challenge_issue_count,
        rollup.challenge_issue_count if rollup else 0,
    )
    challenge_verified_count = max(
        candidate.challenge_verified_count,
        rollup.challenge_verified_count if rollup else 0,
    )
    payload = {
        "latest_flow_state": latest_flow_state or "UNKNOWN",
        "latest_action": latest_action or "UNKNOWN",
        "latest_tier": latest_tier or "UNKNOWN",
        "terminal_outcome": _terminal_outcome_for(latest_action, block_action_count),
        "reason_code": latest_reason_code or candidate.candidate_reason,
        "terminal_reason": candidate.candidate_reason,
        "latest_policy_version": latest_policy_version or "",
        "candidate_reason": candidate.candidate_reason,
        "counts": {
            "throttle_action_count": throttle_action_count,
            "block_action_count": block_action_count,
            "challenge_issue_count": challenge_issue_count,
            "challenge_verified_count": challenge_verified_count,
        },
    }
    events: list[DefenseAuditEventRow] = []
    for index in range(block_action_count):
        events.append(
            DefenseAuditEventRow(
                ts_ms=min(last_ts_ms, first_ts_ms + index),
                trace_id=f"{candidate.session_id}:block:{index}",
                session_id=candidate.session_id,
                event_type="DEF_BLOCK_ENFORCED",
                payload=payload,
            )
        )
    for index in range(throttle_action_count):
        events.append(
            DefenseAuditEventRow(
                ts_ms=min(last_ts_ms, first_ts_ms + block_action_count + index),
                trace_id=f"{candidate.session_id}:throttle:{index}",
                session_id=candidate.session_id,
                event_type="DEF_THROTTLE_APPLIED",
                payload=payload,
            )
        )
    for index in range(max(challenge_issue_count - challenge_verified_count, 0)):
        events.append(
            DefenseAuditEventRow(
                ts_ms=min(
                    last_ts_ms,
                    first_ts_ms + block_action_count + throttle_action_count + index,
                ),
                trace_id=f"{candidate.session_id}:challenge:{index}",
                session_id=candidate.session_id,
                event_type="S3_CHALLENGE_RESULT",
                payload={
                    **payload,
                    "challenge": {"result": "FAIL"},
                    "result": {
                        "status": "FAIL",
                        "reasonCode": latest_reason_code or candidate.candidate_reason,
                    },
                },
            )
        )
    events.append(
        DefenseAuditEventRow(
            ts_ms=last_ts_ms,
            trace_id=f"{candidate.session_id}:candidate",
            session_id=candidate.session_id,
            event_type="DEF_ORCH_EXECUTED",
            payload={
                **payload,
                "serverDecision": {
                    "action": latest_action or "UNKNOWN",
                    "riskTier": latest_tier or "UNKNOWN",
                },
                "result": {
                    "reasonCode": latest_reason_code or candidate.candidate_reason,
                    "terminalReason": candidate.candidate_reason,
                },
            },
        )
    )
    return tuple(events)


def _terminal_outcome_for(latest_action: str | None, block_action_count: int) -> str:
    if block_action_count > 0 or latest_action == "BLOCK":
        return "BLOCKED"
    if latest_action:
        return "NOT_BLOCKED"
    return "UNKNOWN"


def _load_clickhouse_read_model_input(
    config: PostReviewExecutionConfig,
) -> BackofficeClickHouseReadModelInput:
    read_config = build_clickhouse_read_model_config_from_env()
    client = build_clickhouse_select_client(read_config)
    return load_backoffice_clickhouse_read_model_input(
        window_start_ms=config.window_start_ms,
        window_end_ms=config.window_end_ms,
        session_rollup_repository=build_clickhouse_session_rollup_reader_repository(client),
        candidate_repository=build_clickhouse_post_review_candidate_reader_repository(client),
        limit=config.limit,
    )


def _build_llm_adapters_from_env(require_llm: bool) -> tuple[object | None, object | None]:
    api_key = os.getenv("TM_OFFLINE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        if require_llm:
            raise ValueError("TM_OFFLINE_LLM_API_KEY or OPENAI_API_KEY is required.")
        LOGGER.warning("post_review_llm_adapter_missing fallback=deterministic")
        return None, None

    model = os.getenv("TM_OFFLINE_LLM_MODEL", DEFAULT_OFFLINE_LLM_MODEL)
    endpoint = os.getenv("OPENAI_BASE_URL") or os.getenv("TM_OFFLINE_LLM_ENDPOINT")
    timeout_ms = _parse_positive_int_env(
        "TM_OFFLINE_LLM_TIMEOUT_MS",
        DEFAULT_OFFLINE_LLM_TIMEOUT_MS,
    )
    return (
        build_openai_review_adapter(
            api_key=api_key,
            model=model,
            endpoint=endpoint,
            timeout_ms=timeout_ms,
        ),
        build_openai_summary_adapter(
            api_key=api_key,
            model=model,
            endpoint=endpoint,
            timeout_ms=timeout_ms,
        ),
    )


def _build_raw_fallback_provider(
    config: PostReviewExecutionConfig,
) -> DecisionAuditRowProvider | None:
    if not config.use_raw_audit_fallback:
        return None
    if config.fixture_jsonl_path is None:
        raise ValueError(
            "--use-raw-audit-fallback requires --fixture-jsonl until a ClickHouse raw "
            "audit fallback provider is available."
        )
    fixture_jsonl_path = config.fixture_jsonl_path

    def _provider(
        session_id: str,
        window_start_ms: int,
        window_end_ms: int,
        limit: int,
    ) -> Sequence[DefenseAuditEventRow]:
        rows = load_defense_audit_events(
            fixture_jsonl_path,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            limit=limit,
        )
        return tuple(row for row in rows if row.session_id == session_id)

    return _provider


def _run_input_from_config(config: PostReviewExecutionConfig) -> PostReviewRunInput:
    return PostReviewRunInput(
        match_id=config.match_id,
        window_start_ms=config.window_start_ms,
        window_end_ms=config.window_end_ms,
        limit=config.limit,
        use_raw_audit_fallback=config.use_raw_audit_fallback,
    )


def resolve_default_post_review_window(
    *,
    now_ms: int | None = None,
    window_seconds: int = DEFAULT_POST_REVIEW_WINDOW_SECONDS,
) -> tuple[int, int]:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive.")
    now = int(time.time() * 1000) if now_ms is None else now_ms
    window_ms = window_seconds * 1000
    window_end_ms = (now // window_ms) * window_ms
    window_start_ms = window_end_ms - window_ms
    return window_start_ms, window_end_ms


def build_default_post_review_match_id(window_end_ms: int) -> str:
    window_end = datetime.fromtimestamp(window_end_ms / 1000, tz=UTC)
    return f"post-review-{window_end.strftime('%Y%m%d%H%M')}"


def _duration_ms(started_at_monotonic: float) -> int:
    return max(int((time.monotonic() - started_at_monotonic) * 1000), 0)


def _post_review_mode(config: PostReviewExecutionConfig) -> str:
    if config.fixture_jsonl_path is not None:
        return "fixture_dry_run" if config.dry_run else "fixture_apply"
    return "dry_run" if config.dry_run else "apply"


def _log_post_review_summary(
    *,
    config: PostReviewExecutionConfig,
    result: PostReviewCliResult,
) -> None:
    LOGGER.info(
        "post_review_summary mode=%s status=%s match_id=%s window_start_ms=%s "
        "window_end_ms=%s input_source=%s input_count=%s output_count=%s "
        "skipped_count=%s error_count=%s duration_ms=%s dry_run=%s",
        _post_review_mode(config),
        result.status,
        result.match_id,
        result.window_start_ms,
        result.window_end_ms,
        result.input_source,
        result.input_count,
        result.output_count,
        result.skipped_count,
        result.error_count,
        result.duration_ms,
        result.dry_run,
    )


def _parse_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    value = int(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be positive.")
    return value


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tm-ai-post-review")
    parser.add_argument("--match-id")
    parser.add_argument("--window-start-ms", type=int)
    parser.add_argument("--window-end-ms", type=int)
    parser.add_argument("--window-seconds", type=int, default=DEFAULT_POST_REVIEW_WINDOW_SECONDS)
    parser.add_argument("--limit", type=int, default=DEFAULT_POST_REVIEW_LIMIT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fixture-jsonl", type=Path)
    parser.add_argument("--use-raw-audit-fallback", action="store_true")
    parser.add_argument("--require-llm", action="store_true")
    parser.add_argument("--export-dir", type=Path)
    parser.add_argument("--session-analysis-max-workers", type=int, default=4)
    parser.add_argument("--review-max-workers", type=int, default=4)
    parser.add_argument(
        "--conflict-policy",
        choices=[policy.value for policy in PkConflictPolicy],
        default=PkConflictPolicy.UPSERT.value,
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
    )
    return parser.parse_args(argv)


def _config_from_args(args: argparse.Namespace) -> PostReviewExecutionConfig:
    if (args.window_start_ms is None) != (args.window_end_ms is None):
        raise ValueError("--window-start-ms and --window-end-ms must be provided together.")
    if args.window_start_ms is None or args.window_end_ms is None:
        window_start_ms, window_end_ms = resolve_default_post_review_window(
            window_seconds=args.window_seconds,
        )
    else:
        window_start_ms = args.window_start_ms
        window_end_ms = args.window_end_ms
    match_id = args.match_id or build_default_post_review_match_id(window_end_ms)
    return PostReviewExecutionConfig(
        match_id=match_id,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        limit=args.limit,
        dry_run=args.dry_run,
        conflict_policy=PkConflictPolicy(args.conflict_policy),
        use_raw_audit_fallback=args.use_raw_audit_fallback,
        fixture_jsonl_path=args.fixture_jsonl,
        require_llm=args.require_llm,
        export_dir=args.export_dir,
        session_analysis_max_workers=args.session_analysis_max_workers,
        review_max_workers=args.review_max_workers,
    )


if __name__ == "__main__":
    run_post_review()
