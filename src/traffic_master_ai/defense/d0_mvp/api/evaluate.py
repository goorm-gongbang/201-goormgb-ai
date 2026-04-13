"""/evaluate API endpoint integration.

Ref: L1/runtime/contracts.yaml#ai_evaluate
     — response provides x-defense-* headers and DefenseDecision body.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..core.enums import ReasonCode
from .compat import APIRouter, Body, Header, Response
from .http_errors import ensure_route_handler_alias, raise_contract_http_error
from .response_utils import (
    error_payload,
    finalize_payload,
    infer_terminal_reason,
    merge_headers,
    parse_request_meta_headers,
)
from .runtime import DefenseRuntime, RuntimeAPIError, build_evaluate_request


def create_evaluate_router(runtime: Optional[DefenseRuntime] = None) -> APIRouter:
    """Create /evaluate router.

    Ref: L1/runtime/contracts.yaml §5 — ai_evaluate
    Response includes:
    - body: DefenseDecision schema
    - headers: x-defense-tier, x-defense-action, x-defense-policy-version
    """
    rt = runtime or DefenseRuntime()
    router = APIRouter(tags=["defense-evaluate"])

    @router.post("/evaluate")
    def evaluate_endpoint(
        body: Mapping[str, Any] = Body(default={}),
        x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
        x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
        x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
        x_turnstile_token: Optional[str] = Header(default=None, alias="X-Turnstile-Token"),
        x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-Id"),
        x_tm_test_mode: Optional[str] = Header(default=None, alias="X-TM-TestMode"),
        response: Response = None,
    ) -> dict[str, Any]:
        if not x_session_id or not x_trace_id:
            raise_contract_http_error(
                error_payload(
                    ReasonCode.VALIDATION_ERROR,
                    "X-Session-Id and X-Trace-Id are required",
                ),
                status_code=400,
            )
        try:
            request_meta, passthrough_headers = parse_request_meta_headers(
                x_correlation_id=x_correlation_id,
                x_tm_test_mode=x_tm_test_mode,
            )
        except ValueError as exc:
            raise_contract_http_error(
                error_payload(ReasonCode.VALIDATION_ERROR, str(exc)),
                status_code=400,
            )

        try:
            req = build_evaluate_request(
                session_id=x_session_id,
                trace_id=x_trace_id,
                body=body,
            )
            if x_user_id:
                req.user_id = x_user_id.strip() or None
            if x_turnstile_token:
                if req.context.meta is None:
                    req.context.meta = {}
                req.context.meta["turnstile_token"] = x_turnstile_token
            if request_meta:
                if req.context.meta is None:
                    req.context.meta = {}
                req.context.meta.update(request_meta)
        except Exception as exc:
            raise_contract_http_error(
                error_payload(ReasonCode.VALIDATION_ERROR, str(exc)),
                status_code=400,
            )

        try:
            out = rt.evaluate(req)
        except RuntimeAPIError as exc:
            raise_contract_http_error(
                exc.to_error_body(),
                status_code=exc.status_code,
                headers=passthrough_headers,
            )
        except ValueError as exc:
            raise_contract_http_error(
                error_payload(ReasonCode.VALIDATION_ERROR, str(exc)),
                status_code=400,
            )
        except Exception as exc:
            try:
                out = rt.fail_open_on_unavailable(request=req, error=exc)
            except RuntimeAPIError as runtime_exc:
                raise_contract_http_error(
                    runtime_exc.to_error_body(),
                    status_code=runtime_exc.status_code,
                    headers=passthrough_headers,
                )

        orchestrated = out.orchestrator_result
        decision = orchestrated.decision
        headers = merge_headers(decision.to_headers(), passthrough_headers)
        denied_reason_code = (
            orchestrated.error.reason_code
            if orchestrated.error is not None
            else ReasonCode.INTERNAL_ERROR.value
        )
        terminal_reason = infer_terminal_reason(
            reason_code=denied_reason_code,
            action=decision.action.value,
            state_to=orchestrated.state_to.value if orchestrated.state_to else None,
        )

        # Deny path: return proper HTTP status + ErrorResponse + x-defense-* headers
        # Ref: contracts.yaml#schemas.ErrorResponse
        if not orchestrated.allow:
            http_status = orchestrated.http_status or 403
            raise_contract_http_error(
                error_payload(
                    denied_reason_code,
                    orchestrated.error.message if orchestrated.error else "",
                    orchestrated.error.detail if orchestrated.error else None,
                    terminal_reason=terminal_reason,
                ),
                status_code=http_status,
                headers=headers,
            )

        # Allow path: return DefenseDecision body + x-defense-* headers
        # Ref: contracts.yaml §5 — provides_x_defense_headers: true
        response_body: dict[str, Any] = {
            "tier": decision.tier.value,
            "action": decision.action.value,
            "policyVersion": decision.policy_version,
            "throttleMs": decision.throttle_ms,
            "blockTtlSeconds": decision.block_ttl_seconds,
            "reason": decision.reason,
        }
        allow_terminal_reason = infer_terminal_reason(
            reason_code=None,
            action=decision.action.value,
            state_to=orchestrated.state_to.value if orchestrated.state_to else None,
        )
        if allow_terminal_reason:
            response_body["terminalReason"] = allow_terminal_reason
        return finalize_payload(response_body, response=response, headers=headers)

    return ensure_route_handler_alias(router)


__all__ = ["create_evaluate_router"]
