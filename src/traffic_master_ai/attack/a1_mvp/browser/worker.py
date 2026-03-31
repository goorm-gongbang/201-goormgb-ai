"""Browser worker (Playwright) for Attack Agent MVP.

Design goals:
- Keep the orchestrator logic decoupled from Playwright calls.
- Provide "human-ish" primitives (click/type) that generate real mouse events
  so the FE behavioral sensor can observe them.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

from ..logging.audit import now_ms
from ..trajectory.synthesizer import TrajectorySynthesizer


class BrowserWorker:
    def __init__(
        self,
        page: Any,
        *,
        seed: int | None = None,
        mouse_profile: str = "human",
        audit_cb: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.page = page
        self._rng = random.Random(seed)
        self._mouse_profile = mouse_profile
        self._audit_cb = audit_cb
        self._synth = TrajectorySynthesizer(self._rng)
        # Best-effort internal mouse position tracking (Playwright doesn't expose it).
        self._mouse_x = 0.0
        self._mouse_y = 0.0

    async def goto(self, url: str) -> None:
        await self.page.goto(url, wait_until="domcontentloaded")

    async def reload(self) -> None:
        await self.page.reload(wait_until="domcontentloaded")

    async def wait_for_url(self, url_glob: str, *, timeout_ms: int = 120_000) -> None:
        await self.page.wait_for_url(url_glob, timeout=timeout_ms)

    async def wait_for_selector(self, selector: str, *, timeout_ms: int = 30_000) -> None:
        await self.page.wait_for_selector(selector, timeout=timeout_ms)

    async def is_visible(self, selector: str) -> bool:
        loc = self.page.locator(selector)
        try:
            return await loc.is_visible()
        except Exception:
            return False

    async def get_inner_text(self, selector: str) -> str:
        return await self.page.locator(selector).first.inner_text()

    async def is_checked(self, selector: str) -> bool:
        loc = self.page.locator(selector).first
        try:
            return await loc.is_checked()
        except Exception:
            return False

    async def select_option(self, selector: str, value: str) -> None:
        await self.page.select_option(selector, value=value)

    async def set_local_storage_json(self, key: str, value_obj: Any) -> None:
        # Avoid interpolating raw JSON into JS source; let the browser stringify.
        await self.page.evaluate(
            """([k, v]) => { localStorage.setItem(k, JSON.stringify(v)); }""",
            [key, value_obj],
        )

    async def set_local_storage(self, key: str, value: str) -> None:
        await self.page.evaluate("""([k, v]) => { localStorage.setItem(k, v); }""", [key, value])

    async def get_local_storage(self, key: str) -> str | None:
        return await self.page.evaluate("""(k) => localStorage.getItem(k)""", key)

    async def human_click(self, selector: str, *, timeout_ms: int = 30_000, fast: bool = False) -> None:
        loc = self.page.locator(selector).first
        await loc.wait_for(state="visible", timeout=timeout_ms)
        await loc.scroll_into_view_if_needed()

        box = await loc.bounding_box()
        if not box:
            # Fallback to Playwright click (still generates real input events).
            await loc.click()
            return

        # Aim somewhere inside the element, not dead-center.
        tx = box["x"] + box["width"] * self._rng.uniform(0.25, 0.75)
        ty = box["y"] + box["height"] * self._rng.uniform(0.30, 0.70)

        if self._mouse_profile == "bot":
            dwell_ms = await self._bot_move_to(tx, ty)
        else:
            dwell_ms = await self._human_move_to(tx, ty)

        # Dwell before click (affects sensor's dwellTime distribution).
        if fast:
            dwell_ms = min(int(dwell_ms), int(self._rng.uniform(8, 35)))
        await self.page.wait_for_timeout(int(dwell_ms))
        await self.page.mouse.down()
        if fast:
            await self.page.wait_for_timeout(int(self._rng.uniform(8, 25)))
        else:
            await self.page.wait_for_timeout(int(self._rng.uniform(20, 60)))
        await self.page.mouse.up()

    async def human_type(
        self,
        selector: str,
        text: str,
        *,
        timeout_ms: int = 30_000,
        fast_focus: bool = False,
    ) -> None:
        loc = self.page.locator(selector).first
        await loc.wait_for(state="visible", timeout=timeout_ms)
        await loc.scroll_into_view_if_needed()
        # Keep typing interactions observable by the telemetry layer.
        # Using human_click avoids introducing zero-distance click segments.
        await self.human_click(selector, timeout_ms=timeout_ms, fast=fast_focus)
        # Clear existing text.
        try:
            await loc.fill("")
        except Exception:
            pass
        # Type with per-character delay.
        if fast_focus:
            delay_ms = int(self._rng.uniform(20, 45))
        else:
            delay_ms = int(self._rng.uniform(35, 85))
        await loc.type(text, delay=delay_ms)

    async def _bot_move_to(self, x: float, y: float) -> int:
        """Straight-line movement profile for AC-4 (bot detection)."""
        sx, sy = self._mouse_x, self._mouse_y

        # Avoid sweeping from (0,0) on the first move.
        if sx == 0.0 and sy == 0.0:
            sx = max(1.0, x + self._rng.uniform(-40, 40))
            sy = max(1.0, y + self._rng.uniform(-40, 40))
            await self.page.mouse.move(sx, sy)

        steps = 8
        dx = x - sx
        dy = y - sy
        for i in range(1, steps + 1):
            t = i / steps
            await self.page.mouse.move(sx + dx * t, sy + dy * t)

        self._mouse_x, self._mouse_y = x, y
        # Minimal dwell to keep bot "snappy".
        return int(self._rng.uniform(15, 40))

    async def _human_move_to(self, x: float, y: float) -> int:
        sx, sy = self._mouse_x, self._mouse_y

        # If this is the first move, jump near the start to avoid sweeping from (0,0).
        if sx == 0.0 and sy == 0.0:
            sx = max(1.0, x + self._rng.uniform(-60, 60))
            sy = max(1.0, y + self._rng.uniform(-60, 60))
            await self.page.mouse.move(sx, sy)

        # Bezier + noise (M-Prim): synthesize a human-ish trajectory between points.
        res = self._synth.synthesize((sx, sy), (x, y))
        for (px, py) in res.points[1:]:
            await self.page.mouse.move(px, py)
            # Wall-clock timing matters: FE sensor uses event.timeStamp deltas.
            await self.page.wait_for_timeout(res.dt_ms)

        # Ensure we're exactly on target before clicking (noise can end off-target).
        await self.page.mouse.move(x, y)
        self._mouse_x, self._mouse_y = x, y

        if self._audit_cb is not None:
            self._audit_cb(
                {
                    "ts_ms": now_ms(),
                    "event": "TRAJ_SYNTH",
                    "flow_state": "NA",
                    "target": {
                        "velocity_profile": res.target.velocity_profile,
                        "linearity_ratio": res.target.linearity_ratio,
                        "tremor_std_dev": res.target.tremor_std_dev,
                        "avg_velocity": res.target.avg_velocity,
                        "dwell_time_ms": res.target.dwell_time_ms,
                    },
                    "computed": {
                        "total_dist": res.computed.total_dist,
                        "linear_dist": res.computed.linear_dist,
                        "linearity_ratio": res.computed.linearity_ratio,
                        "avg_velocity": res.computed.avg_velocity,
                        "tremor_std_dev": res.computed.tremor_std_dev,
                        "dwell_time_ms": res.computed.dwell_time_ms,
                    },
                }
            )

        return int(max(25.0, min(2000.0, res.target.dwell_time_ms)))
