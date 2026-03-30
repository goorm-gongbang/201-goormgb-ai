"""Validation report skeleton shared by Task 9a and later extensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..core.issues import IssueContext, PipelineIssue

type ValidationStatusImpact = Literal["none", "partial"]

DEFAULT_DEFERRED_CHECKS: tuple[str, ...] = (
    "final_run_status_resolution",
    "stage_outcome_interpretation",
    "backend_delivery_outcome_interpretation",
    "export_policy_finalization",
)


@dataclass(slots=True)
class ValidationCheckResult:
    """One validation check outcome with append-friendly issue containers."""

    check_name: str
    status_impact: ValidationStatusImpact = "none"
    warnings: list[PipelineIssue] = field(default_factory=list)
    errors: list[PipelineIssue] = field(default_factory=list)
    metadata: IssueContext = field(default_factory=dict)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def add_warning(self, issue: PipelineIssue) -> None:
        self.warnings.append(issue)

    def add_error(self, issue: PipelineIssue) -> None:
        self.errors.append(issue)


@dataclass(slots=True)
class ValidationReport:
    """Thin aggregation object that Task 9b can extend without redefining checks."""

    checks: list[ValidationCheckResult] = field(default_factory=list)
    deferred_checks: list[str] = field(default_factory=lambda: list(DEFAULT_DEFERRED_CHECKS))
    summary: IssueContext = field(default_factory=dict)

    @property
    def warnings(self) -> list[PipelineIssue]:
        aggregated: list[PipelineIssue] = []
        for check in self.checks:
            aggregated.extend(check.warnings)
        return aggregated

    @property
    def errors(self) -> list[PipelineIssue]:
        aggregated: list[PipelineIssue] = []
        for check in self.checks:
            aggregated.extend(check.errors)
        return aggregated

    @property
    def has_warnings(self) -> bool:
        return any(check.has_warnings for check in self.checks)

    @property
    def has_errors(self) -> bool:
        return any(check.has_errors for check in self.checks)

    def add_check(self, check: ValidationCheckResult) -> ValidationCheckResult:
        self.checks.append(check)
        return check

    def merge(self, other: ValidationReport) -> ValidationReport:
        self.checks.extend(other.checks)
        for deferred_check in other.deferred_checks:
            if deferred_check not in self.deferred_checks:
                self.deferred_checks.append(deferred_check)
        self.summary.update(other.summary)
        return self


__all__ = [
    "DEFAULT_DEFERRED_CHECKS",
    "ValidationCheckResult",
    "ValidationReport",
    "ValidationStatusImpact",
]
