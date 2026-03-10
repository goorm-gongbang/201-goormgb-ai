"""Offline effect evaluator with optional real OpenAI-compatible caller."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol

from ..core.constants import (
    EVAL_COOLDOWN_SECONDS,
    EVAL_MIN_EVENTS_TOTAL,
    EVAL_MIN_S3_EVENTS,
    EVAL_MIN_THROTTLE_EVENTS,
    EVAL_MIN_UNIQUE_SESSIONS,
    OFFLINE_LLM_CB_DISABLE_SECONDS,
    OFFLINE_LLM_CB_ERROR_RATE_DISABLE,
    OFFLINE_LLM_CB_TIMEOUT_RATE_DISABLE,
    OFFLINE_LLM_CB_WINDOW_SECONDS,
    OFFLINE_LLM_CONCURRENCY_LIMIT,
    OFFLINE_LLM_INPUT_MAX_BYTES,
    OFFLINE_LLM_MAX_CALLS_PER_RUN,
    OFFLINE_LLM_MAX_OUTPUT_TOKENS,
    OFFLINE_LLM_MODEL,
    OFFLINE_LLM_QPS_LIMIT,
    OFFLINE_LLM_MAX_RETRIES,
    OFFLINE_LLM_RETRY_BACKOFF_MS,
    OFFLINE_LLM_TIMEOUT_MS,
)
from ..policy.snapshot import PolicySnapshot
from .offline_llm_audit import append_offline_llm_audit
from .validator import (
    ProposalValidator,
    ValidationResult,
    proposal_base_values_from_policy,
)

logger = logging.getLogger(__name__)

_OFFLINE_LLM_ALLOWED_MODELS: frozenset[str] = frozenset(
    {
        "gpt-5-mini",
        "gpt-5.1-mini",
        "gpt-4.1-mini",
    }
)

_EFFECT_EVALUATOR_PROMPT = (
    "You are the Traffic-Master Defense Effect Evaluator (OFFLINE). "
    "Analyze aggregated decision_audit metrics and propose small, reversible policy parameter changes. "
    "Output valid JSON only."
)

_DEFAULT_ROLLBACK_CONDITIONS: tuple[str, ...] = (
    "s3_temp_lock_rate increases > +0.5%p",
    "block_rate increases > +0.3%p",
    "avg_throttle_delay_ms increases > +100ms",
    "s3_fail_rate increases > +1.0%p",
    "dedup_duplicate_rate spikes > +2.0%p",
    "internal_error spikes",
)


class LLMCaller(Protocol):
    def call(
        self,
        *,
        system_prompt: str,
        user_input: str,
        max_output_tokens: int,
        timeout_ms: int,
    ) -> "LLMCallResult":
        ...


@dataclass(slots=True, frozen=True)
class LLMCallResult:
    success: bool
    output_text: Optional[str] = None
    error: Optional[str] = None
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    is_timeout: bool = False


class StubLLMCaller:
    """Local no-op caller used when no real provider credentials exist."""

    def call(
        self,
        *,
        system_prompt: str,
        user_input: str,
        max_output_tokens: int = OFFLINE_LLM_MAX_OUTPUT_TOKENS,
        timeout_ms: int = OFFLINE_LLM_TIMEOUT_MS,
    ) -> LLMCallResult:
        del system_prompt, user_input, max_output_tokens, timeout_ms
        return LLMCallResult(success=True, output_text=None)


class OpenAICompatibleLLMCaller:
    """OpenAI-compatible REST caller.

    The endpoint is configurable so this also works with OpenAI-compatible gateways.
    """

    def __init__(
        self,
        *,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = OFFLINE_LLM_MODEL,
    ) -> None:
        endpoint_env = endpoint or os.environ.get("TM_OFFLINE_LLM_ENDPOINT")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if endpoint_env:
            self._endpoint = endpoint_env
        else:
            self._endpoint = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key or os.environ.get("TM_OFFLINE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self._model = model

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def call(
        self,
        *,
        system_prompt: str,
        user_input: str,
        max_output_tokens: int,
        timeout_ms: int,
    ) -> LLMCallResult:
        started_at = time.time()
        if not self._api_key:
            return LLMCallResult(success=False, error="missing_api_key")

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            "max_completion_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        raw: Optional[str] = None
        last_http_error: Optional[urllib.error.HTTPError] = None
        last_timeout = False
        last_error: Optional[Exception] = None
        for attempt in range(OFFLINE_LLM_MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=max(1.0, timeout_ms / 1000.0),
                ) as response:
                    raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                last_http_error = exc
                if not _should_retry_llm_http_error(exc) or attempt >= OFFLINE_LLM_MAX_RETRIES:
                    break
                _sleep_ms(OFFLINE_LLM_RETRY_BACKOFF_MS)
            except TimeoutError as exc:
                last_error = exc
                last_timeout = True
                if attempt >= OFFLINE_LLM_MAX_RETRIES:
                    break
                _sleep_ms(OFFLINE_LLM_RETRY_BACKOFF_MS)
            except Exception as exc:
                last_error = exc
                last_timeout = exc.__class__.__name__.lower() == "timeouterror"
                if not last_timeout or attempt >= OFFLINE_LLM_MAX_RETRIES:
                    break
                _sleep_ms(OFFLINE_LLM_RETRY_BACKOFF_MS)

        if raw is None:
            latency_ms = int((time.time() - started_at) * 1000)
            if last_http_error is not None:
                try:
                    body = last_http_error.read().decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                error = f"http_{last_http_error.code}"
                if body:
                    error = f"{error}:{body[:400]}"
                return LLMCallResult(success=False, error=error, latency_ms=latency_ms)
            if last_timeout:
                return LLMCallResult(success=False, error="timeout", latency_ms=latency_ms, is_timeout=True)
            error_name = str(last_error.__class__.__name__) if last_error is not None else "unknown_error"
            return LLMCallResult(success=False, error=error_name, latency_ms=latency_ms, is_timeout=last_timeout)

        latency_ms = int((time.time() - started_at) * 1000)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return LLMCallResult(success=False, error="invalid_json", latency_ms=latency_ms)

        output_text = _extract_output_text(parsed)
        usage = parsed.get("usage") if isinstance(parsed, Mapping) else None
        tokens_in = int(_mapping_get(usage, "prompt_tokens", default=0) or 0)
        tokens_out = int(_mapping_get(usage, "completion_tokens", default=0) or 0)
        return LLMCallResult(
            success=output_text is not None,
            output_text=output_text,
            error=None if output_text is not None else "missing_output_text",
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )


class _OfflineLLMBudgetGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: deque[float] = deque()
        self._inflight = 0

    def try_acquire(self) -> Optional[str]:
        now = time.time()
        with self._lock:
            while self._calls and now - self._calls[0] >= 1.0:
                self._calls.popleft()
            if len(self._calls) >= OFFLINE_LLM_QPS_LIMIT:
                return "qps_limit"
            if self._inflight >= OFFLINE_LLM_CONCURRENCY_LIMIT:
                return "concurrency_limit"
            self._calls.append(now)
            self._inflight += 1
        return None

    def release(self) -> None:
        with self._lock:
            self._inflight = max(0, self._inflight - 1)


_OFFLINE_LLM_BUDGET_GATE = _OfflineLLMBudgetGate()


@dataclass
class CircuitBreaker:
    window_seconds: int = OFFLINE_LLM_CB_WINDOW_SECONDS
    timeout_rate_threshold: float = OFFLINE_LLM_CB_TIMEOUT_RATE_DISABLE
    error_rate_threshold: float = OFFLINE_LLM_CB_ERROR_RATE_DISABLE
    disable_duration_seconds: int = OFFLINE_LLM_CB_DISABLE_SECONDS

    def __post_init__(self) -> None:
        self._call_count = 0
        self._timeout_count = 0
        self._error_count = 0
        self._window_start_ms = 0
        self._disabled_until_ms = 0

    @property
    def is_open(self) -> bool:
        now = _now_ms()
        if self._disabled_until_ms > 0 and now < self._disabled_until_ms:
            return True
        if self._disabled_until_ms > 0 and now >= self._disabled_until_ms:
            self._reset()
        return False

    def record_success(self) -> None:
        self._ensure_window()
        self._call_count += 1

    def record_timeout(self) -> None:
        self._ensure_window()
        self._call_count += 1
        self._timeout_count += 1
        self._check_thresholds()

    def record_error(self) -> None:
        self._ensure_window()
        self._call_count += 1
        self._error_count += 1
        self._check_thresholds()

    def _ensure_window(self) -> None:
        now = _now_ms()
        if self._window_start_ms == 0:
            self._window_start_ms = now
        elif now - self._window_start_ms > self.window_seconds * 1000:
            self._reset()
            self._window_start_ms = now

    def _check_thresholds(self) -> None:
        if self._call_count < 3:
            return
        timeout_rate = self._timeout_count / self._call_count
        error_rate = self._error_count / self._call_count
        if timeout_rate >= self.timeout_rate_threshold or error_rate >= self.error_rate_threshold:
            self._disabled_until_ms = _now_ms() + (self.disable_duration_seconds * 1000)
            logger.warning(
                "Circuit breaker opened: timeout_rate=%.2f error_rate=%.2f",
                timeout_rate,
                error_rate,
            )

    def _reset(self) -> None:
        self._call_count = 0
        self._timeout_count = 0
        self._error_count = 0
        self._window_start_ms = 0
        self._disabled_until_ms = 0


@dataclass
class EffectEvaluator:
    validator: ProposalValidator
    max_calls_per_run: int = OFFLINE_LLM_MAX_CALLS_PER_RUN
    min_events_total: int = EVAL_MIN_EVENTS_TOTAL
    min_unique_sessions: int = EVAL_MIN_UNIQUE_SESSIONS
    min_throttle_events: int = EVAL_MIN_THROTTLE_EVENTS
    min_s3_events: int = EVAL_MIN_S3_EVENTS
    cooldown_seconds: int = EVAL_COOLDOWN_SECONDS
    llm_caller: Optional[LLMCaller] = None
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def __post_init__(self) -> None:
        self._calls_made = 0
        self._last_run_at_ms = 0
        if self.llm_caller is None:
            self.llm_caller = build_default_llm_caller()

    def should_trigger(self, metrics_snapshot: Mapping[str, Any], now_ms: Optional[int] = None) -> bool:
        now = now_ms or _now_ms()
        if self._calls_made >= self.max_calls_per_run:
            return False
        if self._last_run_at_ms and now - self._last_run_at_ms < self.cooldown_seconds * 1000:
            return False
        if self.circuit_breaker.is_open:
            return False
        total_events = int(metrics_snapshot.get("events_total", 0))
        unique_sessions = int(metrics_snapshot.get("unique_sessions", 0))
        event_counts = metrics_snapshot.get("event_counts_by_type", {})
        throttle_events = _mapping_int(event_counts, "DEF_THROTTLE_APPLIED")
        s3_events = _mapping_int(event_counts, "S3_CHALLENGE_RESULT")
        return (
            total_events >= self.min_events_total
            and unique_sessions >= self.min_unique_sessions
            and throttle_events >= self.min_throttle_events
            and s3_events >= self.min_s3_events
        )

    def propose(
        self,
        *,
        metrics_snapshot: Mapping[str, Any],
        base_policy_version: str,
        base_policy: Optional[PolicySnapshot] = None,
        now_ms: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        now = now_ms or _now_ms()
        if not self.should_trigger(metrics_snapshot, now):
            append_offline_llm_audit(
                "OFFLINE_LLM_SKIPPED",
                {
                    "offline_llm": {
                        "model": OFFLINE_LLM_MODEL,
                        "skipped_reason": "trigger_guard",
                        "base_policy_version": base_policy_version,
                    }
                },
            )
            return None

        self._calls_made += 1
        self._last_run_at_ms = now
        base_values = (
            proposal_base_values_from_policy(base_policy)
            if base_policy is not None
            else None
        )

        rule_based = _rule_based_proposal(
            metrics_snapshot,
            base_policy_version,
            validator=self.validator,
            base_values=base_values,
        )
        if rule_based is not None:
            append_offline_llm_audit(
                "OFFLINE_LLM_PATCH_PROPOSED",
                {
                    "offline_llm": {
                        "model": OFFLINE_LLM_MODEL,
                        "skipped_reason": "rule_based_primary",
                        "proposal_id": rule_based["proposal_id"],
                        "base_policy_version": base_policy_version,
                        "patches_count": len(rule_based["patches"]),
                        "confidence": rule_based.get("confidence"),
                    }
                },
            )
            return rule_based

        prepared_input = _build_llm_input(metrics_snapshot, base_policy_version)
        input_text = prepared_input["input_text"]
        input_truncated = prepared_input["input_truncated"]

        budget_reason = try_acquire_offline_llm_budget()
        if budget_reason is not None:
            append_offline_llm_audit(
                "OFFLINE_LLM_SKIPPED",
                {
                    "offline_llm": {
                        "model": OFFLINE_LLM_MODEL,
                        "skipped_reason": budget_reason,
                        "input_truncated": input_truncated,
                        "base_policy_version": base_policy_version,
                    }
                },
            )
            return None

        append_offline_llm_audit(
            "OFFLINE_LLM_RUN_STARTED",
            {
                "offline_llm": {
                    "model": OFFLINE_LLM_MODEL,
                    "input_truncated": input_truncated,
                    "base_policy_version": base_policy_version,
                }
            },
        )
        try:
            result = self.llm_caller.call(
                system_prompt=_EFFECT_EVALUATOR_PROMPT,
                user_input=input_text,
                max_output_tokens=OFFLINE_LLM_MAX_OUTPUT_TOKENS,
                timeout_ms=OFFLINE_LLM_TIMEOUT_MS,
            )
        finally:
            release_offline_llm_budget()

        _record_circuit_breaker(self.circuit_breaker, result)
        append_offline_llm_audit(
            "OFFLINE_LLM_RUN_FINISHED",
            {
                "offline_llm": {
                    "model": OFFLINE_LLM_MODEL,
                    "latency_ms": result.latency_ms,
                    "tokens_in": result.tokens_in,
                    "tokens_out": result.tokens_out,
                    "input_truncated": input_truncated,
                    "base_policy_version": base_policy_version,
                    "skipped_reason": None if result.success else result.error,
                }
            },
        )
        if not result.success or not result.output_text:
            return None

        try:
            proposal = json.loads(result.output_text)
        except json.JSONDecodeError:
            append_offline_llm_audit(
                "OFFLINE_LLM_SKIPPED",
                {
                    "offline_llm": {
                        "model": OFFLINE_LLM_MODEL,
                        "skipped_reason": "schema_invalid",
                        "input_truncated": input_truncated,
                        "base_policy_version": base_policy_version,
                    }
                },
            )
            return None

        validated: ValidationResult = self.validator.validate(
            proposal,
            expected_base_policy_version=base_policy_version,
            base_values=base_values,
        )
        if not validated.valid:
            append_offline_llm_audit(
                "OFFLINE_LLM_SKIPPED",
                {
                    "offline_llm": {
                        "model": OFFLINE_LLM_MODEL,
                        "skipped_reason": "schema_invalid",
                        "input_truncated": input_truncated,
                        "base_policy_version": base_policy_version,
                    }
                },
            )
            return None

        sanitized = validated.sanitized_proposal
        append_offline_llm_audit(
            "OFFLINE_LLM_PATCH_PROPOSED",
            {
                "offline_llm": {
                    "model": OFFLINE_LLM_MODEL,
                    "proposal_id": sanitized.get("proposal_id"),
                    "base_policy_version": sanitized.get("base_policy_version"),
                    "patches_count": len(sanitized.get("patches", [])),
                    "confidence": sanitized.get("confidence"),
                    "input_truncated": input_truncated,
                }
            },
        )
        return sanitized



def build_default_llm_caller() -> LLMCaller:
    if OFFLINE_LLM_MODEL not in _OFFLINE_LLM_ALLOWED_MODELS:
        logger.warning(
            "Offline LLM model '%s' is not in allowlist; using StubLLMCaller.",
            OFFLINE_LLM_MODEL,
        )
        return StubLLMCaller()
    caller = OpenAICompatibleLLMCaller()
    if caller.is_configured:
        return caller
    return StubLLMCaller()



def try_acquire_offline_llm_budget() -> Optional[str]:
    return _OFFLINE_LLM_BUDGET_GATE.try_acquire()



def release_offline_llm_budget() -> None:
    _OFFLINE_LLM_BUDGET_GATE.release()



def _record_circuit_breaker(circuit_breaker: CircuitBreaker, result: LLMCallResult) -> None:
    if result.success:
        circuit_breaker.record_success()
    elif result.is_timeout:
        circuit_breaker.record_timeout()
    else:
        circuit_breaker.record_error()



def _rule_based_proposal(
    metrics_snapshot: Mapping[str, Any],
    base_policy_version: str,
    *,
    validator: ProposalValidator,
    base_values: Optional[Mapping[str, float]] = None,
) -> Optional[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    s3_lock_rate = float(metrics_snapshot.get("s3_temp_lock_rate", 0.0))
    avg_throttle_delay = float(metrics_snapshot.get("avg_throttle_delay_ms", 0.0))
    block_rate = float(metrics_snapshot.get("block_rate", 0.0))
    s3_fail_rate = float(metrics_snapshot.get("s3_fail_rate", 0.0))

    if s3_lock_rate > 0.020:
        patches.append(
            {
                "path": "challenge.halt_seconds",
                "op": "dec",
                "value": 5,
                "why": "s3 temporary lock rate above baseline",
            }
        )
    if avg_throttle_delay > 260:
        patches.append(
            {
                "path": "planner.throttle_delay_ms.T2",
                "op": "dec",
                "value": 20,
                "why": "average throttle delay too high",
            }
        )
    if block_rate > 0.015 and s3_fail_rate > 0.08:
        patches.append(
            {
                "path": "risk.alpha",
                "op": "dec",
                "value": 0.02,
                "why": "reduce short-term score volatility under elevated block+s3 fail",
            }
        )
    if not patches:
        return None

    proposal = {
        "proposal_id": f"proposal-{uuid.uuid4().hex[:12]}",
        "base_policy_version": base_policy_version,
        "patches": patches,
        "rationale": "Rule-based offline proposal generated from decision_audit aggregates.",
        "confidence": 0.58,
        "rollback_conditions": list(_DEFAULT_ROLLBACK_CONDITIONS),
        "notes": "MVP proposal-only mode; manual approval required.",
    }
    validated: ValidationResult = validator.validate(
        proposal,
        expected_base_policy_version=base_policy_version,
        base_values=base_values,
    )
    if not validated.valid:
        return None
    return validated.sanitized_proposal



def _build_llm_input(metrics_snapshot: Mapping[str, Any], base_policy_version: str) -> dict[str, Any]:
    payload = {
        "window_meta": {
            "window_start_ms": metrics_snapshot.get("window_start_ms"),
            "window_end_ms": metrics_snapshot.get("window_end_ms"),
            "policy_version": base_policy_version,
        },
        "traffic": {
            "unique_sessions": metrics_snapshot.get("unique_sessions"),
            "unique_traces": metrics_snapshot.get("unique_traces"),
            "event_counts_by_type": metrics_snapshot.get("event_counts_by_type", {}),
        },
        "defense_outcomes": {
            "tier_distribution": metrics_snapshot.get("tier_distribution", {}),
            "action_distribution": metrics_snapshot.get("action_distribution", {}),
            "block_rate": metrics_snapshot.get("block_rate"),
            "require_s3_rate": metrics_snapshot.get("require_s3_rate"),
            "throttle_applied_rate": metrics_snapshot.get("throttle_applied_rate"),
            "avg_throttle_delay_ms": metrics_snapshot.get("avg_throttle_delay_ms"),
            "s3_pass_rate": metrics_snapshot.get("s3_pass_rate"),
            "s3_fail_rate": metrics_snapshot.get("s3_fail_rate"),
            "s3_temp_lock_rate": metrics_snapshot.get("s3_temp_lock_rate"),
        },
        "integrity": {
            "dedup_duplicate_rate": metrics_snapshot.get("dedup_duplicate_rate"),
            "missing_feature_rate": metrics_snapshot.get("missing_feature_rate"),
        },
        "allowlist": [
            "risk.alpha",
            "tier.thresholds.T0_max",
            "tier.thresholds.T1_max",
            "tier.thresholds.T2_max",
            "tier.hysteresis.margin",
            "risk.probation_seconds",
            "planner.throttle_delay_ms.T1",
            "planner.throttle_delay_ms.T2",
            "challenge.max_attempts",
            "challenge.cooldown_ms.first",
            "challenge.cooldown_ms.second",
            "challenge.halt_seconds",
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    truncated = False
    if len(encoded.encode("utf-8")) > OFFLINE_LLM_INPUT_MAX_BYTES:
        truncated = True
        payload["traffic"]["event_counts_by_type"] = {}
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return {"input_text": encoded, "input_truncated": truncated}



def _extract_output_text(parsed: Mapping[str, Any]) -> Optional[str]:
    choices = parsed.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, Mapping):
            message = first.get("message")
            if isinstance(message, Mapping):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = [str(item.get("text", "")) for item in content if isinstance(item, Mapping)]
                    text = "".join(parts).strip()
                    if text:
                        return text
    output_text = parsed.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text
    output = parsed.get("output")
    if isinstance(output, list) and output:
        first = output[0]
        if isinstance(first, Mapping):
            content = first.get("content")
            if isinstance(content, list):
                texts = [str(item.get("text", "")) for item in content if isinstance(item, Mapping)]
                text = "".join(texts).strip()
                if text:
                    return text
    return None



def _mapping_get(data: Any, key: str, *, default: Any = None) -> Any:
    if not isinstance(data, Mapping):
        return default
    return data.get(key, default)


def _mapping_int(data: Any, key: str) -> int:
    try:
        return int(_mapping_get(data, key, default=0) or 0)
    except (TypeError, ValueError):
        return 0


def _should_retry_llm_http_error(exc: urllib.error.HTTPError) -> bool:
    return 500 <= int(exc.code) < 600


def _sleep_ms(delay_ms: int) -> None:
    if delay_ms <= 0:
        return
    time.sleep(delay_ms / 1000.0)



def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = [
    "EffectEvaluator",
    "LLMCaller",
    "LLMCallResult",
    "StubLLMCaller",
    "OpenAICompatibleLLMCaller",
    "CircuitBreaker",
    "build_default_llm_caller",
    "try_acquire_offline_llm_budget",
    "release_offline_llm_budget",
]
