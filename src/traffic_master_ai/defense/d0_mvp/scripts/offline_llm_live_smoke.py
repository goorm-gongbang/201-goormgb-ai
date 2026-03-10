from __future__ import annotations

import json
import sys
from typing import Any

from traffic_master_ai.defense.d0_mvp.optimizer.effect_evaluator import (
    OpenAICompatibleLLMCaller,
)


PROMPT = "Return exactly this JSON and nothing else: {\"status\":\"LIVE_OK\"}"


def main() -> int:
    caller = OpenAICompatibleLLMCaller()
    if not caller.is_configured:
        print(json.dumps({"ok": False, "error": "missing_api_key"}, ensure_ascii=False))
        return 1

    result = caller.call(
        system_prompt="You are a precise test assistant. Output exactly what the user requests.",
        user_input=PROMPT,
        max_output_tokens=160,
        timeout_ms=8000,
    )

    output: dict[str, Any] = {
        "ok": result.success,
        "latency_ms": result.latency_ms,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "error": result.error,
    }

    if result.output_text is not None:
        output["output_preview"] = result.output_text[:120]
        try:
            parsed = json.loads(result.output_text)
        except json.JSONDecodeError:
            output["schema_ok"] = False
        else:
            output["schema_ok"] = parsed == {"status": "LIVE_OK"}
    else:
        output["schema_ok"] = False

    print(json.dumps(output, ensure_ascii=False))
    return 0 if output["ok"] and output["schema_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
