from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(title="TM Authz Adapter", version="v1")

AI_DEFENSE_URL = os.getenv("AI_DEFENSE_URL", "http://ai-defense:8000/evaluate")
AI_DEFENSE_TIMEOUT_MS = int(os.getenv("AI_DEFENSE_TIMEOUT_MS", "800"))
ADAPTER_POLICY_VERSION = os.getenv("ADAPTER_POLICY_VERSION", "adapter-v1")
CHECK_METHODS = {
    m.strip().upper()
    for m in os.getenv("TM_AUTHZ_CHECK_METHODS", "POST").split(",")
    if m.strip()
}
CHECK_PATH_PREFIXES = tuple(
    p.strip() for p in os.getenv("TM_AUTHZ_CHECK_PATH_PREFIXES", "/api/").split(",") if p.strip()
)


def _int_header(headers: dict[str, str], key: str, default: int = 0) -> int:
    raw = headers.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_header(headers: dict[str, str], key: str) -> bool:
    raw = headers.get(key, "false").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _needs_authz_check(method: str, path: str) -> bool:
    if method.upper() not in CHECK_METHODS:
        return False
    return any(path.startswith(prefix) for prefix in CHECK_PATH_PREFIXES)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "authz-adapter"}


@app.api_route("/check", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
@app.api_route("/check/{subpath:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def check(request: Request, subpath: str = "") -> Response:
    headers = {k.lower(): v for k, v in request.headers.items()}
    session_id = headers.get("x-session-id", "sess-anon")
    trace_id = headers.get("x-trace-id", "")
    fallback_path = f"/{subpath}" if subpath else "/"
    raw_path = headers.get("x-envoy-original-path") or headers.get(":path") or fallback_path
    if subpath:
        # ext_authz HTTP service usually calls /check/{original_path}; prefer reconstructed path.
        path = fallback_path
    elif raw_path.startswith("/check/"):
        path = "/" + raw_path[len("/check/") :]
    elif raw_path == "/check":
        path = "/"
    else:
        path = raw_path
    method = (
        headers.get("x-original-method")
        or headers.get("x-envoy-original-method")
        or headers.get(":method")
        or request.method
    )

    if not _needs_authz_check(method, path):
        return Response(
            status_code=200,
            headers={
                "x-defense-action": "none",
                "x-defense-policy-version": ADAPTER_POLICY_VERSION,
                "x-defense-check-skipped": "true",
            },
        )

    payload: dict[str, Any] = {
        "session_id": session_id,
        "trace_id": trace_id or None,
        "path": path,
        "method": method,
        "timestamp": int(time.time() * 1000),
        "headers": {
            "user-agent": headers.get("user-agent", ""),
            "x-forwarded-for": headers.get("x-forwarded-for", ""),
        },
        "flow_state": headers.get("x-flow-state") or None,
        "defense_tier": headers.get("x-defense-tier") or None,
        "challenge_fail_count": _int_header(headers, "x-challenge-fail-count", 0),
        "repetitive_pattern_count": _int_header(headers, "x-repetitive-pattern-count", 0),
        "token_mismatch": _bool_header(headers, "x-token-mismatch"),
    }

    try:
        async with httpx.AsyncClient(timeout=AI_DEFENSE_TIMEOUT_MS / 1000.0) as client:
            resp = await client.post(AI_DEFENSE_URL, json=payload)
            resp.raise_for_status()
            decision = resp.json()
    except Exception:
        # Fail-open for pilot stability.
        return Response(
            status_code=200,
            headers={
                "x-defense-action": "none",
                "x-defense-tier": "T0",
                "x-defense-policy-version": ADAPTER_POLICY_VERSION,
                "x-defense-adapter": "fail-open",
            },
        )

    allow = bool(decision.get("allow", True))
    headers_to_add = {
        str(k).lower(): str(v)
        for k, v in (decision.get("headers_to_add") or {}).items()
        if v is not None
    }

    if trace_id and "x-defense-trace-id" not in headers_to_add:
        headers_to_add["x-defense-trace-id"] = trace_id

    if allow:
        return Response(status_code=200, headers=headers_to_add)

    action = str(decision.get("action", "BLOCK")).upper()
    reason = str(decision.get("reason") or "BLOCKED")

    status_code = 403
    reason_code = "BLOCKED"
    message = "Denied by AI defense"

    if action == "CHALLENGE":
        status_code = 428
        reason_code = "CHALLENGE_REQUIRED"
        message = "Security challenge required"
    elif action == "GATE" or reason == "HIGH_VALUE_GATED":
        status_code = 428
        reason_code = "HIGH_VALUE_GATED"
        message = "High-value action gated"

    body = {
        "status": "FAIL",
        "reasonCode": reason_code,
        "message": message,
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers_to_add)
