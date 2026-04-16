"""OpenAI-compatible LLM Adapters for Backoffice Copilot.

Uses standard library urllib to avoid heavy external dependencies.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Mapping

from ...langsmith_support import current_tm_ai_environment, start_langsmith_llm_trace
from ..core.models import LlmReviewInput
from ..review.executor import LlmReviewAdapter
from ..summary.window_summary import WindowSummaryAdapter

_DEFAULT_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _call_openai_chat_completions(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_input: str,
    trace_name: str,
    trace_metadata: Mapping[str, object],
    endpoint: str | None = None,
    timeout_ms: int = 15000,
) -> tuple[Any, dict[str, str]]:
    """Internal helper to make the POST request and parse the JSON completion.

    Returns (structured_output, langsmith_link) where langsmith_link is a dict
    with optional 'runId' and 'traceUrl' keys for observability payload injection.
    """
    url = endpoint or os.environ.get("OPENAI_BASE_URL", _DEFAULT_OPENAI_URL).rstrip("/")
    if url.endswith(".com/v1"):
        url += "/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    
    if not api_key:
        raise ValueError("missing API key for OpenAI Adapter")
        
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    trace_inputs = {
        "model": model,
        "messages": payload["messages"],
    }
    with start_langsmith_llm_trace(
        name=trace_name,
        model_name=model,
        inputs=trace_inputs,
        metadata=trace_metadata,
        tags=("backoffice_copilot", str(trace_metadata.get("agent_step_name", trace_name))),
    ) as trace:
        try:
            with urllib.request.urlopen(request, timeout=max(1.0, timeout_ms / 1000.0)) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            trace.record_error(exc)
            raise ConnectionError(f"HTTP request failed: {exc}") from exc
        except TimeoutError as exc:
            trace.record_error(exc)
            raise TimeoutError(f"HTTP request timed out: {exc}") from exc

        try:
            parsed_response = json.loads(raw)
        except json.JSONDecodeError as exc:
            trace.record_error(exc)
            raise ValueError("Invalid JSON received from OpenAI API.") from exc

        usage_metadata = _extract_usage_metadata(parsed_response)
        trace.record_usage_metadata(usage_metadata)
        trace.record_output(parsed_response)

        langsmith_link = trace.get_langsmith_link()

        choices = parsed_response.get("choices", [])
        if not choices:
            error = ValueError("No choices returned in OpenAI response.")
            trace.record_error(error)
            raise error

        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str):
            error = ValueError("Content text missing or invalid in OpenAI response.")
            trace.record_error(error)
            raise error

        try:
            structured_output = json.loads(content)
            return structured_output, langsmith_link
        except json.JSONDecodeError as exc:
            trace.record_error(exc)
            raise ValueError("LLM response content is not valid JSON.") from exc


def _extract_usage_metadata(parsed_response: Mapping[str, Any]) -> dict[str, int]:
    usage = parsed_response.get("usage")
    if not isinstance(usage, Mapping):
        return {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    if input_tokens <= 0 and output_tokens <= 0 and total_tokens <= 0:
        return {}
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def build_openai_review_adapter(
    api_key: str,
    model: str,
    endpoint: str | None = None,
    timeout_ms: int = 15000,
) -> LlmReviewAdapter:
    """Create an LlmReviewAdapter bound to the OpenAI API."""

    def _adapter(llm_input: LlmReviewInput) -> object:
        system_prompt = (
            "You are a security review AI. "
            "Analyze the provided session context and determine if the activity is 'NORMAL' or 'SUSPICIOUS'. "
            "You must output valid JSON containing exactly two keys: "
            "'review_result' (either 'NORMAL' or 'SUSPICIOUS') and 'evidence_summary' (a brief explanation)."
        )

        user_input_dict = {
            "match_id": llm_input.match_id,
            "session_id": llm_input.session_analysis.session_id,
            "signals": llm_input.session_analysis.suspicious_signals,
            "timeline": llm_input.session_analysis.timeline_summary,
            "flow_state": llm_input.session_analysis.latest_flow_state,
            "action": llm_input.session_analysis.latest_action,
        }
        user_input_str = json.dumps(user_input_dict, ensure_ascii=False)
        trace_metadata = {
            "session_id": llm_input.session_analysis.session_id,
            "thread_id": llm_input.match_id,
            "feature_name": "backoffice_copilot",
            "agent_step_name": "review_session",
            "environment": current_tm_ai_environment(),
            "match_id": llm_input.match_id,
            "window_start_ms": llm_input.window_start_ms,
            "window_end_ms": llm_input.window_end_ms,
            "owner_team": "TM_AI",
        }

        result, langsmith_link = _call_openai_chat_completions(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_input=user_input_str,
            trace_name="backoffice_copilot.review_session",
            trace_metadata=trace_metadata,
            endpoint=endpoint,
            timeout_ms=timeout_ms,
        )
        if langsmith_link and isinstance(result, dict):
            result["langsmith"] = langsmith_link
        return result

    return _adapter


def build_openai_summary_adapter(
    api_key: str,
    model: str,
    endpoint: str | None = None,
    timeout_ms: int = 15000,
) -> WindowSummaryAdapter:
    """Create a WindowSummaryAdapter bound to the OpenAI API."""

    def _adapter(summary_input: Mapping[str, object]) -> object:
        system_prompt = (
            "You are a Traffic-Master defense analyst AI. "
            "Generate a 3-line summary of the current operational window metrics. "
            "You must output exactly valid JSON with one key: 'summary_text', which maps to an array of exactly 3 strings.\n"
            "Line 1: State total candidate sessions reviewed, the suspicious count, and the normal count.\n"
            "Line 2: Cite concrete mitigation evidence — use throttle_total (total throttle events applied), "
            "challenge_fail_total (total challenge failures), and tier_breakdown (tier distribution across sessions); "
            "name the dominant tier and highlight any T2 or T3 presence.\n"
            "Line 3: Operational assessment — reference action_breakdown to describe which actions were applied and how often; "
            "note sessions still needing raw context (needs_raw_fallback_count) and characterize the overall window risk level."
        )

        user_input_str = json.dumps(summary_input, ensure_ascii=False)
        match_id = str(summary_input.get("match_id") or "")
        trace_metadata = {
            "thread_id": match_id,
            "feature_name": "backoffice_copilot",
            "agent_step_name": "summarize_window",
            "environment": current_tm_ai_environment(),
            "match_id": match_id,
            "window_start_ms": summary_input.get("window_start_ms"),
            "window_end_ms": summary_input.get("window_end_ms"),
            "owner_team": "TM_AI",
        }

        result, langsmith_link = _call_openai_chat_completions(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_input=user_input_str,
            trace_name="backoffice_copilot.summarize_window",
            trace_metadata=trace_metadata,
            endpoint=endpoint,
            timeout_ms=timeout_ms,
        )
        if langsmith_link and isinstance(result, dict):
            result["langsmith"] = langsmith_link
        return result

    return _adapter

__all__ = ["build_openai_review_adapter", "build_openai_summary_adapter"]
