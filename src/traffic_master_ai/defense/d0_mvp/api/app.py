"""FastAPI app factory for D0-MVP."""

from __future__ import annotations

from typing import Optional

from .admin_console import create_admin_console_router
from .challenge_api import create_challenge_router
from .check import create_check_router
from .compat import FASTAPI_AVAILABLE, FastAPI
from .evaluate import create_evaluate_router
from .http_errors import install_contract_exception_handler
from .runtime import DefenseRuntime


def create_app(
    runtime: Optional[DefenseRuntime] = None,
    *,
    include_admin: bool = True,
) -> FastAPI:
    """Create D0-MVP API app and register routers.

    `include_admin=False` keeps online runtime path minimal.
    """
    app = FastAPI(title="traffic-master-defense-d0-mvp")
    install_contract_exception_handler(app)
    rt = runtime or DefenseRuntime()
    app.include_router(create_evaluate_router(rt))
    app.include_router(create_check_router(rt))
    app.include_router(create_challenge_router(rt))
    if include_admin:
        app.include_router(create_admin_console_router(rt))
    return app


__all__ = ["create_app", "FASTAPI_AVAILABLE"]
