"""/check/* adapter endpoint integration.

Ref: L1/runtime/contracts.yaml#envoy_ext_authz_adapter
     — path_prefix: "/check/"
     — response_contract: allow/deny with x-defense-* headers
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
from .runtime import DefenseRuntime, RuntimeAPIError, build_check_request, _to_runtime_event


def create_check_router(runtime: Optional[DefenseRuntime] = None) -> APIRouter:
    """Create /check router.

    Ref: contracts.yaml §4 — envoy_ext_authz_adapter
    """
    rt = runtime or DefenseRuntime()
    router = APIRouter(prefix="/check", tags=["defense-check"])

    @router.post("/evaluate")
    def check_evaluate_endpoint(
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
            check_req = build_check_request(
                session_id=x_session_id,
                trace_id=x_trace_id,
                body=body,
            )
            if x_user_id:
                check_req.user_id = x_user_id.strip() or None
            if x_turnstile_token:
                check_req.turnstile_token = x_turnstile_token
        except Exception as exc:
            raise_contract_http_error(
                error_payload(ReasonCode.VALIDATION_ERROR, str(exc)),
                status_code=400,
            )

        try:
            eval_req = rt.check_request_to_evaluate(check_req)
        except RuntimeAPIError as exc:
            raise_contract_http_error(
                exc.to_error_body(),
                status_code=exc.status_code,
                headers=passthrough_headers,
            )
        if request_meta:
            if eval_req.context.meta is None:
                eval_req.context.meta = {}
            eval_req.context.meta.update(request_meta)
        try:
            out = rt.evaluate(eval_req)
        except ValueError as exc:
            raise_contract_http_error(
                error_payload(ReasonCode.VALIDATION_ERROR, str(exc)),
                status_code=400,
            )
        except Exception as exc:
            out = rt.fail_open_on_unavailable(request=eval_req, error=exc)
        orchestrated = out.orchestrator_result

        headers = merge_headers(orchestrated.headers, passthrough_headers)
        decision = orchestrated.decision

        # Apply throttle delay if needed
        # Ref: annex/throttle_spec.yaml#adapter_enforcement
        if orchestrated.allow and decision.action.value == "THROTTLE":
            delay_ms = rt.throttle.resolve_delay_ms(
                action=decision.action,
                tier=decision.tier,
                policy=out.policy,
                request_path=check_req.upstream_path,
                override_delay_ms=decision.throttle_ms,
            )
            headers["x-defense-throttle-ms"] = str(delay_ms)
            rt.throttle.apply_delay(delay_ms)

            # Emit DEF_THROTTLE_APPLIED audit event
            event = _to_runtime_event(eval_req)
            rt.emit_throttle_audit(
                request=eval_req,
                event=event,
                policy=out.policy,
                tier=decision.tier.value,
                delay_ms=delay_ms,
                request_path=check_req.upstream_path,
                request_method=check_req.upstream_method,
            )

        # Allow path
        # Ref: contracts.yaml §4 — response_contract.allow
        if orchestrated.allow:
            body_out = {"allow": True}
            allow_terminal_reason = infer_terminal_reason(
                reason_code=None,
                action=decision.action.value,
                state_to=orchestrated.state_to.value if orchestrated.state_to else None,
            )
            if allow_terminal_reason:
                body_out["terminalReason"] = allow_terminal_reason
            return finalize_payload(body_out, response=response, headers=headers)

        # Deny path
        # Ref: contracts.yaml §4 — response_contract.deny
        if orchestrated.error is None or orchestrated.http_status is None:
            raise_contract_http_error(
                error_payload(ReasonCode.INTERNAL_ERROR, "invalid orchestrator deny result"),
                status_code=500,
            )

        raise_contract_http_error(
            error_payload(
                orchestrated.error.reason_code,
                orchestrated.error.message,
                orchestrated.error.detail,
                terminal_reason=infer_terminal_reason(
                    reason_code=orchestrated.error.reason_code,
                    action=decision.action.value,
                    state_to=orchestrated.state_to.value if orchestrated.state_to else None,
                ),
            ),
            status_code=orchestrated.http_status,
            headers=headers,
        )

    return ensure_route_handler_alias(router)


__all__ = ["create_check_router"]
