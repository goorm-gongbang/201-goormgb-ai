"""Compatibility sync endpoints for external runtimes.

Provides backend-to-runtime VQA pass/fail sync so legacy callers can update
`s3Passed` state without going through challenge verify flow.
"""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional

from ..core.enums import FlowState, ReasonCode
from .compat import APIRouter, Body
from .http_errors import ensure_route_handler_alias, raise_contract_http_error
from .response_utils import error_payload
from .runtime import DefenseRuntime


def create_runtime_sync_router(runtime: Optional[DefenseRuntime] = None) -> APIRouter:
    """Create compatibility sync router."""
    rt = runtime or DefenseRuntime()
    router = APIRouter(tags=["defense-runtime-sync"])

    @router.post("/runtime/vqa/mark")
    def runtime_mark_vqa(body: Mapping[str, Any] = Body(default={})) -> dict[str, Any]:
        session_id = _resolve_session_id(body)
        vqa_passed = _resolve_vqa_passed(body)
        flow_state = _resolve_flow_state(body)
        now_ms = int(time.time() * 1000)

        existing = rt.session_state.get_or_create(session_id)
        next_flow = flow_state or (
            FlowState.S4 if (vqa_passed and existing.flow_state == FlowState.S3) else existing.flow_state
        )

        if vqa_passed:
            rt.session_state.update_by_role(
                "orchestrator",
                session_id,
                {
                    "flowState": next_flow.value,
                    "s3Passed": 1,
                    "s3PassedAtMs": now_ms,
                    "lastDecisionAction": "NONE",
                },
                is_allow=True,
            )
            rt.session_state.update_by_role(
                "analyzer",
                session_id,
                {"challengeFailCount": 0},
                is_allow=True,
            )
        else:
            rt.session_state.update_by_role(
                "orchestrator",
                session_id,
                {
                    "flowState": next_flow.value,
                    "s3Passed": 0,
                    "lastDecisionAction": "REQUIRE_S3",
                },
                is_allow=False,
            )

        latest = rt.session_state.get_or_create(session_id)
        return {
            "session_id": session_id,
            "vqa_passed": bool(latest.s3_passed),
            "flow_state": latest.flow_state.value,
            "updated_ts_ms": now_ms,
        }

    return ensure_route_handler_alias(router)


def _resolve_session_id(body: Mapping[str, Any]) -> str:
    raw = body.get("session_id")
    if raw is None:
        raw = body.get("sessionId")
    value = str(raw or "").strip()
    if value:
        return value
    raise_contract_http_error(
        error_payload(ReasonCode.VALIDATION_ERROR, "session_id is required"),
        status_code=400,
    )


def _resolve_vqa_passed(body: Mapping[str, Any]) -> bool:
    raw = body.get("vqa_passed")
    if raw is None:
        raw = body.get("vqaPassed")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise_contract_http_error(
        error_payload(ReasonCode.VALIDATION_ERROR, "vqa_passed must be boolean"),
        status_code=400,
    )


def _resolve_flow_state(body: Mapping[str, Any]) -> Optional[FlowState]:
    raw = body.get("flow_state")
    if raw is None:
        raw = body.get("flowState")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        raise_contract_http_error(
            error_payload(ReasonCode.VALIDATION_ERROR, "flow_state must be non-empty when provided"),
            status_code=400,
        )
    try:
        return FlowState(value)
    except ValueError:
        raise_contract_http_error(
            error_payload(ReasonCode.VALIDATION_ERROR, "flow_state must be a valid FlowState"),
            status_code=400,
        )
    return None


__all__ = ["create_runtime_sync_router"]
