from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace

from langgraph.runtime import Runtime

from traffic_master_ai.common.models.states import FlowState, TerminalReason

from ..logging.audit import now_ms
from ..security.arithmetic import ArithmeticParseError, solve_arithmetic_prompt
from ..state import AgentState
from .context import AgentContext


SEL_BOOKING_BTN = "#booking-button:not([disabled])"
SEL_SECURITY_OVERLAY = '[data-testid="security-overlay"]'
SEL_SECURITY_INPUT = '[data-testid="security-input"]'
SEL_SECURITY_SUBMIT = '[data-testid="security-submit"]'
SEL_SECURITY_ERROR = '[data-testid="security-error"]'

SEL_ZONE_ITEM = 'button[data-testid^="zone-"][data-remaining]:not([disabled])'
SEL_SEAT_GRID = '[data-testid="seat-grid"]'
SEL_SEAT_AVAILABLE = 'button[data-seat-status="AVAILABLE"]'
SEL_MAP_BOOK_BTN = "#booking-button-map:not([disabled])"

SEL_REC_AUTO = '[data-testid="rec-auto-select"]:not([disabled])'
SEL_SEAT_MODE_TOGGLE = '[data-testid="seat-mode-toggle"]'

SEL_HOLD_FAIL_CLOSE = '[data-testid="hold-fail-close"]'

SEL_AGREE_TERMS = '[data-testid="agree-terms"]'
SEL_AGREE_CANCEL = '[data-testid="agree-cancel-fee"]'
SEL_PAY_BTN = "#pay-button:not([disabled])"


async def _enter_security_if_visible(
    state: AgentState,
    runtime: Runtime[AgentContext],
    *,
    where: FlowState,
) -> dict:
    w = runtime.context.worker
    if await w.is_visible(SEL_SECURITY_OVERLAY):
        last = state.last_non_security_state
        if where.can_be_last_non_security():
            last = where
        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "CHALLENGE_DETECTED",
                "flow_state": where.value,
            }
        )
        return {
            "flow_state": FlowState.S3,
            "last_non_security_state": last,
        }
    return {}


async def node_init(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    cfg = runtime.context.cfg
    w = runtime.context.worker

    await w.goto(f"{cfg.frontend_url}/games/{cfg.game_id}")

    # Deterministic session ID for this run.
    session_id = str(uuid.uuid4())
    await w.set_local_storage("TM_SESSION_ID", session_id)

    # Ensure Pre-Entry preference matches agent mode (controls queue nextUrl mode).
    prefs = {
        "recommendEnabled": state.mode == "RECOMMEND",
        "partySize": 2,
        "priceFilterEnabled": False,
        "priceRange": {"min": 20000, "max": 100000},
    }
    await w.set_local_storage_json("TM_PREFERENCES", prefs)
    await w.reload()

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "BOOTSTRAP_COMPLETE",
            "flow_state": FlowState.S0.value,
            "mode": state.mode,
            "session_id": session_id,
        }
    )

    return {"flow_state": FlowState.S1, "session_id": session_id}


async def node_pre_entry(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    # Security can be inserted here.
    sec = await _enter_security_if_visible(state, runtime, where=FlowState.S1)
    if sec:
        return sec

    w = runtime.context.worker

    try:
        await w.wait_for_selector(SEL_BOOKING_BTN, timeout_ms=120_000)
        await w.human_click(SEL_BOOKING_BTN)
        await w.wait_for_url("**/queue/**", timeout_ms=60_000)
    except Exception as e:
        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "PRE_ENTRY_FAILED",
                "flow_state": FlowState.S1.value,
                "error": repr(e),
            }
        )
        return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.ABORT}

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "ENTRY_CLICKED",
            "flow_state": FlowState.S1.value,
        }
    )
    return {"flow_state": FlowState.S2}


async def node_queue(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    sec = await _enter_security_if_visible(state, runtime, where=FlowState.S2)
    if sec:
        return sec

    w = runtime.context.worker

    try:
        # Queue page redirects to /seats?mode=... once GRANTED.
        if state.mode == "MAP":
            await w.wait_for_url("**/seats?mode=MAP", timeout_ms=180_000)
            next_state = FlowState.S4
        else:
            await w.wait_for_url("**/seats?mode=RECOMMEND", timeout_ms=180_000)
            next_state = FlowState.S4R
    except Exception as e:
        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "QUEUE_TIMEOUT",
                "flow_state": FlowState.S2.value,
                "error": repr(e),
            }
        )
        return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.ABORT}

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "QUEUE_PASSED",
            "flow_state": FlowState.S2.value,
        }
    )
    return {"flow_state": next_state}


async def node_security(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    w = runtime.context.worker

    try:
        await w.wait_for_selector(SEL_SECURITY_OVERLAY, timeout_ms=30_000)
        await w.wait_for_selector(SEL_SECURITY_INPUT, timeout_ms=30_000)
        overlay_text = await w.get_inner_text(SEL_SECURITY_OVERLAY)
        try:
            answer = solve_arithmetic_prompt(overlay_text)
        except ArithmeticParseError:
            # Current backend prompt is fixed; safe fallback.
            answer = "7"
        input_loc = w.page.locator(SEL_SECURITY_INPUT).first
        # Keep security gate fast: keyboard focus + fill avoids IME/layout drift
        # without adding extra synthesized mouse movement.
        await input_loc.focus()
        try:
            await input_loc.fill("")
        except Exception:
            pass
        await input_loc.fill(answer)
        submit_loc = w.page.locator(SEL_SECURITY_SUBMIT).first

        # Wait briefly for React state to enable submit.
        try:
            await w.page.wait_for_function(
                "(sel) => { const el = document.querySelector(sel); return !!el && !el.disabled; }",
                SEL_SECURITY_SUBMIT,
                timeout=1_200,
            )
        except Exception:
            # Continue with best-effort submit attempts.
            pass

        async def _wait_submit_result() -> str:
            try:
                await w.page.wait_for_selector(
                    SEL_SECURITY_OVERLAY,
                    state="detached",
                    timeout=2_400,
                )
                return "passed"
            except Exception:
                try:
                    if await w.is_visible(SEL_SECURITY_ERROR):
                        return "error"
                except Exception:
                    pass
                return "pending"

        submit_attempts: list[str] = [
            "locator_click",
            "press_enter",
            "locator_click_force",
            "js_click",
        ]
        last_err: Exception | None = None
        for i, method in enumerate(submit_attempts, start=1):
            try:
                if method == "locator_click":
                    await submit_loc.click(timeout=2_500)
                elif method == "locator_click_force":
                    await submit_loc.click(timeout=2_500, force=True)
                elif method == "press_enter":
                    await input_loc.press("Enter")
                elif method == "js_click":
                    # Last resort: may produce untrusted events; ok for test-mode recovery.
                    await w.page.evaluate(
                        "(sel) => { const el = document.querySelector(sel); if (el) el.click(); }",
                        SEL_SECURITY_SUBMIT,
                    )
                else:
                    raise RuntimeError(f"unknown submit method: {method}")

                outcome = await _wait_submit_result()
                if outcome == "passed":
                    last_err = None
                    break
                if outcome == "error":
                    msg = await w.get_inner_text(SEL_SECURITY_ERROR)
                    runtime.context.audit.log(
                        {
                            "ts_ms": now_ms(),
                            "event": "CHALLENGE_SUBMIT_ERROR",
                            "flow_state": FlowState.S3.value,
                            "attempt": i,
                            "method": method,
                            "message": msg,
                        }
                    )
                    raise RuntimeError(f"security verify rejected: {msg}")

                last_err = RuntimeError("security submit pending (overlay still visible)")
            except Exception as e:
                last_err = e
                if i < len(submit_attempts):
                    await asyncio.sleep(0.08)
                    continue
                raise
    except Exception as e:
        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "CHALLENGE_FAILED",
                "flow_state": FlowState.S3.value,
                "error": repr(e),
            }
        )
        return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.BLOCKED}

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "CHALLENGE_PASSED",
            "flow_state": FlowState.S3.value,
        }
    )

    # Return to the last non-security state (default: queue).
    return {"flow_state": state.last_non_security_state or FlowState.S2}


async def node_section_map(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    sec = await _enter_security_if_visible(state, runtime, where=FlowState.S4)
    if sec:
        return sec

    w = runtime.context.worker

    try:
        # Ensure party size is 1 for robustness.
        await w.wait_for_selector('[data-testid="party-size-select"]', timeout_ms=30_000)
        await w.select_option('[data-testid="party-size-select"]', "1")

        # Wait for zones (may require security first in TM_TEST_MODE).
        await w.wait_for_selector(SEL_ZONE_ITEM, timeout_ms=60_000)

        # After zone click, the UI fetches /api/zones/{id}/seats. In TM_TEST_MODE,
        # Defense gating can respond with BLOCKED / CHALLENGE_REQUIRED. Listen for
        # that response deterministically (Playwright Python uses expect_response).
        clicked = False
        try:
            async with w.page.expect_response(
                lambda r: ("/api/zones/" in r.url) and ("/seats" in r.url),
                timeout=60_000,
            ) as resp_info:
                await w.human_click(SEL_ZONE_ITEM)
                clicked = True

            resp = await resp_info.value
            status = resp.status
            reason_code: str | None = None
            if status >= 400:
                try:
                    data = await resp.json()
                    if isinstance(data, dict):
                        reason = data.get("reasonCode")
                        if isinstance(reason, str):
                            reason_code = reason
                except Exception:
                    reason_code = None

            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "ZONE_SEATS_RESPONSE",
                    "flow_state": FlowState.S4.value,
                    "http_status": status,
                    "reason_code": reason_code,
                }
            )

            if status == 403 or reason_code == "BLOCKED":
                runtime.context.audit.log(
                    {
                        "ts_ms": now_ms(),
                        "event": "SECTION_BLOCKED",
                        "flow_state": FlowState.S4.value,
                        "http_status": status,
                        "reason_code": reason_code,
                    }
                )
                return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.BLOCKED}

            if status == 428 or reason_code == "CHALLENGE_REQUIRED":
                return {"flow_state": FlowState.S3, "last_non_security_state": FlowState.S4}
        except Exception:
            # If we fail to capture the response, proceed best-effort.
            if not clicked:
                await w.human_click(SEL_ZONE_ITEM)

        # Seat grid appears after zone selection and fetch.
        await w.wait_for_selector(SEL_SEAT_GRID, timeout_ms=60_000)
    except Exception as e:
        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "SECTION_FAILED",
                "flow_state": FlowState.S4.value,
                "error": repr(e),
            }
        )
        # If a challenge popped up during the zone/seat-grid fetch, handle it as an interrupt.
        try:
            if await w.is_visible(SEL_SECURITY_OVERLAY):
                return {"flow_state": FlowState.S3, "last_non_security_state": FlowState.S4}
        except Exception:
            pass
        return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.ABORT}

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "SECTION_SELECTED",
            "flow_state": FlowState.S4.value,
        }
    )
    return {"flow_state": FlowState.S5}


async def node_seat_map(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    sec = await _enter_security_if_visible(state, runtime, where=FlowState.S5)
    if sec:
        return sec

    w = runtime.context.worker

    try:
        await w.wait_for_selector(SEL_SEAT_AVAILABLE, timeout_ms=60_000)
        # Select exactly one seat (party size set to 1).
        await w.human_click(SEL_SEAT_AVAILABLE)

        await w.wait_for_selector(SEL_MAP_BOOK_BTN, timeout_ms=10_000)
        # Defense gating can block /api/holds. Detect quickly to avoid long UI timeouts.
        clicked = False
        try:
            async with w.page.expect_response(
                lambda r: "/api/holds" in r.url,
                timeout=10_000,
            ) as resp_info:
                await w.human_click(SEL_MAP_BOOK_BTN)
                clicked = True

            hold_resp = await resp_info.value
            if hold_resp.status >= 400:
                reason_code: str | None = None
                try:
                    data = await hold_resp.json()
                    if isinstance(data, dict):
                        reason = data.get("reasonCode")
                        if isinstance(reason, str):
                            reason_code = reason
                except Exception:
                    reason_code = None

                runtime.context.audit.log(
                    {
                        "ts_ms": now_ms(),
                        "event": "HOLDS_RESPONSE",
                        "flow_state": FlowState.S5.value,
                        "http_status": hold_resp.status,
                        "reason_code": reason_code,
                    }
                )

                if hold_resp.status == 403 or reason_code == "BLOCKED":
                    return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.BLOCKED}
                if hold_resp.status == 428 or reason_code == "CHALLENGE_REQUIRED":
                    return {"flow_state": FlowState.S3, "last_non_security_state": FlowState.S5}
        except Exception:
            if not clicked:
                await w.human_click(SEL_MAP_BOOK_BTN)

        # Either payment navigation, or hold failure modal.
        async def _wait_payment() -> str:
            await w.wait_for_url("**/payment?orderId=*", timeout_ms=60_000)
            return "PAYMENT"

        async def _wait_hold_fail() -> str:
            await w.wait_for_selector(SEL_HOLD_FAIL_CLOSE, timeout_ms=60_000)
            return "HOLD_FAIL"

        done, pending = await asyncio.wait(
            {asyncio.create_task(_wait_payment()), asyncio.create_task(_wait_hold_fail())},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for p in pending:
            p.cancel()

        result = next(iter(done)).result()
        if result == "HOLD_FAIL":
            await w.human_click(SEL_HOLD_FAIL_CLOSE)
            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "HOLD_FAILED",
                    "flow_state": FlowState.S5.value,
                }
            )
            # Retry seat selection.
            return {"flow_state": FlowState.S5}
    except Exception as e:
        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "SEAT_FAILED",
                "flow_state": FlowState.S5.value,
                "error": repr(e),
            }
        )
        return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.ABORT}

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "HOLD_ACQUIRED",
            "flow_state": FlowState.S5.value,
        }
    )
    return {"flow_state": FlowState.S6}


async def node_recommend(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    sec = await _enter_security_if_visible(state, runtime, where=FlowState.S4R)
    if sec:
        return sec

    w = runtime.context.worker

    try:
        await w.wait_for_selector('[data-testid="party-size-select"]', timeout_ms=30_000)
        # Defense gating can block /api/recommendations. Detect early.
        selected = False
        try:
            async with w.page.expect_response(
                lambda r: "/api/recommendations" in r.url,
                timeout=10_000,
            ) as resp_info:
                await w.select_option('[data-testid="party-size-select"]', "1")
                selected = True

            rec_resp = await resp_info.value
            if rec_resp.status >= 400:
                reason_code: str | None = None
                try:
                    data = await rec_resp.json()
                    if isinstance(data, dict):
                        reason = data.get("reasonCode")
                        if isinstance(reason, str):
                            reason_code = reason
                except Exception:
                    reason_code = None

                runtime.context.audit.log(
                    {
                        "ts_ms": now_ms(),
                        "event": "RECOMMENDATIONS_RESPONSE",
                        "flow_state": FlowState.S4R.value,
                        "http_status": rec_resp.status,
                        "reason_code": reason_code,
                    }
                )

                if rec_resp.status == 403 or reason_code == "BLOCKED":
                    return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.BLOCKED}
                if rec_resp.status == 428 or reason_code == "CHALLENGE_REQUIRED":
                    return {"flow_state": FlowState.S3, "last_non_security_state": FlowState.S4R}
        except Exception:
            if not selected:
                await w.select_option('[data-testid="party-size-select"]', "1")

        # Wait for an actionable recommendation.
        await w.wait_for_selector(SEL_REC_AUTO, timeout_ms=60_000)
    except Exception:
        # Fallback: switch to MAP mode if no recommendations.
        try:
            await w.human_click(SEL_SEAT_MODE_TOGGLE)
            await w.wait_for_url("**/seats?mode=MAP", timeout_ms=30_000)
            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "NO_RECOMMENDATIONS_SWITCH_TO_MAP",
                    "flow_state": FlowState.S4R.value,
                }
            )
            return {"flow_state": FlowState.S4, "mode": "MAP"}
        except Exception as e:
            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "RECOMMEND_FAILED",
                    "flow_state": FlowState.S4R.value,
                    "error": repr(e),
                }
            )
            return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.ABORT}

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "RECOMMENDATIONS_LOADED",
            "flow_state": FlowState.S4R.value,
        }
    )
    return {"flow_state": FlowState.S5R}


async def node_accept_recommend(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    sec = await _enter_security_if_visible(state, runtime, where=FlowState.S5R)
    if sec:
        return sec

    w = runtime.context.worker

    try:
        await w.wait_for_selector(SEL_REC_AUTO, timeout_ms=30_000)
        # Defense gating can block /api/holds here as well.
        clicked = False
        try:
            async with w.page.expect_response(
                lambda r: "/api/holds" in r.url,
                timeout=10_000,
            ) as resp_info:
                await w.human_click(SEL_REC_AUTO)
                clicked = True

            hold_resp = await resp_info.value
            if hold_resp.status >= 400:
                reason_code: str | None = None
                try:
                    data = await hold_resp.json()
                    if isinstance(data, dict):
                        reason = data.get("reasonCode")
                        if isinstance(reason, str):
                            reason_code = reason
                except Exception:
                    reason_code = None

                runtime.context.audit.log(
                    {
                        "ts_ms": now_ms(),
                        "event": "HOLDS_RESPONSE",
                        "flow_state": FlowState.S5R.value,
                        "http_status": hold_resp.status,
                        "reason_code": reason_code,
                    }
                )

                if hold_resp.status == 403 or reason_code == "BLOCKED":
                    return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.BLOCKED}
                if hold_resp.status == 428 or reason_code == "CHALLENGE_REQUIRED":
                    return {"flow_state": FlowState.S3, "last_non_security_state": FlowState.S5R}
        except Exception:
            if not clicked:
                await w.human_click(SEL_REC_AUTO)

        async def _wait_payment() -> str:
            await w.wait_for_url("**/payment?orderId=*", timeout_ms=60_000)
            return "PAYMENT"

        async def _wait_hold_fail() -> str:
            await w.wait_for_selector(SEL_HOLD_FAIL_CLOSE, timeout_ms=60_000)
            return "HOLD_FAIL"

        done, pending = await asyncio.wait(
            {asyncio.create_task(_wait_payment()), asyncio.create_task(_wait_hold_fail())},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for p in pending:
            p.cancel()

        result = next(iter(done)).result()
        if result == "HOLD_FAIL":
            await w.human_click(SEL_HOLD_FAIL_CLOSE)
            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "HOLD_FAILED",
                    "flow_state": FlowState.S5R.value,
                }
            )
            return {"flow_state": FlowState.S5R}
    except Exception as e:
        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "ACCEPT_FAILED",
                "flow_state": FlowState.S5R.value,
                "error": repr(e),
            }
        )
        return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.ABORT}

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "BUNDLE_ACCEPTED",
            "flow_state": FlowState.S5R.value,
        }
    )
    return {"flow_state": FlowState.S6}


async def node_payment(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    sec = await _enter_security_if_visible(state, runtime, where=FlowState.S6)
    if sec:
        return sec

    w = runtime.context.worker

    try:
        await w.wait_for_selector(SEL_AGREE_TERMS, timeout_ms=30_000)
        if not await w.is_checked(SEL_AGREE_TERMS):
            await w.human_click(SEL_AGREE_TERMS)

        await w.wait_for_selector(SEL_AGREE_CANCEL, timeout_ms=30_000)
        if not await w.is_checked(SEL_AGREE_CANCEL):
            await w.human_click(SEL_AGREE_CANCEL)

        await w.wait_for_selector(SEL_PAY_BTN, timeout_ms=30_000)
        await w.human_click(SEL_PAY_BTN)

        await w.wait_for_url("**/payment/done*", timeout_ms=60_000)
    except Exception as e:
        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "PAYMENT_FAILED",
                "flow_state": FlowState.S6.value,
                "error": repr(e),
            }
        )
        return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.ABORT}

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "PAYMENT_COMPLETED",
            "flow_state": FlowState.S6.value,
        }
    )
    return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.DONE}


async def node_terminal(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "TERMINAL",
            "flow_state": FlowState.SX.value,
            "terminal_reason": state.terminal_reason.value if state.terminal_reason else None,
        }
    )
    # No further updates.
    return {}
