"""FastAPI app factory for D0-MVP."""

from __future__ import annotations

from typing import Optional

from .challenge_api import create_challenge_router
from .check import create_check_router
from .compat import FASTAPI_AVAILABLE, FastAPI
from .evaluate import create_evaluate_router
from .http_errors import install_contract_exception_handler
from .runtime import DefenseRuntime
from .runtime_sync import create_runtime_sync_router


def create_app(
    runtime: Optional[DefenseRuntime] = None,
    *,
    include_admin: bool = False,
) -> FastAPI:
    """Create D0-MVP API app and register routers."""
    del include_admin
    app = FastAPI(title="traffic-master-defense-d0-mvp")
    install_contract_exception_handler(app)
    rt = runtime or DefenseRuntime()
    app.include_router(create_evaluate_router(rt))
    app.include_router(create_check_router(rt))
    app.include_router(create_challenge_router(rt))
    app.include_router(create_runtime_sync_router(rt))
    return app


__all__ = ["create_app", "FASTAPI_AVAILABLE"]
