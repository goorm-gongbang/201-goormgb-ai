from __future__ import annotations

import asyncio
import uuid
from typing import Any

from langgraph.runtime import Runtime

from traffic_master_ai.common.models.states import FlowState, TerminalReason

from ..contracts.api import (
    API_PATH_HOLDS,
    API_PATH_PAYMENTS,
    API_PATH_RECOMMENDATIONS,
    API_PATH_SEATS_SUFFIX,
    API_PATH_ZONES_PREFIX,
    URL_GLOB_PAYMENT,
    URL_GLOB_PAYMENT_DONE,
    URL_GLOB_QUEUE_PAGE,
    URL_GLOB_SEATS_MAP,
    URL_GLOB_SEATS_RECOMMEND,
)
from ..contracts.defense import (
    is_blocked_response,
    is_challenge_required_response,
)
from ..contracts.selectors import (
    SEL_AGREE_CANCEL,
    SEL_AGREE_TERMS,
    SEL_BOOKING_BTN,
    SEL_SECURITY_CHALLENGE_START,
    SEL_SECURITY_GLOVE_CATCH,
    SEL_HOLD_FAIL_CLOSE,
    SEL_MAP_BOOK_BTN,
    SEL_PARTY_SIZE_SELECT_MAP,
    SEL_PARTY_SIZE_SELECT_RECOMMEND,
    SEL_PAY_BTN,
    SEL_REC_AUTO,
    SEL_SEAT_AVAILABLE,
    SEL_SEAT_GRID,
    SEL_SEAT_MODE_TOGGLE,
    SEL_SECURITY_ERROR,
    SEL_SECURITY_INPUT,
    SEL_SECURITY_OVERLAY,
    SEL_SECURITY_RETRY,
    SEL_SECURITY_SUBMIT,
    SEL_ZONE_ITEM,
)
from ..contracts.storage import (
    TM_PREFERENCES_KEY,
    TM_SESSION_ID_KEY,
    TM_VQA_PASSED_SESSION_ID_KEY,
    build_default_tm_preferences,
)
from ..logging.audit import now_ms
from ..security.arithmetic import ArithmeticParseError, solve_arithmetic_prompt
from ..security.catch_ball import (
    build_fail_telemetry,
    build_pass_telemetry,
    resolve_fail_profile,
    resolve_pass_profile,
)
from ..state import AgentState
from .context import AgentContext


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
    await w.set_local_storage(TM_SESSION_ID_KEY, session_id)

    # Ensure Pre-Entry preference matches agent mode (controls queue nextUrl mode).
    prefs = build_default_tm_preferences(state.mode)
    await w.set_local_storage_json(TM_PREFERENCES_KEY, prefs)
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
        await w.wait_for_url(URL_GLOB_QUEUE_PAGE, timeout_ms=60_000)
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
            await w.wait_for_url(URL_GLOB_SEATS_MAP, timeout_ms=180_000)
            next_state = FlowState.S4
        else:
            await w.wait_for_url(URL_GLOB_SEATS_RECOMMEND, timeout_ms=180_000)
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


async def _run_catch_ball_api_mode(
    state: AgentState,
    runtime: Runtime[AgentContext],
    *,
    mode: str,
    strategy: str,
) -> bool:
    """Drive catch-ball verification through backend API for deterministic pass/fail.

    Used in Step4 ST4-1 to reproduce challenge outcomes without external AI/OCR.
    """
    w = runtime.context.worker
    cfg = runtime.context.cfg
    session_id = state.session_id or (await w.get_local_storage(TM_SESSION_ID_KEY)) or ""
    if not session_id:
        raise RuntimeError("missing session_id for catch-ball challenge flow")

    challenge_url = f"{cfg.frontend_url}/api/security/challenge"
    verify_url = f"{cfg.frontend_url}/api/security/verify"

    issue_resp = await w.page.request.get(challenge_url, params={"sessionId": session_id})
    if issue_resp.status != 200:
        raise RuntimeError(f"challenge issue failed: status={issue_resp.status}")

    issue_body: dict[str, Any] = await issue_resp.json()
    challenge_id = str(issue_body.get("challengeId", ""))
    challenge_token = str(issue_body.get("challengeToken", ""))
    attempt_limit = int(issue_body.get("attemptLimit", 2))
    if not challenge_id:
        raise RuntimeError("challenge issue response missing challengeId")

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "CHALLENGE_MODE_SELECTED",
            "flow_state": FlowState.S3.value,
            "challenge_mode": mode,
            "challenge_solver_strategy": strategy,
            "challenge_type": issue_body.get("type", "UNKNOWN"),
            "challenge_id": challenge_id,
            "attempt_limit": attempt_limit,
        }
    )

    should_pass = mode == "pass"
    token_tamper = strategy == "token_tamper"
    verify_attempts = 1 if (should_pass or token_tamper) else max(1, attempt_limit)
    final_pass = False
    last_payload: dict[str, Any] | None = None
    for attempt in range(1, verify_attempts + 1):
        started = now_ms()
        ts = now_ms()
        if token_tamper:
            telemetry = build_pass_telemetry(ts, profile=resolve_pass_profile("api_fast"))
            answer = "__VQA_PASS__"
            sent_token = f"{challenge_token}.tampered"
        elif should_pass:
            telemetry = build_pass_telemetry(ts, profile=resolve_pass_profile(strategy))
            answer = "__VQA_PASS__"
            sent_token = challenge_token
        else:
            telemetry = build_fail_telemetry(ts, profile=resolve_fail_profile(strategy))
            answer = "__VQA_FAIL__"
            sent_token = challenge_token
        payload: dict[str, Any] = {
            "challengeId": challenge_id,
            "sessionId": session_id,
            "challengeToken": sent_token,
            "answer": answer,
            "telemetry": telemetry,
        }
        last_payload = payload
        verify_resp = await w.page.request.post(
            verify_url,
            headers={"content-type": "application/json"},
            data=payload,
        )

        verify_body: dict[str, Any] = {}
        if verify_resp.status != 200:
            try:
                maybe = await verify_resp.json()
                if isinstance(maybe, dict):
                    verify_body = maybe
            except Exception:
                verify_body = {}
            result = "HTTP_ERROR"
            blocked = bool(verify_body.get("blocked", verify_resp.status == 403))
        else:
            verify_body = await verify_resp.json()
            result = str(verify_body.get("result", "FAIL")).upper()
            blocked = bool(verify_body.get("blocked", False))

        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "CHALLENGE_ATTEMPT",
                "flow_state": FlowState.S3.value,
                "challenge_mode": mode,
                "challenge_solver_strategy": strategy,
                "challenge_id": challenge_id,
                "challenge_attempt": attempt,
                "challenge_result": result,
                "blocked": blocked,
                "http_status": verify_resp.status,
                "remaining_attempts": verify_body.get("remainingAttempts"),
                "reason_code": verify_body.get("reasonCode"),
                "challenge_solver_latency_ms": now_ms() - started,
            }
        )

        if verify_resp.status != 200:
            final_pass = False
            break

        if result == "PASS":
            final_pass = True
            break
        if blocked:
            final_pass = False
            break

    if final_pass:
        # SecurityTrigger gate bypass: mark once so seats page does not pop overlay again after reload.
        await w.set_local_storage(TM_VQA_PASSED_SESSION_ID_KEY, session_id)
        await w.set_local_storage("TM_VQA_PASSED_ONCE", "1")
        await w.reload()
        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "CHALLENGE_PASSED",
                "flow_state": FlowState.S3.value,
                "challenge_mode": mode,
                "challenge_solver_strategy": strategy,
                "challenge_id": challenge_id,
            }
        )
        return True

    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "CHALLENGE_FAILED",
            "flow_state": FlowState.S3.value,
            "challenge_mode": mode,
            "challenge_solver_strategy": strategy,
            "challenge_id": challenge_id,
            "last_payload_has_telemetry": bool(last_payload and last_payload.get("telemetry")),
        }
    )
    return False


async def _run_catch_ball_ui_solver(state: AgentState, runtime: Runtime[AgentContext]) -> bool:
    """Solve catch-ball by real UI interaction (no direct /verify forge)."""
    w = runtime.context.worker
    page = w.page
    runtime.context.audit.log(
        {
            "ts_ms": now_ms(),
            "event": "CHALLENGE_UI_SOLVER_START",
            "flow_state": FlowState.S3.value,
        }
    )

    async def _click_start_if_needed() -> bool:
        try:
            await w.wait_for_selector(SEL_SECURITY_CHALLENGE_START, timeout_ms=5_000)
            await w.human_click(SEL_SECURITY_CHALLENGE_START, timeout_ms=5_000)
            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "CHALLENGE_UI_SOLVER_START_CLICKED",
                    "flow_state": FlowState.S3.value,
                }
            )
            return True
        except Exception:
            return False

    async def _snapshot_targets() -> dict[str, Any] | None:
        return await page.evaluate(
            """() => {
              const root = document.querySelector('[data-testid="security-overlay"]');
              if (!root) return null;
              const glove = root.querySelector('[data-testid="catchball-glove"]');
              const target = root.querySelector('[data-testid="catchball-landing-marker"]');
              const play = root.querySelector('[data-testid="catchball-playfield"]');
              if (!play) return null;
              if (!glove || !target) return null;

              const g = glove.getBoundingClientRect();
              const t = target.getBoundingClientRect();
              const p = play.getBoundingClientRect();
              return {
                glove: { x: g.left + g.width / 2, y: g.top + g.height / 2 },
                target: { x: t.left + t.width / 2, y: t.top + t.height / 2 },
                play: { left: p.left, top: p.top, right: p.right, bottom: p.bottom },
              };
            }"""
        )

    async def _snapshot_timing() -> dict[str, Any]:
        snap = await page.evaluate(
            """() => {
              const root = document.querySelector('[data-testid="security-overlay"]');
              const play = root?.querySelector('[data-testid="catchball-playfield"]');
              const phaseRow = Array.from(root?.querySelectorAll('p') ?? []).find((el) =>
                (el.textContent ?? '').trim().startsWith('Phase:')
              );
              const phaseLabel = phaseRow?.querySelector('span')?.textContent?.trim() ?? null;
              const indicatorCount = root ? root.querySelectorAll('[data-testid="catchball-indicator"]').length : 0;
              const windowCount = root ? root.querySelectorAll('[data-testid="catchball-window"]').length : 0;
              const indicator = play?.querySelector('[data-testid="catchball-indicator"]');
              const windowEl = play?.querySelector('[data-testid="catchball-window"]');
              if (!indicator || !windowEl) return { ready: false, indicatorCount, windowCount, phaseLabel };
              const i = indicator.getBoundingClientRect();
              const w = windowEl.getBoundingClientRect();
              const centerX = i.left + i.width / 2;
              return {
                ready: true,
                phaseLabel,
                indicatorCount,
                windowCount,
                indicatorLeft: i.left,
                centerX,
                windowLeft: w.left,
                windowRight: w.right,
                inWindow: centerX >= w.left && centerX <= w.right,
              };
            }"""
        )
        return snap if isinstance(snap, dict) else {"ready": False}

    async def _play_round(round_idx: int) -> bool:
        start_clicked = await _click_start_if_needed()
        await w.wait_for_selector(SEL_SECURITY_GLOVE_CATCH, timeout_ms=8_000)
        if not start_clicked and await w.is_visible(SEL_SECURITY_CHALLENGE_START):
            raise RuntimeError("ui_solver: start button visible but click failed")
        round_start_ms = now_ms()
        phase_active = False
        for _ in range(360):
            phase_snap = await _snapshot_timing()
            if phase_snap.get("phaseLabel") == "ACTIVE_PLAY":
                phase_active = True
                break
            await page.wait_for_timeout(10)
        if not phase_active:
            raise RuntimeError("ui_solver: phase did not transition to ACTIVE_PLAY")

        # Wait until the indicator actually starts moving (ACTIVE_PLAY + pitch start).
        motion_start: float | None = None
        motion_observed = False
        motion_snapshot: dict[str, Any] | None = None
        for _ in range(180):
            snap = await _snapshot_timing()
            if snap.get("ready"):
                cx = float(snap.get("centerX", 0.0))
                if motion_start is None:
                    motion_start = cx
                elif abs(cx - motion_start) >= 10.0:
                    motion_observed = True
                    motion_snapshot = snap
                    break
            await page.wait_for_timeout(20)
        runtime.context.audit.log(
            {
                "ts_ms": now_ms(),
                "event": "CHALLENGE_UI_SOLVER_MOTION_CHECK",
                "flow_state": FlowState.S3.value,
                "ui_solver_round": round_idx,
                "motion_observed": motion_observed,
                "motion_snapshot": motion_snapshot,
            }
        )

        targets = await _snapshot_targets()
        if not targets:
            raise RuntimeError("ui_solver: unable to resolve glove/target nodes")

        sx = float(targets["glove"]["x"])
        sy = float(targets["glove"]["y"])
        tx = float(targets["target"]["x"])
        ty = float(targets["target"]["y"])
        left = float(targets["play"]["left"])
        top = float(targets["play"]["top"])
        right = float(targets["play"]["right"])
        bottom = float(targets["play"]["bottom"])

        await page.mouse.move(sx, sy)
        await page.mouse.down()

        # Human-like curved path with light overshoot/correction so telemetry curvature
        # is above backend minimum and looks less like a linear bot drag.
        dx = tx - sx
        dy = ty - sy
        dist = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux = dx / dist
        uy = dy / dist
        nxv = -uy
        nyv = ux
        arc = min(24.0, max(8.0, dist * 0.13))
        overshoot = min(18.0, max(6.0, dist * 0.09))
        waypoints = [
            (sx, sy),
            (sx + dx * 0.34 + nxv * arc, sy + dy * 0.34 + nyv * arc),
            (sx + dx * 0.72 - nxv * (arc * 0.45), sy + dy * 0.72 - nyv * (arc * 0.45)),
            (tx + ux * overshoot, ty + uy * overshoot),
            (tx, ty),
        ]
        segment_steps = (3, 4, 3, 4)
        for seg_idx in range(len(waypoints) - 1):
            ax, ay = waypoints[seg_idx]
            bx, by = waypoints[seg_idx + 1]
            steps = segment_steps[seg_idx]
            for i in range(1, steps + 1):
                t = i / steps
                px = ax + (bx - ax) * t
                py = ay + (by - ay) * t
                px = max(left + 8.0, min(right - 8.0, px))
                py = max(top + 8.0, min(bottom - 8.0, py))
                await page.mouse.move(px, py)
                await page.wait_for_timeout(24)
        await page.mouse.up()

        # Prefer runtime window sync: click when indicator center enters red zone.
        # Fallback to conservative timeline only when selector-based sync misses.
        used_runtime_timing = False
        timing_snapshot: dict[str, Any] | None = None
        timing_ready_count = 0
        timing_in_window_count = 0
        timing_min_center: float | None = None
        timing_max_center: float | None = None
        for _ in range(260):
            timing_snapshot = await _snapshot_timing()
            if timing_snapshot.get("ready"):
                timing_ready_count += 1
                center_x = float(timing_snapshot.get("centerX", 0.0))
                timing_min_center = center_x if timing_min_center is None else min(timing_min_center, center_x)
                timing_max_center = center_x if timing_max_center is None else max(timing_max_center, center_x)
            if timing_snapshot.get("ready") and timing_snapshot.get("inWindow"):
                timing_in_window_count += 1
                used_runtime_timing = True
                break
            await page.wait_for_timeout(10)

        if not used_runtime_timing:
            target_click_at = round_start_ms + 3590
            wait_ms = max(0, target_click_at - now_ms())
            if wait_ms > 0:
                await page.wait_for_timeout(wait_ms)
            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "CHALLENGE_UI_SOLVER_TIMING_FALLBACK",
                    "flow_state": FlowState.S3.value,
                    "ui_solver_round": round_idx,
                    "timing_snapshot": timing_snapshot,
                    "timing_ready_count": timing_ready_count,
                    "timing_in_window_count": timing_in_window_count,
                    "timing_min_center": timing_min_center,
                    "timing_max_center": timing_max_center,
                }
            )
        await page.locator(SEL_SECURITY_GLOVE_CATCH).first.click(timeout=4_000, force=True)
        if used_runtime_timing:
            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "CHALLENGE_UI_SOLVER_TIMING_SYNCED",
                    "flow_state": FlowState.S3.value,
                    "ui_solver_round": round_idx,
                    "timing_snapshot": timing_snapshot,
                    "timing_ready_count": timing_ready_count,
                    "timing_in_window_count": timing_in_window_count,
                    "timing_min_center": timing_min_center,
                    "timing_max_center": timing_max_center,
                }
            )

        try:
            await page.wait_for_selector(SEL_SECURITY_OVERLAY, state="detached", timeout=12_000)
            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "CHALLENGE_UI_SOLVER_PASSED",
                    "flow_state": FlowState.S3.value,
                    "ui_solver_round": round_idx,
                }
            )
            return True
        except Exception:
            phase_snapshot = await page.evaluate(
                """() => {
                  const root = document.querySelector('[data-testid="security-overlay"]');
                  if (!root) return { overlayVisible: false };
                  const title = root.querySelector('h3');
                  const status = root.querySelector('.text-sm.text-slate-300');
                  const retry = root.querySelector('[data-testid="catchball-retry"]');
                  const err = root.querySelector('[data-testid="security-error"]');
                  return {
                    overlayVisible: true,
                    title: title?.textContent ?? null,
                    statusText: status?.textContent ?? null,
                    retryVisible: !!retry,
                    startVisible: !!root.querySelector('[data-testid="catchball-start"]'),
                    errorText: err?.textContent ?? null,
                  };
                }"""
            )
            if await w.is_visible(SEL_SECURITY_RETRY):
                runtime.context.audit.log(
                    {
                        "ts_ms": now_ms(),
                        "event": "CHALLENGE_UI_SOLVER_RETRY_REQUIRED",
                        "flow_state": FlowState.S3.value,
                        "ui_solver_round": round_idx,
                        "snapshot": phase_snapshot,
                    }
                )
                return False
            if await w.is_visible(SEL_SECURITY_ERROR):
                msg = await w.get_inner_text(SEL_SECURITY_ERROR)
                raise RuntimeError(f"ui_solver verify rejected: {msg}")
            # Overlay still visible but no retry/error label yet -> treat as failure.
            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "CHALLENGE_UI_SOLVER_NO_RESULT",
                    "flow_state": FlowState.S3.value,
                    "ui_solver_round": round_idx,
                    "snapshot": phase_snapshot,
                }
            )
            return False

    max_rounds = 2
    for round_idx in range(1, max_rounds + 1):
        passed = await _play_round(round_idx)
        if passed:
            return True
        if round_idx < max_rounds and await w.is_visible(SEL_SECURITY_RETRY):
            await w.human_click(SEL_SECURITY_RETRY, timeout_ms=4_000)
            await page.wait_for_timeout(80)
            continue
        break

    return False


async def node_security(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    w = runtime.context.worker

    try:
        await w.wait_for_selector(SEL_SECURITY_OVERLAY, timeout_ms=30_000)
        has_legacy_input = await w.is_visible(SEL_SECURITY_INPUT)

        if has_legacy_input:
            await w.wait_for_selector(SEL_SECURITY_INPUT, timeout_ms=30_000)
            overlay_text = await w.get_inner_text(SEL_SECURITY_OVERLAY)
            try:
                answer = solve_arithmetic_prompt(overlay_text)
            except ArithmeticParseError:
                # Current backend prompt is fixed; safe fallback.
                answer = "7"
            input_loc = w.page.locator(SEL_SECURITY_INPUT).first
            await input_loc.focus()
            try:
                await input_loc.fill("")
            except Exception:
                pass
            await input_loc.fill(answer)
            submit_loc = w.page.locator(SEL_SECURITY_SUBMIT).first

            try:
                await w.page.wait_for_function(
                    "(sel) => { const el = document.querySelector(sel); return !!el && !el.disabled; }",
                    SEL_SECURITY_SUBMIT,
                    timeout=1_200,
                )
            except Exception:
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
        else:
            mode = runtime.context.cfg.challenge_mode
            if mode == "auto":
                raise RuntimeError("catch_ball detected but challenge_mode=auto (no solver selected)")
            strategy = runtime.context.cfg.challenge_strategy
            if strategy in ("ui_solver", "ui_solver_stealth"):
                passed = await _run_catch_ball_ui_solver(state, runtime)
            else:
                passed = await _run_catch_ball_api_mode(
                    state,
                    runtime,
                    mode=mode,
                    strategy=strategy,
                )
            if not passed:
                return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.BLOCKED}
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
        await w.wait_for_selector(SEL_PARTY_SIZE_SELECT_MAP, timeout_ms=30_000)
        await w.select_option(SEL_PARTY_SIZE_SELECT_MAP, "1")

        # Wait for zones (may require security first in TM_TEST_MODE).
        await w.wait_for_selector(SEL_ZONE_ITEM, timeout_ms=60_000)

        # After zone click, the UI fetches /api/zones/{id}/seats. In TM_TEST_MODE,
        # Defense gating can respond with BLOCKED / CHALLENGE_REQUIRED. Listen for
        # that response deterministically (Playwright Python uses expect_response).
        clicked = False
        try:
            async with w.page.expect_response(
                lambda r: (API_PATH_ZONES_PREFIX in r.url) and (API_PATH_SEATS_SUFFIX in r.url),
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

            if is_blocked_response(status, reason_code):
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

            if is_challenge_required_response(status, reason_code):
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

        async def _wait_map_book_enabled(timeout_ms: int) -> bool:
            try:
                await w.page.wait_for_function(
                    """() => {
                        const byTestId = document.querySelector('[data-testid="map-booking-button"]');
                        const byId = document.querySelector('#booking-button-map');
                        const el = byTestId || byId;
                        return !!el && !el.disabled;
                    }""",
                    timeout=timeout_ms,
                )
                return True
            except Exception:
                return False

        # Select seat(s) until map booking button becomes enabled.
        seat_locator = w.page.locator(SEL_SEAT_AVAILABLE)
        seat_count = await seat_locator.count()
        max_seat_attempts = max(1, min(seat_count, 6))
        map_book_enabled = False
        for idx in range(max_seat_attempts):
            seat_loc = seat_locator.nth(idx)
            seat_testid = await seat_loc.get_attribute("data-testid")
            if seat_testid:
                await w.human_click(f'[data-testid="{seat_testid}"]')
            else:
                await seat_loc.click()
            if await _wait_map_book_enabled(timeout_ms=1_500):
                map_book_enabled = True
                break

        if not map_book_enabled:
            runtime.context.audit.log(
                {
                    "ts_ms": now_ms(),
                    "event": "MAP_BOOK_BUTTON_DISABLED",
                    "flow_state": FlowState.S5.value,
                    "seat_attempts": max_seat_attempts,
                }
            )
            raise RuntimeError("map booking button did not enable after seat selection attempts")

        await w.wait_for_selector(SEL_MAP_BOOK_BTN, timeout_ms=10_000)
        # Defense gating can block /api/holds. Detect quickly to avoid long UI timeouts.
        clicked = False
        try:
            async with w.page.expect_response(
                lambda r: API_PATH_HOLDS in r.url,
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

                if is_blocked_response(hold_resp.status, reason_code):
                    return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.BLOCKED}
                if is_challenge_required_response(hold_resp.status, reason_code):
                    return {"flow_state": FlowState.S3, "last_non_security_state": FlowState.S5}
        except Exception:
            if not clicked:
                await w.human_click(SEL_MAP_BOOK_BTN)

        # Either payment navigation, or hold failure modal.
        async def _wait_payment() -> str:
            await w.wait_for_url(URL_GLOB_PAYMENT, timeout_ms=60_000)
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
        await w.wait_for_selector(SEL_PARTY_SIZE_SELECT_RECOMMEND, timeout_ms=30_000)
        # Defense gating can block /api/recommendations. Detect early.
        selected = False
        try:
            async with w.page.expect_response(
                lambda r: API_PATH_RECOMMENDATIONS in r.url,
                timeout=10_000,
            ) as resp_info:
                await w.select_option(SEL_PARTY_SIZE_SELECT_RECOMMEND, "1")
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

                if is_blocked_response(rec_resp.status, reason_code):
                    return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.BLOCKED}
                if is_challenge_required_response(rec_resp.status, reason_code):
                    return {"flow_state": FlowState.S3, "last_non_security_state": FlowState.S4R}
        except Exception:
            if not selected:
                await w.select_option(SEL_PARTY_SIZE_SELECT_RECOMMEND, "1")

        # Wait for an actionable recommendation.
        await w.wait_for_selector(SEL_REC_AUTO, timeout_ms=60_000)
    except Exception:
        # Fallback: switch to MAP mode if no recommendations.
        try:
            await w.human_click(SEL_SEAT_MODE_TOGGLE)
            await w.wait_for_url(URL_GLOB_SEATS_MAP, timeout_ms=30_000)
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
                lambda r: API_PATH_HOLDS in r.url,
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

                if is_blocked_response(hold_resp.status, reason_code):
                    return {"flow_state": FlowState.SX, "terminal_reason": TerminalReason.BLOCKED}
                if is_challenge_required_response(hold_resp.status, reason_code):
                    return {"flow_state": FlowState.S3, "last_non_security_state": FlowState.S5R}
        except Exception:
            if not clicked:
                await w.human_click(SEL_REC_AUTO)

        async def _wait_payment() -> str:
            await w.wait_for_url(URL_GLOB_PAYMENT, timeout_ms=60_000)
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

        max_payment_attempts = 3
        payment_succeeded = False
        last_failure: str | None = None

        for attempt in range(1, max_payment_attempts + 1):
            await w.wait_for_selector(SEL_PAY_BTN, timeout_ms=30_000)
            clicked = False
            try:
                async with w.page.expect_response(
                    lambda r: API_PATH_PAYMENTS in r.url,
                    timeout=15_000,
                ) as resp_info:
                    await w.human_click(SEL_PAY_BTN)
                    clicked = True

                pay_resp = await resp_info.value
                pay_http = pay_resp.status
                pay_status: str | None = None
                reason_code: str | None = None
                try:
                    payload = await pay_resp.json()
                    if isinstance(payload, dict):
                        st = payload.get("status")
                        rc = payload.get("reasonCode")
                        if isinstance(st, str):
                            pay_status = st
                        if isinstance(rc, str):
                            reason_code = rc
                except Exception:
                    pass

                runtime.context.audit.log(
                    {
                        "ts_ms": now_ms(),
                        "event": "PAYMENT_API_RESPONSE",
                        "flow_state": FlowState.S6.value,
                        "attempt": attempt,
                        "http_status": pay_http,
                        "status": pay_status,
                        "reason_code": reason_code,
                    }
                )

                if pay_http < 400 and pay_status == "SUCCEEDED":
                    payment_succeeded = True
                    break

                last_failure = reason_code or pay_status or f"HTTP_{pay_http}"
            except Exception as e:
                if not clicked:
                    try:
                        await w.human_click(SEL_PAY_BTN)
                    except Exception:
                        pass
                last_failure = repr(e)

            if attempt < max_payment_attempts:
                await asyncio.sleep(0.35)

        if not payment_succeeded:
            raise RuntimeError(f"payment did not succeed after retries: {last_failure}")

        await w.wait_for_url(URL_GLOB_PAYMENT_DONE, timeout_ms=30_000)
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
