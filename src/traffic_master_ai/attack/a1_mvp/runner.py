from __future__ import annotations

import asyncio
from typing import Any

from traffic_master_ai.common.models.states import FlowState

from .browser.worker import BrowserWorker
from .config import RunConfig
from .graph.builder import compile_app
from .graph.context import AgentContext
from .logging.audit import DecisionAuditLogger, now_ms
from .state import AgentState


async def run_once(cfg: RunConfig, audit: DecisionAuditLogger) -> dict[str, Any]:
    """Run a single end-to-end agent instance."""
    try:
        from playwright.async_api import async_playwright  # type: ignore[import-not-found]
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Playwright is required for attack/a1_mvp.\n"
            "Install:\n"
            "  pip install playwright\n"
            "  playwright install chromium\n"
        ) from e

    app = compile_app()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=cfg.headless, slow_mo=cfg.slow_mo_ms)
        context = await browser.new_context()
        page = await context.new_page()

        worker = BrowserWorker(page, mouse_profile=cfg.mouse_profile, audit_cb=audit.log)
        ctx = AgentContext(cfg=cfg, worker=worker, audit=audit)

        init_state = AgentState(flow_state=FlowState.S0, mode=cfg.mode)

        audit.log(
            {
                "ts_ms": now_ms(),
                "event": "RUN_START",
                "flow_state": init_state.flow_state.value,
                "mode": init_state.mode,
                "mouse_profile": cfg.mouse_profile,
            }
        )

        final_state = await app.ainvoke(init_state, context=ctx)

        audit.log(
            {
                "ts_ms": now_ms(),
                "event": "RUN_END",
                "flow_state": final_state.get("flow_state"),
                "terminal_reason": final_state.get("terminal_reason"),
            }
        )

        await browser.close()
        return final_state


def run(cfg: RunConfig, audit: DecisionAuditLogger) -> dict[str, Any]:
    return asyncio.run(run_once(cfg, audit))
