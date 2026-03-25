"""
Envoy ext_authz gRPC Adapter for AI Defense

This adapter implements the Envoy ext_authz v3 gRPC protocol,
forwarding authorization checks to the AI Defense service.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from concurrent import futures
from typing import Any

import grpc
from grpc_reflection.v1alpha import reflection

# Add protos to path for generated code
sys.path.insert(0, os.path.dirname(__file__))

# Import generated protobuf code (will be generated from proto file)
import ext_authz_pb2
import ext_authz_pb2_grpc

import httpx

# Configuration
AI_DEFENSE_URL = os.getenv("AI_DEFENSE_URL", "http://ai-defense:8000/evaluate")
AI_DEFENSE_TIMEOUT_SEC = float(os.getenv("AI_DEFENSE_TIMEOUT_SEC", "0.8"))
ADAPTER_POLICY_VERSION = os.getenv("ADAPTER_POLICY_VERSION", "grpc-adapter-v1")
GRPC_PORT = int(os.getenv("GRPC_PORT", "9001"))
GRPC_WORKERS = int(os.getenv("GRPC_WORKERS", "10"))

# Methods and paths to check
CHECK_METHODS = {
    m.strip().upper()
    for m in os.getenv("TM_AUTHZ_CHECK_METHODS", "POST,GET").split(",")
    if m.strip()
}
CHECK_PATH_PREFIXES = tuple(
    p.strip()
    for p in os.getenv(
        "TM_AUTHZ_CHECK_PATH_PREFIXES",
        "/queue/,/seat/"
    ).split(",")
    if p.strip()
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("authz-adapter-grpc")


def _needs_authz_check(method: str, path: str) -> bool:
    """Determine if this request needs authorization check."""
    if method.upper() not in CHECK_METHODS:
        return False
    return any(path.startswith(prefix) for prefix in CHECK_PATH_PREFIXES)


def _extract_header(headers: dict[str, str], key: str, default: str = "") -> str:
    """Extract header value (case-insensitive)."""
    return headers.get(key.lower(), headers.get(key, default))


def _int_header(headers: dict[str, str], key: str, default: int = 0) -> int:
    """Extract integer header value."""
    raw = _extract_header(headers, key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_header(headers: dict[str, str], key: str) -> bool:
    """Extract boolean header value."""
    raw = _extract_header(headers, key, "false").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


class AuthorizationServicer(ext_authz_pb2_grpc.AuthorizationServicer):
    """gRPC servicer implementing Envoy ext_authz v3 Authorization.Check"""

    def __init__(self):
        self.http_client = httpx.Client(timeout=AI_DEFENSE_TIMEOUT_SEC)

    def Check(self, request: ext_authz_pb2.CheckRequest, context) -> ext_authz_pb2.CheckResponse:
        """
        Handle authorization check request from Envoy.

        Returns:
            CheckResponse with status OK (code=0) to allow,
            or with denied_response to block/challenge.
        """
        start_time = time.time()

        try:
            # Extract request attributes
            attrs = request.attributes
            http_req = attrs.request if attrs.HasField("request") else None

            if not http_req:
                logger.warning("No HTTP request in CheckRequest")
                return self._allow_response()

            method = http_req.method or "GET"
            path = http_req.path or "/"
            headers = dict(http_req.headers) if http_req.headers else {}

            # Remove query string from path for matching
            path_only = path.split("?")[0]

            logger.info(f"Check request: {method} {path_only}")

            # Skip check if not a protected path
            if not _needs_authz_check(method, path_only):
                logger.debug(f"Skipping authz check for {method} {path_only}")
                return self._allow_response(skipped=True)

            # Extract session/user info from headers
            session_id = _extract_header(headers, "x-session-id", "sess-anon")
            trace_id = _extract_header(headers, "x-trace-id", "")
            authorization = _extract_header(headers, "authorization", "")
            event_type = _extract_header(headers, "x-ext-authz-event-type", "")

            # Build AI Defense request payload
            payload: dict[str, Any] = {
                "session_id": session_id,
                "trace_id": trace_id or None,
                "path": path_only,
                "method": method,
                "timestamp": int(time.time() * 1000),
                "event_type": event_type or None,
                "headers": {
                    "user-agent": _extract_header(headers, "user-agent"),
                    "x-forwarded-for": _extract_header(headers, "x-forwarded-for"),
                    "authorization": authorization[:50] if authorization else "",  # Truncate for safety
                },
                "flow_state": _extract_header(headers, "x-flow-state") or None,
                "defense_tier": _extract_header(headers, "x-defense-tier") or None,
                "challenge_fail_count": _int_header(headers, "x-challenge-fail-count", 0),
                "repetitive_pattern_count": _int_header(headers, "x-repetitive-pattern-count", 0),
                "token_mismatch": _bool_header(headers, "x-token-mismatch"),
            }

            # Call AI Defense service
            try:
                resp = self.http_client.post(AI_DEFENSE_URL, json=payload)
                resp.raise_for_status()
                decision = resp.json()
            except Exception as e:
                logger.error(f"AI Defense call failed: {e}")
                # Fail-open: allow request if AI Defense is unavailable
                return self._allow_response(fail_open=True)

            # Process decision
            allow = bool(decision.get("allow", True))
            headers_to_add = decision.get("headers_to_add") or {}

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"Decision: allow={allow}, elapsed={elapsed_ms:.2f}ms")

            if allow:
                return self._allow_response(extra_headers=headers_to_add)

            # Denied - determine action type
            action = str(decision.get("action", "BLOCK")).upper()
            reason = str(decision.get("reason") or "BLOCKED")

            if action == "CHALLENGE" or reason == "CHALLENGE_REQUIRED":
                return self._deny_response(
                    status_code=428,
                    reason_code="CHALLENGE_REQUIRED",
                    message="Security challenge required",
                    extra_headers=headers_to_add
                )
            elif action == "GATE" or reason == "HIGH_VALUE_GATED":
                return self._deny_response(
                    status_code=428,
                    reason_code="HIGH_VALUE_GATED",
                    message="High-value action gated",
                    extra_headers=headers_to_add
                )
            else:
                return self._deny_response(
                    status_code=403,
                    reason_code="BLOCKED",
                    message="Denied by AI defense",
                    extra_headers=headers_to_add
                )

        except Exception as e:
            logger.exception(f"Unexpected error in Check: {e}")
            # Fail-open on unexpected errors
            return self._allow_response(fail_open=True)

    def _allow_response(
        self,
        skipped: bool = False,
        fail_open: bool = False,
        extra_headers: dict[str, str] | None = None
    ) -> ext_authz_pb2.CheckResponse:
        """Build an OK (allow) response."""
        headers = []

        # Add standard headers
        headers.append(ext_authz_pb2.HeaderValueOption(
            header=ext_authz_pb2.HeaderValue(
                key="x-defense-policy-version",
                value=ADAPTER_POLICY_VERSION
            )
        ))

        if skipped:
            headers.append(ext_authz_pb2.HeaderValueOption(
                header=ext_authz_pb2.HeaderValue(
                    key="x-defense-check-skipped",
                    value="true"
                )
            ))

        if fail_open:
            headers.append(ext_authz_pb2.HeaderValueOption(
                header=ext_authz_pb2.HeaderValue(
                    key="x-defense-adapter",
                    value="fail-open"
                )
            ))

        # Add extra headers from AI Defense
        if extra_headers:
            for key, value in extra_headers.items():
                headers.append(ext_authz_pb2.HeaderValueOption(
                    header=ext_authz_pb2.HeaderValue(
                        key=str(key).lower(),
                        value=str(value)
                    )
                ))

        return ext_authz_pb2.CheckResponse(
            status=ext_authz_pb2.Status(code=0, message="OK"),
            ok_response=ext_authz_pb2.OkHttpResponse(headers=headers)
        )

    def _deny_response(
        self,
        status_code: int,
        reason_code: str,
        message: str,
        extra_headers: dict[str, str] | None = None
    ) -> ext_authz_pb2.CheckResponse:
        """Build a denied response."""
        headers = []

        # Add standard headers
        headers.append(ext_authz_pb2.HeaderValueOption(
            header=ext_authz_pb2.HeaderValue(
                key="x-defense-policy-version",
                value=ADAPTER_POLICY_VERSION
            )
        ))
        headers.append(ext_authz_pb2.HeaderValueOption(
            header=ext_authz_pb2.HeaderValue(
                key="x-defense-reason",
                value=reason_code
            )
        ))

        # Add extra headers
        if extra_headers:
            for key, value in extra_headers.items():
                headers.append(ext_authz_pb2.HeaderValueOption(
                    header=ext_authz_pb2.HeaderValue(
                        key=str(key).lower(),
                        value=str(value)
                    )
                ))

        body = f'{{"status":"FAIL","reasonCode":"{reason_code}","message":"{message}"}}'

        return ext_authz_pb2.CheckResponse(
            status=ext_authz_pb2.Status(code=7, message="PERMISSION_DENIED"),  # code 7 = PERMISSION_DENIED
            denied_response=ext_authz_pb2.DeniedHttpResponse(
                status=ext_authz_pb2.HttpStatus(code=status_code),
                headers=headers,
                body=body
            )
        )


def serve():
    """Start the gRPC server."""
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=GRPC_WORKERS),
        options=[
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),  # 10MB
            ("grpc.max_send_message_length", 10 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 5000),
            ("grpc.keepalive_permit_without_calls", True),
        ]
    )

    # Register Authorization service
    ext_authz_pb2_grpc.add_AuthorizationServicer_to_server(
        AuthorizationServicer(),
        server
    )

    # Enable reflection for debugging
    SERVICE_NAMES = (
        ext_authz_pb2.DESCRIPTOR.services_by_name["Authorization"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    # Start server
    listen_addr = f"[::]:{GRPC_PORT}"
    server.add_insecure_port(listen_addr)
    server.start()

    logger.info(f"gRPC ext_authz adapter started on {listen_addr}")
    logger.info(f"AI Defense URL: {AI_DEFENSE_URL}")
    logger.info(f"Check methods: {CHECK_METHODS}")
    logger.info(f"Check path prefixes: {CHECK_PATH_PREFIXES}")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.stop(grace=5)


if __name__ == "__main__":
    serve()
