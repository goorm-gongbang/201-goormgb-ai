"""Policy-apply guardrails for offline patch candidates."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GuardrailConfig:
    min_evaluable_sessions: int = 5
    min_alignment_rate: float = 0.65
    max_unavailable_ratio: float = 0.3
    max_patch_delta_ratio: float = 0.5
    require_manual_approval: bool = True
    approval_token_env_key: str = "TM_POLICY_APPLY_APPROVAL_TOKEN"

    @staticmethod
    def from_env() -> GuardrailConfig:
        return GuardrailConfig(
            min_evaluable_sessions=int(os.getenv("TM_GUARDRAIL_MIN_EVALUABLE", "5")),
            min_alignment_rate=float(os.getenv("TM_GUARDRAIL_MIN_ALIGNMENT", "0.65")),
            max_unavailable_ratio=float(os.getenv("TM_GUARDRAIL_MAX_UNAVAILABLE", "0.3")),
            max_patch_delta_ratio=float(os.getenv("TM_GUARDRAIL_MAX_PATCH_DELTA", "0.5")),
            require_manual_approval=os.getenv(
                "TM_GUARDRAIL_REQUIRE_APPROVAL", "true"
            ).strip().lower()
            in {"1", "true", "yes", "y", "on"},
            approval_token_env_key=os.getenv(
                "TM_GUARDRAIL_APPROVAL_TOKEN_ENV",
                "TM_POLICY_APPLY_APPROVAL_TOKEN",
            ).strip(),
        )


def _validate_patch_delta(patch: dict[str, Any], max_delta_ratio: float) -> bool:
    current = patch.get("current")
    proposed = patch.get("proposed")
    if not isinstance(current, (int, float)) or not isinstance(proposed, (int, float)):
        return True
    if current == 0:
        return False
    delta_ratio = abs(float(proposed) - float(current)) / abs(float(current))
    return delta_ratio <= max_delta_ratio


def evaluate_guardrails(
    *,
    cfg: GuardrailConfig,
    batch_summary: dict[str, Any],
    patches: list[dict[str, Any]],
    approval_token: str | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    status = str(batch_summary.get("status") or "")
    if status != "OK":
        reasons.append("BATCH_NOT_OK")

    alignment = batch_summary.get("alignment") or {}
    try:
        evaluable = int(alignment.get("evaluable_session_count", 0))
    except (TypeError, ValueError):
        evaluable = 0
    try:
        alignment_rate = float(alignment.get("alignment_rate", 0.0))
    except (TypeError, ValueError):
        alignment_rate = 0.0
    try:
        unavailable_ratio = float(alignment.get("unavailable_ratio", 0.0))
    except (TypeError, ValueError):
        unavailable_ratio = 0.0

    if evaluable < cfg.min_evaluable_sessions:
        reasons.append("NOT_ENOUGH_EVALUABLE_SESSIONS")
    if alignment_rate < cfg.min_alignment_rate:
        reasons.append("ALIGNMENT_TOO_LOW")
    if unavailable_ratio > cfg.max_unavailable_ratio:
        reasons.append("UNAVAILABLE_RATIO_TOO_HIGH")

    patch_count = len(patches)
    if patch_count == 0:
        reasons.append("NO_PATCH_CANDIDATES")

    for patch in patches:
        if not bool(patch.get("manual_review_required", False)):
            reasons.append("PATCH_WITHOUT_MANUAL_REVIEW_FLAG")
            break
    for patch in patches:
        if not _validate_patch_delta(patch, cfg.max_patch_delta_ratio):
            reasons.append("PATCH_DELTA_TOO_LARGE")
            break

    expected_token = os.getenv(cfg.approval_token_env_key, "")
    if cfg.require_manual_approval:
        if not expected_token:
            reasons.append("APPROVAL_TOKEN_NOT_CONFIGURED")
        elif approval_token != expected_token:
            reasons.append("APPROVAL_TOKEN_MISMATCH")

    approved = len(reasons) == 0
    return {
        "decision": "APPLY_READY" if approved else "HOLD",
        "approved": approved,
        "reasons": reasons,
        "guardrails": {
            "min_evaluable_sessions": cfg.min_evaluable_sessions,
            "min_alignment_rate": cfg.min_alignment_rate,
            "max_unavailable_ratio": cfg.max_unavailable_ratio,
            "max_patch_delta_ratio": cfg.max_patch_delta_ratio,
            "require_manual_approval": cfg.require_manual_approval,
            "approval_token_env_key": cfg.approval_token_env_key,
        },
        "snapshot": {
            "patch_count": patch_count,
            "evaluable_session_count": evaluable,
            "alignment_rate": round(alignment_rate, 4),
            "unavailable_ratio": round(unavailable_ratio, 4),
        },
    }
