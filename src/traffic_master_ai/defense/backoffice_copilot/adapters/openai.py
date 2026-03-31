"""OpenAI-compatible LLM Adapters for Backoffice Copilot.

Uses standard library urllib to avoid heavy external dependencies.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Mapping

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
    endpoint: str | None = None,
    timeout_ms: int = 15000,
) -> Any:
    """Internal helper to make the POST request and parse the JSON completion."""
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

    try:
        with urllib.request.urlopen(request, timeout=max(1.0, timeout_ms / 1000.0)) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ConnectionError(f"HTTP request failed: {exc}") from exc
    except TimeoutError as exc:
        raise TimeoutError(f"HTTP request timed out: {exc}") from exc

    try:
        parsed_response = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON received from OpenAI API.") from exc

    choices = parsed_response.get("choices", [])
    if not choices:
        raise ValueError("No choices returned in OpenAI response.")

    message = choices[0].get("message", {})
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("Content text missing or invalid in OpenAI response.")

    try:
        structured_output = json.loads(content)
        return structured_output
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response content is not valid JSON.") from exc


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

        return _call_openai_chat_completions(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_input=user_input_str,
            endpoint=endpoint,
            timeout_ms=timeout_ms,
        )

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
            "Line 1: Summarize total candidates and number of suspicious sessions.\n"
            "Line 2: Summarize top signals or mitigation events (like throttle or block).\n"
            "Line 3: Recommend overall status or outline raw fallback needs if applicable."
        )

        user_input_str = json.dumps(summary_input, ensure_ascii=False)

        return _call_openai_chat_completions(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_input=user_input_str,
            endpoint=endpoint,
            timeout_ms=timeout_ms,
        )

    return _adapter

__all__ = ["build_openai_review_adapter", "build_openai_summary_adapter"]
