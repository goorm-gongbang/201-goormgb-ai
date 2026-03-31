"""Contract-specific HTTP exception helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from .compat import APIRouter, FASTAPI_AVAILABLE, FastAPI, HTTPException

if FASTAPI_AVAILABLE:
    from fastapi import Request
    from fastapi.responses import JSONResponse
else:
    Request = Any

    class JSONResponse(dict[str, Any]):
        def __init__(
            self,
            *,
            status_code: int,
            content: Any,
            headers: Optional[Mapping[str, str]] = None,
        ) -> None:
            super().__init__(content=content, status_code=status_code, headers=dict(headers or {}))


class ContractHTTPException(HTTPException):
    """HTTPException variant whose detail is the final response body."""


def raise_contract_http_error(
    detail: Mapping[str, Any],
    *,
    status_code: int,
    headers: Optional[Mapping[str, str]] = None,
) -> None:
    """Raise one HTTP exception for SSOT contract bodies."""
    raise ContractHTTPException(
        status_code=status_code,
        detail=dict(detail),
        headers=dict(headers or {}),
    )


def install_contract_exception_handler(app: FastAPI) -> None:
    """Emit ContractHTTPException.detail as the root JSON body in FastAPI."""
    if not FASTAPI_AVAILABLE:
        return

    @app.exception_handler(ContractHTTPException)
    async def _contract_http_exception_handler(
        request: Request, exc: ContractHTTPException
    ) -> JSONResponse:
        del request
        content = exc.detail if isinstance(exc.detail, Mapping) else {"detail": exc.detail}
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=exc.headers or {},
        )


def ensure_route_handler_alias(router: APIRouter) -> APIRouter:
    """Mirror compatibility-shim route.handler on real FastAPI routes."""
    for route in getattr(router, "routes", []):
        if not hasattr(route, "handler") and hasattr(route, "endpoint"):
            setattr(route, "handler", route.endpoint)
    return router


__all__ = [
    "ContractHTTPException",
    "ensure_route_handler_alias",
    "install_contract_exception_handler",
    "raise_contract_http_error",
]
