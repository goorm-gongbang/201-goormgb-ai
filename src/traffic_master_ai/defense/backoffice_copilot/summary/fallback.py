"""Template fallback summary builder for Task 7."""

from __future__ import annotations

from typing import Mapping

from ..storage.validators import validate_summary_text_json


def build_fallback_summary_text(summary_input: Mapping[str, object]) -> tuple[str, str, str]:
    """Build a stable three-line run summary from concrete run aggregates."""

    candidate_count = int(summary_input.get("candidate_count", 0))
    reviewed_count = int(summary_input.get("reviewed_count", 0))
    suspicious_count = int(summary_input.get("suspicious_count", 0))
    normal_count = int(summary_input.get("normal_count", 0))
    needs_raw_fallback_count = int(summary_input.get("needs_raw_fallback_count", 0))
    top_signals = summary_input.get("top_signals", [])
    throttle_total = int(summary_input.get("throttle_total", 0))
    challenge_fail_total = int(summary_input.get("challenge_fail_total", 0))
    tier_breakdown = summary_input.get("tier_breakdown") or {}
    action_breakdown = summary_input.get("action_breakdown") or {}

    line_1 = (
        f"Match {summary_input.get('match_id')} window {summary_input.get('window_start_ms')}"
        f"-{summary_input.get('window_end_ms')} reviewed {reviewed_count} of {candidate_count} candidate sessions"
        f" with {suspicious_count} suspicious and {normal_count} normal results."
    )

    # Line 2: concrete mitigation counts take precedence over generic signal names
    mitigation_parts = []
    if throttle_total > 0:
        mitigation_parts.append(f"{throttle_total} throttle event(s)")
    if challenge_fail_total > 0:
        mitigation_parts.append(f"{challenge_fail_total} challenge failure(s)")

    if mitigation_parts:
        mitigation_str = ", ".join(mitigation_parts)
        if isinstance(top_signals, list) and top_signals:
            formatted_signals = ", ".join(
                f"{item['signal']} ({item['count']})"
                for item in top_signals
                if isinstance(item, Mapping) and item.get("signal") and item.get("count") is not None
            )
            line_2 = f"Mitigations: {mitigation_str}; top signals: {formatted_signals}."
        else:
            line_2 = f"Mitigations applied in this window: {mitigation_str}."
    elif isinstance(top_signals, list) and top_signals:
        formatted_signals = ", ".join(
            f"{item['signal']} ({item['count']})"
            for item in top_signals
            if isinstance(item, Mapping) and item.get("signal") and item.get("count") is not None
        )
        line_2 = f"Top suspicious signals in this window: {formatted_signals}."
    else:
        line_2 = "No repeated suspicious signal pattern was recorded in this window."

    # Line 3: tier and action distribution + raw fallback note
    tier_parts = (
        [f"{tier}:{count}" for tier, count in sorted(tier_breakdown.items())]
        if isinstance(tier_breakdown, Mapping) and tier_breakdown
        else []
    )
    action_parts = (
        [f"{action}:{count}" for action, count in sorted(action_breakdown.items())]
        if isinstance(action_breakdown, Mapping) and action_breakdown
        else []
    )

    breakdown_parts = []
    if tier_parts:
        breakdown_parts.append(f"tier distribution [{', '.join(tier_parts)}]")
    if action_parts:
        breakdown_parts.append(f"actions [{', '.join(action_parts)}]")

    if breakdown_parts:
        breakdown_str = "; ".join(breakdown_parts)
        line_3 = f"{breakdown_str}. Raw context pending: {needs_raw_fallback_count} session(s)."
    else:
        line_3 = (
            f"Sessions still requiring additional raw context: {needs_raw_fallback_count};"
            f" summary generation remained run-level and independent from storage."
        )

    lines = (line_1, line_2, line_3)
    validate_summary_text_json(lines)
    return lines


__all__ = ["build_fallback_summary_text"]
