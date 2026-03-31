"""Catch-ball challenge payload helpers for attack-agent experiments.

This module intentionally avoids external model dependencies.
It builds deterministic telemetry payloads to drive pass/fail branches.
"""

from __future__ import annotations

from typing import Any

PASS_PROFILES: tuple[str, ...] = ("api_fast", "humanish_pass", "edge_pass")
FAIL_PROFILES: tuple[str, ...] = ("botlike_fail", "timing_fail", "hard_fail")


def resolve_pass_profile(strategy: str) -> str:
    return strategy if strategy in PASS_PROFILES else "api_fast"


def resolve_fail_profile(strategy: str) -> str:
    return strategy if strategy in FAIL_PROFILES else "botlike_fail"


def build_pass_telemetry(now_ms: int, *, profile: str = "api_fast") -> dict[str, Any]:
    """Return a telemetry payload that satisfies current backend checks.

    Backend checks (SecurityService.validateTelemetry):
    - position_ok/timing_ok must be true
    - distance_to_target <= position.catch_radius
    - click_ts in [indicator_enter_ts, indicator_exit_ts]
    - drag_path length >= 5 with strictly increasing `t`
    - per-segment speed <= 10 px/ms
    """
    indicator_enter = now_ms + 120
    indicator_exit = indicator_enter + 240
    click_ts = indicator_enter + 110

    if profile == "humanish_pass":
        drag_path = [
            {"x": 628.0, "y": 424.0, "t": 0},
            {"x": 611.0, "y": 407.0, "t": 18},
            {"x": 588.0, "y": 388.0, "t": 37},
            {"x": 564.0, "y": 370.0, "t": 56},
            {"x": 540.0, "y": 352.0, "t": 76},
            {"x": 521.0, "y": 340.0, "t": 94},
            {"x": 512.0, "y": 334.0, "t": 113},
        ]
        total_distance = 181.0
        linear_distance = 128.0
        curvature = 1.41
        overshoot = 1
        correction = 3
        distance_to_target = 14.2
    elif profile == "edge_pass":
        # Boundary pass: valid but close to backend threshold edges.
        # - near timing window end
        # - near catch radius upper bound
        click_ts = indicator_exit - 4
        drag_path = [
            {"x": 620.0, "y": 418.0, "t": 0},
            {"x": 606.0, "y": 406.0, "t": 22},
            {"x": 588.0, "y": 392.0, "t": 44},
            {"x": 566.0, "y": 374.0, "t": 68},
            {"x": 548.0, "y": 360.0, "t": 92},
            {"x": 533.0, "y": 348.0, "t": 116},
            {"x": 522.0, "y": 340.0, "t": 138},
        ]
        total_distance = 139.0
        linear_distance = 112.0
        curvature = 1.24
        overshoot = 0
        correction = 1
        distance_to_target = 37.6
    else:
        # t is relative and strictly increasing; dt=20ms keeps speed comfortably low.
        drag_path = [
            {"x": 620.0, "y": 420.0, "t": 0},
            {"x": 600.0, "y": 402.0, "t": 20},
            {"x": 575.0, "y": 380.0, "t": 40},
            {"x": 548.0, "y": 360.0, "t": 60},
            {"x": 526.0, "y": 342.0, "t": 80},
            {"x": 512.0, "y": 334.0, "t": 100},
        ]
        total_distance = 164.0
        linear_distance = 122.0
        curvature = 1.34
        overshoot = 1
        correction = 2
        distance_to_target = 14.2

    return {
        "position_ok": True,
        "timing_ok": True,
        "distance_to_target": distance_to_target,
        "position": {
            "catch_radius": 38.0,
            "final_glove_center": {"x": 512.0, "y": 334.0},
            "ball_landing_point": {"x": 520.0, "y": 338.0},
        },
        "timing": {
            "indicator_enter_ts": indicator_enter,
            "indicator_exit_ts": indicator_exit,
            "click_ts": click_ts,
        },
        "drag": {
            "drag_path": drag_path,
            "total_distance": total_distance,
            "linear_distance": linear_distance,
            "curvature": curvature,
            "overshoot_count": overshoot,
            "correction_count": correction,
        },
    }


def build_fail_telemetry(now_ms: int, *, profile: str = "botlike_fail") -> dict[str, Any]:
    """Return a telemetry payload that deterministically fails validation."""
    if profile == "botlike_fail":
        # Position/timing look superficially valid but drag path violates physics.
        return {
            "position_ok": True,
            "timing_ok": True,
            "distance_to_target": 9.0,
            "position": {
                "catch_radius": 38.0,
                "final_glove_center": {"x": 520.0, "y": 338.0},
                "ball_landing_point": {"x": 520.0, "y": 338.0},
            },
            "timing": {
                "indicator_enter_ts": now_ms + 100,
                "indicator_exit_ts": now_ms + 280,
                "click_ts": now_ms + 160,
            },
            "drag": {
                # dt=1 with huge jumps -> impossible speed
                "drag_path": [
                    {"x": 100.0, "y": 100.0, "t": 0},
                    {"x": 500.0, "y": 320.0, "t": 1},
                    {"x": 520.0, "y": 338.0, "t": 2},
                    {"x": 530.0, "y": 346.0, "t": 3},
                    {"x": 520.0, "y": 338.0, "t": 4},
                ],
                "total_distance": 900.0,
                "linear_distance": 500.0,
                "curvature": 1.8,
                "overshoot_count": 0,
                "correction_count": 0,
            },
        }
    if profile == "timing_fail":
        # Physics/position are valid but click is outside indicator window.
        return {
            "position_ok": True,
            "timing_ok": False,
            "distance_to_target": 15.0,
            "position": {
                "catch_radius": 38.0,
                "final_glove_center": {"x": 514.0, "y": 336.0},
                "ball_landing_point": {"x": 520.0, "y": 338.0},
            },
            "timing": {
                "indicator_enter_ts": now_ms + 100,
                "indicator_exit_ts": now_ms + 260,
                "click_ts": now_ms + 280,
            },
            "drag": {
                "drag_path": [
                    {"x": 620.0, "y": 420.0, "t": 0},
                    {"x": 600.0, "y": 404.0, "t": 18},
                    {"x": 578.0, "y": 386.0, "t": 38},
                    {"x": 556.0, "y": 368.0, "t": 58},
                    {"x": 536.0, "y": 350.0, "t": 80},
                    {"x": 514.0, "y": 336.0, "t": 102},
                ],
                "total_distance": 162.0,
                "linear_distance": 120.0,
                "curvature": 1.35,
                "overshoot_count": 1,
                "correction_count": 2,
            },
        }

    return {
        "position_ok": False,
        "timing_ok": False,
        "distance_to_target": 999.0,
        "position": {
            "catch_radius": 38.0,
            "final_glove_center": {"x": 100.0, "y": 100.0},
            "ball_landing_point": {"x": 520.0, "y": 338.0},
        },
        "timing": {
            "indicator_enter_ts": now_ms + 100,
            "indicator_exit_ts": now_ms + 200,
            "click_ts": now_ms + 50,
        },
        "drag": {
            "drag_path": [],
            "total_distance": 0.0,
            "linear_distance": 0.0,
            "curvature": 0.0,
            "overshoot_count": 0,
            "correction_count": 0,
        },
    }
