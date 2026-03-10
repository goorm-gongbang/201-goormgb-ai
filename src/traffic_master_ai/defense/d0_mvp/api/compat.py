"""FastAPI compatibility shim.

If FastAPI is not installed, lightweight stubs keep modules importable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

try:
    from fastapi import APIRouter, Body, FastAPI, Header, HTTPException, Response
    from fastapi.responses import HTMLResponse

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False

    class HTTPException(Exception):
        def __init__(
            self,
            status_code: int,
            detail: Any = None,
            headers: Optional[dict[str, str]] = None,
        ) -> None:
            super().__init__(f"HTTP {status_code}: {detail}")
            self.status_code = status_code
            self.detail = detail
            self.headers = headers or {}

    class Response:
        def __init__(self, status_code: int = 200) -> None:
            self.status_code = status_code
            self.headers: dict[str, str] = {}

    def Header(default: Any = None, alias: Optional[str] = None) -> Any:
        del alias
        return default

    def Body(default: Any = None) -> Any:
        return default

    class HTMLResponse(str):
        def __new__(cls, content: str, status_code: int = 200) -> "HTMLResponse":
            obj = str.__new__(cls, content)
            obj.status_code = status_code
            return obj

    @dataclass
    class _Route:
        method: str
        path: str
        handler: Callable[..., Any]

    class APIRouter:
        def __init__(self, prefix: str = "", tags: Optional[list[str]] = None) -> None:
            self.prefix = prefix
            self.tags = tags or []
            self.routes: list[_Route] = []

        def post(
            self, path: str, **kwargs: Any
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            del kwargs
            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                self.routes.append(_Route(method="POST", path=f"{self.prefix}{path}", handler=func))
                return func

            return decorator

        def get(
            self, path: str, **kwargs: Any
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            del kwargs
            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                self.routes.append(_Route(method="GET", path=f"{self.prefix}{path}", handler=func))
                return func

            return decorator

    class FastAPI(APIRouter):
        def __init__(self, title: str = "app") -> None:
            super().__init__(prefix="")
            self.title = title
            self._routers: list[APIRouter] = []

        def include_router(self, router: APIRouter) -> None:
            self._routers.append(router)


__all__ = [
    "APIRouter",
    "Body",
    "FastAPI",
    "FASTAPI_AVAILABLE",
    "Header",
    "HTMLResponse",
    "HTTPException",
    "Response",
]
