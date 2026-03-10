"""Offline audit summarizer with optional real LLM path."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from ..core.constants import (
    OFFLINE_AUDIT_SUMMARY_FILENAME,
    OFFLINE_LLM_INPUT_MAX_BYTES,
    OFFLINE_LLM_MAX_OUTPUT_TOKENS,
    OFFLINE_LLM_MAX_SAMPLE_TRACES,
    OFFLINE_LLM_MODEL,
    OFFLINE_LLM_TIMEOUT_MS,
    SUM_COOLDOWN_SECONDS,
    SUM_MIN_EVENTS_TOTAL,
)
from .effect_evaluator import (
    LLMCaller,
    build_default_llm_caller,
    release_offline_llm_budget,
    try_acquire_offline_llm_budget,
)
from .offline_llm_audit import append_offline_llm_audit

_SUMMARIZER_PROMPT = (
    "Summarize the given aggregated defense audit metrics for engineers. "
    "Keep it concise and factual. Output markdown."
)


@dataclass(slots=True, frozen=True)
class AuditSummaryResult:
    report_id: str
    generated_at_ms: int
    summary_text: str
    metrics_snapshot: dict[str, Any]
    sampled_traces: list[dict[str, Any]]
    input_truncated: bool


class AuditSummarizer:
    def __init__(
        self,
        *,
        file_path: str = OFFLINE_AUDIT_SUMMARY_FILENAME,
        min_events_total: int = SUM_MIN_EVENTS_TOTAL,
        cooldown_seconds: int = SUM_COOLDOWN_SECONDS,
        max_input_bytes: int = OFFLINE_LLM_INPUT_MAX_BYTES,
        max_sample_traces: int = OFFLINE_LLM_MAX_SAMPLE_TRACES,
        llm_caller: Optional[LLMCaller] = None,
    ) -> None:
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._min_events_total = min_events_total
        self._cooldown_seconds = cooldown_seconds
        self._max_input_bytes = max_input_bytes
        self._max_sample_traces = max_sample_traces
        self._llm_caller = llm_caller or build_default_llm_caller()
        self._last_run_at_ms = 0

    def should_trigger(self, metrics_snapshot: Mapping[str, Any], now_ms: Optional[int] = None) -> bool:
        now = now_ms or _now_ms()
        if self._last_run_at_ms and now - self._last_run_at_ms < self._cooldown_seconds * 1000:
            return False
        return int(metrics_snapshot.get("events_total", 0)) >= self._min_events_total

    def summarize(
        self,
        *,
        metrics_snapshot: Mapping[str, Any],
        sampled_traces: list[dict[str, Any]],
        now_ms: Optional[int] = None,
    ) -> Optional[AuditSummaryResult]:
        now = now_ms or _now_ms()
        if not self.should_trigger(metrics_snapshot, now):
            append_offline_llm_audit(
                "OFFLINE_LLM_SKIPPED",
                {"offline_llm": {"model": OFFLINE_LLM_MODEL, "skipped_reason": "summary_trigger_guard"}},
            )
            return None
        self._last_run_at_ms = now

        safe_traces = sampled_traces[: self._max_sample_traces]
        payload, truncated = _build_summary_input(
            metrics_snapshot=dict(metrics_snapshot),
            sampled_traces=safe_traces,
            max_input_bytes=self._max_input_bytes,
        )
        summary_text = _render_summary(metrics_snapshot=dict(metrics_snapshot), sampled_traces=payload["sampled_traces"])

        budget_reason = try_acquire_offline_llm_budget()
        if budget_reason is not None:
            append_offline_llm_audit(
                "OFFLINE_LLM_SKIPPED",
                {"offline_llm": {"model": OFFLINE_LLM_MODEL, "skipped_reason": budget_reason, "input_truncated": truncated}},
            )
        else:
            append_offline_llm_audit(
                "OFFLINE_LLM_RUN_STARTED",
                {"offline_llm": {"model": OFFLINE_LLM_MODEL, "input_truncated": truncated}},
            )
            try:
                result = self._llm_caller.call(
                    system_prompt=_SUMMARIZER_PROMPT,
                    user_input=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    max_output_tokens=OFFLINE_LLM_MAX_OUTPUT_TOKENS,
                    timeout_ms=OFFLINE_LLM_TIMEOUT_MS,
                )
            finally:
                release_offline_llm_budget()
            append_offline_llm_audit(
                "OFFLINE_LLM_RUN_FINISHED",
                {
                    "offline_llm": {
                        "model": OFFLINE_LLM_MODEL,
                        "latency_ms": result.latency_ms,
                        "tokens_in": result.tokens_in,
                        "tokens_out": result.tokens_out,
                        "input_truncated": truncated,
                        "skipped_reason": None if result.success else result.error,
                    }
                },
            )
            if result.success and result.output_text:
                summary_text = result.output_text.strip()

        result = AuditSummaryResult(
            report_id=f"summary-{uuid.uuid4().hex[:12]}",
            generated_at_ms=now,
            summary_text=summary_text,
            metrics_snapshot=dict(metrics_snapshot),
            sampled_traces=list(payload["sampled_traces"]),
            input_truncated=truncated,
        )
        self._append(result)
        return result

    def read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
        return out

    def latest(self) -> Optional[dict[str, Any]]:
        reports = self.read_all()
        return reports[-1] if reports else None

    def _append(self, result: AuditSummaryResult) -> None:
        row = {
            "reportId": result.report_id,
            "generatedAtMs": result.generated_at_ms,
            "summaryText": result.summary_text,
            "metricsSnapshot": result.metrics_snapshot,
            "sampledTraces": result.sampled_traces,
            "inputTruncated": result.input_truncated,
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")



def _build_summary_input(
    *,
    metrics_snapshot: dict[str, Any],
    sampled_traces: list[dict[str, Any]],
    max_input_bytes: int,
) -> tuple[dict[str, Any], bool]:
    payload = {
        "window_start_ms": metrics_snapshot.get("window_start_ms"),
        "window_end_ms": metrics_snapshot.get("window_end_ms"),
        "policy_version": metrics_snapshot.get("policy_version"),
        "tier_distribution": metrics_snapshot.get("tier_distribution", {}),
        "action_distribution": metrics_snapshot.get("action_distribution", {}),
        "s3_pass_rate": metrics_snapshot.get("s3_pass_rate"),
        "s3_temp_lock_rate": metrics_snapshot.get("s3_temp_lock_rate"),
        "block_rate": metrics_snapshot.get("block_rate"),
        "avg_throttle_delay_ms": metrics_snapshot.get("avg_throttle_delay_ms"),
        "sampled_traces": sampled_traces,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    truncated = False
    if len(encoded.encode("utf-8")) > max_input_bytes:
        truncated = True
        payload["sampled_traces"] = sampled_traces[: min(len(sampled_traces), 10)]
    return payload, truncated



def _render_summary(metrics_snapshot: Mapping[str, Any], sampled_traces: list[dict[str, Any]]) -> str:
    block_rate = metrics_snapshot.get("block_rate", 0.0)
    throttle_delay = metrics_snapshot.get("avg_throttle_delay_ms", 0.0)
    s3_lock_rate = metrics_snapshot.get("s3_temp_lock_rate", 0.0)
    event_count = metrics_snapshot.get("events_total", 0)
    trace_examples = ", ".join(str(item.get("traceId", "")) for item in sampled_traces[:5] if item.get("traceId"))
    lines = [
        "# Defense Audit Summary",
        f"- events_total: {event_count}",
        f"- block_rate: {block_rate}",
        f"- avg_throttle_delay_ms: {throttle_delay}",
        f"- s3_temp_lock_rate: {s3_lock_rate}",
    ]
    if trace_examples:
        lines.append(f"- sample_traces: {trace_examples}")
    if block_rate and float(block_rate) > 0.02:
        lines.append("- block_rate is elevated relative to the MVP baseline")
    if throttle_delay and float(throttle_delay) > 260:
        lines.append("- throttle delay is elevated and should be reviewed")
    if s3_lock_rate and float(s3_lock_rate) > 0.02:
        lines.append("- temporary S3 lock rate is elevated")
    return "\n".join(lines)



def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["AuditSummarizer", "AuditSummaryResult"]
