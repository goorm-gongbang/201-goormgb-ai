"""Allowed-value validation interface layered above storage validators."""

from __future__ import annotations

from typing import Literal

from ..core.issues import PipelineIssue
from ..storage.validators import (
    ALLOWED_BACKEND_DELIVERY_STATUSES,
    ALLOWED_REVIEW_RESULTS,
    ALLOWED_RUN_STATUSES,
)
from .report import ValidationCheckResult

type AllowedValueTarget = Literal["status", "review_result", "backend_delivery_status"]

_ALLOWED_VALUE_MAP: dict[AllowedValueTarget, frozenset[str]] = {
    "status": ALLOWED_RUN_STATUSES,
    "review_result": ALLOWED_REVIEW_RESULTS,
    "backend_delivery_status": ALLOWED_BACKEND_DELIVERY_STATUSES,
}


def get_allowed_values(target: AllowedValueTarget) -> frozenset[str]:
    """Expose fixed allowed-value sets without duplicating Task 2 storage rules."""

    return _ALLOWED_VALUE_MAP[target]


def validate_allowed_value(target: AllowedValueTarget, value: object) -> ValidationCheckResult:
    """Validate one allowed-value field and return a skeleton check result."""

    check = ValidationCheckResult(
        check_name=f"allowed_values.{target}",
        metadata={
            "field_name": target,
            "allowed_values": sorted(_ALLOWED_VALUE_MAP[target]),
        },
    )
    allowed_values = _ALLOWED_VALUE_MAP[target]
    if not isinstance(value, str):
        check.add_error(
            PipelineIssue(
                code="invalid_allowed_value_type",
                message=f"{target} must be a string from the documented allowed set.",
                context={"field_name": target, "received_type": type(value).__name__},
            )
        )
        return check
    if value not in allowed_values:
        check.add_error(
            PipelineIssue(
                code="invalid_allowed_value",
                message=f"{target} must be one of the documented allowed values.",
                context={
                    "field_name": target,
                    "received_value": value,
                    "allowed_values": sorted(allowed_values),
                },
            )
        )
    return check


__all__ = [
    "AllowedValueTarget",
    "get_allowed_values",
    "validate_allowed_value",
]
