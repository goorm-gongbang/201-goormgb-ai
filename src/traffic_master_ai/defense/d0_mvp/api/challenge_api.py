"""Challenge issue/verify API endpoints."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..core.enums import FlowState, ReasonCode
from .compat import APIRouter, Body, Header, Response
from .http_errors import ensure_route_handler_alias, raise_contract_http_error
from .response_utils import (
    error_payload,
    finalize_payload,
    infer_terminal_reason,
    parse_request_meta_headers,
)
from .runtime import DefenseRuntime, RuntimeAPIError


def create_challenge_router(runtime: Optional[DefenseRuntime] = None) -> APIRouter:
    """Create /defense/challenge router."""
    rt = runtime or DefenseRuntime()
    router = APIRouter(prefix="/defense/challenge", tags=["defense-challenge"])

    @router.post("/issue")
    def challenge_issue_endpoint(
        body: Mapping[str, Any] = Body(default={}),
        x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
        x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
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

        viewport = body.get("clientViewport")
        flow_state_raw = body.get("flowState")
        requested_flow_state = None
        if flow_state_raw is not None:
            try:
                requested_flow_state = FlowState(str(flow_state_raw))
            except ValueError:
                raise_contract_http_error(
                    error_payload(ReasonCode.VALIDATION_ERROR, "flowState must be a valid FlowState"),
                    status_code=400,
                )
        try:
            issue = rt.issue_challenge(
                session_id=x_session_id,
                trace_id=x_trace_id,
                requested_flow_state=requested_flow_state,
                client_viewport=viewport if isinstance(viewport, Mapping) else None,
                request_meta=request_meta or None,
            )
        except RuntimeAPIError as exc:
            raise_contract_http_error(
                exc.to_error_body(),
                status_code=exc.status_code,
                headers=passthrough_headers,
            )
        except Exception as exc:
            raise_contract_http_error(
                error_payload(ReasonCode.INTERNAL_ERROR, str(exc)),
                status_code=500,
                headers=passthrough_headers,
            )
        return finalize_payload({
            "challenge_id": issue.challenge_id,
            "game_id": issue.game_id,
            "issued_at_ms": issue.issued_at_ms,
            "expires_at_ms": issue.expires_at_ms,
            "seed_commitment": issue.seed_commitment,
            "public_params": issue.public_params,
        }, response=response, headers=passthrough_headers)

    @router.post("/verify")
    def challenge_verify_endpoint(
        body: Mapping[str, Any] = Body(default={}),
        x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
        x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
        x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
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

        challenge_id = body.get("challenge_id")
        client_answer = body.get("client_answer")
        if not isinstance(challenge_id, str) or not isinstance(client_answer, Mapping):
            raise_contract_http_error(
                error_payload(
                    ReasonCode.VALIDATION_ERROR,
                    "challenge_id and client_answer are required",
                ),
                status_code=400,
            )

        try:
            result = rt.verify_challenge(
                session_id=x_session_id,
                trace_id=x_trace_id,
                challenge_id=challenge_id,
                client_answer=client_answer,
                request_meta=request_meta or None,
                request_user_id=x_user_id.strip() if x_user_id else None,
            )
        except RuntimeAPIError as exc:
            raise_contract_http_error(
                exc.to_error_body(),
                status_code=exc.status_code,
                headers=passthrough_headers,
            )
        except Exception as exc:
            raise_contract_http_error(
                error_payload(ReasonCode.INTERNAL_ERROR, str(exc)),
                status_code=500,
                headers=passthrough_headers,
            )
        body_out = {
            "result": result.result,
            "reason_code": result.reason_code,
            "server_verdict": result.server_verdict,
            "http_status": result.http_status,
            "cooldown_ms": result.cooldown_ms,
            "attempts_in_window": result.attempts_in_window,
        }
        if result.http_status >= 400:
            raise_contract_http_error(
                error_payload(
                    result.reason_code,
                    "challenge verification failed",
                    detail=body_out,
                    terminal_reason=infer_terminal_reason(
                        reason_code=result.reason_code,
                        action="BLOCK" if result.reason_code == ReasonCode.BLOCKED.value else None,
                        state_to=None,
                    ),
                ),
                status_code=result.http_status,
                headers=passthrough_headers,
            )
        return finalize_payload(
            body_out,
            response=response,
            status_code=result.http_status,
            headers=passthrough_headers,
        )

    return ensure_route_handler_alias(router)


__all__ = ["create_challenge_router"]
