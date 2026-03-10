"""Offline policy proposal validator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..policy.snapshot import PolicySnapshot


_ALLOWED_PATHS: frozenset[str] = frozenset(
    {
        "risk.alpha",
        "tier.thresholds.T0_max",
        "tier.thresholds.T1_max",
        "tier.thresholds.T2_max",
        "tier.hysteresis.margin",
        "risk.probation_seconds",
        "planner.throttle_delay_ms.T1",
        "planner.throttle_delay_ms.T2",
        "challenge.max_attempts",
        "challenge.cooldown_ms.first",
        "challenge.cooldown_ms.second",
        "challenge.halt_seconds",
    }
)

_INTEGER_PATHS: frozenset[str] = frozenset(
    {
        "risk.probation_seconds",
        "planner.throttle_delay_ms.T1",
        "planner.throttle_delay_ms.T2",
        "challenge.max_attempts",
        "challenge.cooldown_ms.first",
        "challenge.cooldown_ms.second",
        "challenge.halt_seconds",
    }
)

_ROOT_FIELDS: frozenset[str] = frozenset(
    {
        "proposal_id",
        "base_policy_version",
        "patches",
        "rationale",
        "confidence",
        "rollback_conditions",
        "notes",
    }
)

_BASELINE_VALUES: dict[str, float] = {
    "risk.alpha": 0.30,
    "tier.thresholds.T0_max": 0.20,
    "tier.thresholds.T1_max": 0.50,
    "tier.thresholds.T2_max": 0.80,
    "tier.hysteresis.margin": 0.02,
    "risk.probation_seconds": 45,
    "planner.throttle_delay_ms.T1": 80,
    "planner.throttle_delay_ms.T2": 250,
    "challenge.max_attempts": 2,
    "challenge.cooldown_ms.first": 0,
    "challenge.cooldown_ms.second": 2500,
    "challenge.halt_seconds": 30,
}

_NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "risk.alpha": (0.05, 0.60),
    "tier.thresholds.T0_max": (0.05, 0.40),
    "tier.thresholds.T1_max": (0.20, 0.70),
    "tier.thresholds.T2_max": (0.50, 0.95),
    "tier.hysteresis.margin": (0.0, 0.10),
    "risk.probation_seconds": (10, 120),
    "planner.throttle_delay_ms.T1": (0, 200),
    "planner.throttle_delay_ms.T2": (100, 600),
    "challenge.max_attempts": (1, 3),
    "challenge.cooldown_ms.first": (0, 3000),
    "challenge.cooldown_ms.second": (0, 5000),
    "challenge.halt_seconds": (0, 120),
}


@dataclass(slots=True, frozen=True)
class ValidationResult:
    """Proposal validation output."""

    valid: bool
    errors: tuple[str, ...]
    sanitized_proposal: dict[str, Any]


class ProposalValidator:
    """Validate EffectEvaluatorPatchProposalV1 payloads."""

    def validate(
        self,
        proposal: Mapping[str, Any],
        *,
        expected_base_policy_version: Optional[str] = None,
        base_values: Optional[Mapping[str, float]] = None,
    ) -> ValidationResult:
        errors: list[str] = []
        unknown_root = sorted(str(key) for key in proposal.keys() if str(key) not in _ROOT_FIELDS)
        if unknown_root:
            errors.append("unknown root fields: " + ", ".join(unknown_root))

        proposal_id = str(proposal.get("proposal_id", "")).strip()
        if not proposal_id:
            errors.append("proposal_id is required")

        base_policy_version = str(proposal.get("base_policy_version", "")).strip()
        if not base_policy_version:
            errors.append("base_policy_version is required")
        elif (
            expected_base_policy_version is not None
            and base_policy_version != expected_base_policy_version
        ):
            errors.append(
                "base_policy_version mismatch: "
                f"{base_policy_version} != {expected_base_policy_version}"
            )

        patches = proposal.get("patches")
        if not isinstance(patches, list) or not patches:
            errors.append("patches must be non-empty array")
            return ValidationResult(False, tuple(errors), _empty_sanitized_proposal())
        if len(patches) > 12:
            errors.append("patches length must be <= 12")

        rationale = str(proposal.get("rationale", ""))
        if not rationale:
            errors.append("rationale is required")
        elif len(rationale) > 1200:
            errors.append("rationale must be <= 1200 chars")

        confidence_raw = proposal.get("confidence")
        confidence = 0.0
        if confidence_raw is not None:
            try:
                confidence = float(confidence_raw)
            except (TypeError, ValueError):
                errors.append("confidence must be numeric")
            else:
                if confidence < 0.0 or confidence > 1.0:
                    errors.append("confidence must be within [0,1]")

        rollback_conditions_raw = proposal.get("rollback_conditions")
        sanitized_rollback_conditions: list[str] = []
        if not isinstance(rollback_conditions_raw, list) or not rollback_conditions_raw:
            errors.append("rollback_conditions must be non-empty array")
        else:
            if len(rollback_conditions_raw) > 12:
                errors.append("rollback_conditions length must be <= 12")
            for idx, item in enumerate(rollback_conditions_raw):
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"rollback_conditions[{idx}] must be non-empty string")
                    continue
                if len(item) > 200:
                    errors.append(f"rollback_conditions[{idx}] must be <= 200 chars")
                    continue
                sanitized_rollback_conditions.append(item)

        notes = str(proposal.get("notes", ""))
        if len(notes) > 600:
            errors.append("notes must be <= 600 chars")

        working_values = build_base_patch_values(base_values)
        sanitized_patches: list[dict[str, Any]] = []

        for idx, patch in enumerate(patches):
            if not isinstance(patch, Mapping):
                errors.append(f"patch[{idx}] must be object")
                continue
            unknown_patch_fields = sorted(
                str(key) for key in patch.keys() if str(key) not in {"path", "op", "value", "why"}
            )
            if unknown_patch_fields:
                errors.append(
                    f"patch[{idx}] has unknown fields: " + ", ".join(unknown_patch_fields)
                )
            path = str(patch.get("path", ""))
            op = str(patch.get("op", ""))
            value = patch.get("value")
            why = str(patch.get("why", ""))

            if path not in _ALLOWED_PATHS:
                errors.append(f"forbidden patch path: {path}")
                continue
            if op not in {"set", "inc", "dec"}:
                errors.append(f"invalid op for patch[{idx}]: {op}")
                continue
            if not why:
                errors.append(f"patch[{idx}] missing why")
            elif len(why) > 280:
                errors.append(f"patch[{idx}] why must be <= 280 chars")

            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                errors.append(f"patch[{idx}] value must be numeric")
                continue
            if path in _INTEGER_PATHS:
                if not numeric_value.is_integer():
                    errors.append(f"patch[{idx}] value must be integer for {path}")
                    continue
                normalized_value: float | int = int(numeric_value)
            else:
                normalized_value = numeric_value

            prev = working_values[path]
            if op == "set":
                nxt = normalized_value
            elif op == "inc":
                nxt = prev + normalized_value
            else:
                nxt = prev - normalized_value

            lo, hi = _NUMERIC_BOUNDS[path]
            if nxt < lo or nxt > hi:
                errors.append(
                    f"patch[{idx}] out of range for {path}: {nxt} not in [{lo}, {hi}]"
                )
                continue

            working_values[path] = nxt
            sanitized_patches.append(
                {
                    "path": path,
                    "op": op,
                    "value": normalized_value,
                    "why": why,
                }
            )

        t0 = working_values["tier.thresholds.T0_max"]
        t1 = working_values["tier.thresholds.T1_max"]
        t2 = working_values["tier.thresholds.T2_max"]
        if not (t0 < t1 < t2 < 1.0):
            errors.append("monotonic thresholds violated: T0 < T1 < T2 < 1.0")

        delay_t1 = working_values["planner.throttle_delay_ms.T1"]
        delay_t2 = working_values["planner.throttle_delay_ms.T2"]
        if delay_t2 < delay_t1:
            errors.append("guardrail violated: T2 throttle delay must be >= T1")

        cd1 = working_values["challenge.cooldown_ms.first"]
        cd2 = working_values["challenge.cooldown_ms.second"]
        if cd2 < cd1:
            errors.append("guardrail violated: challenge cooldown second must be >= first")

        sanitized = {
            "proposal_id": proposal_id,
            "base_policy_version": base_policy_version,
            "patches": sanitized_patches,
            "rationale": rationale,
            "confidence": confidence,
            "rollback_conditions": sanitized_rollback_conditions,
            "notes": notes,
        }

        return ValidationResult(valid=not errors, errors=tuple(errors), sanitized_proposal=sanitized)


def build_base_patch_values(
    base_values: Optional[Mapping[str, float]] = None,
) -> dict[str, float]:
    """Return proposal patch base values, defaulting to SSOT baseline."""
    working_values = dict(_BASELINE_VALUES)
    if base_values is None:
        return working_values
    for path in _ALLOWED_PATHS:
        if path not in base_values:
            continue
        raw = base_values[path]
        working_values[path] = int(raw) if path in _INTEGER_PATHS else float(raw)
    return working_values


def proposal_base_values_from_policy(policy: PolicySnapshot) -> dict[str, float]:
    """Map one PolicySnapshot to allowlisted patch base values."""
    return {
        "risk.alpha": policy.ewma_alpha,
        "tier.thresholds.T0_max": policy.t0_max,
        "tier.thresholds.T1_max": policy.t1_max,
        "tier.thresholds.T2_max": policy.t2_max,
        "tier.hysteresis.margin": policy.hysteresis_margin,
        "risk.probation_seconds": policy.probation_seconds_after_s3_pass,
        "planner.throttle_delay_ms.T1": policy.throttle_delay_ms_t1,
        "planner.throttle_delay_ms.T2": policy.throttle_delay_ms_t2,
        "challenge.max_attempts": policy.challenge_max_attempts,
        "challenge.cooldown_ms.first": policy.challenge_cooldown_ms_1,
        "challenge.cooldown_ms.second": policy.challenge_cooldown_ms_2,
        "challenge.halt_seconds": policy.challenge_halt_seconds,
    }


def _empty_sanitized_proposal() -> dict[str, Any]:
    return {
        "proposal_id": "",
        "base_policy_version": "",
        "patches": [],
        "rationale": "",
        "confidence": 0.0,
        "rollback_conditions": [],
        "notes": "",
    }


__all__ = [
    "ProposalValidator",
    "ValidationResult",
    "build_base_patch_values",
    "proposal_base_values_from_policy",
]
