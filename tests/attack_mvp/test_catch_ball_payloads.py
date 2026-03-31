from __future__ import annotations

from traffic_master_ai.attack.a1_mvp.security.catch_ball import (
    build_fail_telemetry,
    build_pass_telemetry,
    resolve_fail_profile,
    resolve_pass_profile,
)


def test_build_pass_telemetry_contains_required_fields() -> None:
    payload = build_pass_telemetry(1_700_000_000_000)

    assert payload["position_ok"] is True
    assert payload["timing_ok"] is True
    assert payload["distance_to_target"] <= payload["position"]["catch_radius"]

    timing = payload["timing"]
    assert timing["indicator_enter_ts"] < timing["indicator_exit_ts"]
    assert timing["indicator_enter_ts"] <= timing["click_ts"] <= timing["indicator_exit_ts"]

    drag = payload["drag"]
    assert len(drag["drag_path"]) >= 5
    assert drag["total_distance"] >= 30.0
    assert drag["linear_distance"] >= 10.0
    assert 1.02 <= drag["curvature"] <= 12.0


def test_build_pass_telemetry_edge_profile_is_within_backend_bounds() -> None:
    payload = build_pass_telemetry(1_700_000_000_000, profile="edge_pass")
    timing = payload["timing"]
    assert timing["indicator_enter_ts"] <= timing["click_ts"] <= timing["indicator_exit_ts"]
    assert payload["distance_to_target"] <= payload["position"]["catch_radius"]
    assert len(payload["drag"]["drag_path"]) >= 5


def test_build_fail_telemetry_fails_fast_conditions() -> None:
    payload = build_fail_telemetry(1_700_000_000_000)

    # botlike_fail profile keeps top-level flags true and fails on physics checks.
    assert payload["position_ok"] is True
    assert payload["timing_ok"] is True
    drag_path = payload["drag"]["drag_path"]
    assert len(drag_path) >= 5
    assert drag_path[1]["t"] - drag_path[0]["t"] == 1

    # Legacy fast-fail profile still available.
    hard_fail = build_fail_telemetry(1_700_000_000_000, profile="hard_fail")
    assert hard_fail["position_ok"] is False
    assert hard_fail["timing_ok"] is False
    assert hard_fail["distance_to_target"] > hard_fail["position"]["catch_radius"]


def test_build_fail_telemetry_timing_fail_breaks_timing_only() -> None:
    payload = build_fail_telemetry(1_700_000_000_000, profile="timing_fail")
    assert payload["position_ok"] is True
    assert payload["timing_ok"] is False
    assert payload["distance_to_target"] <= payload["position"]["catch_radius"]
    timing = payload["timing"]
    assert timing["click_ts"] > timing["indicator_exit_ts"]


def test_profile_resolvers_have_safe_fallbacks() -> None:
    assert resolve_pass_profile("edge_pass") == "edge_pass"
    assert resolve_pass_profile("token_tamper") == "api_fast"
    assert resolve_fail_profile("timing_fail") == "timing_fail"
    assert resolve_fail_profile("token_tamper") == "botlike_fail"
