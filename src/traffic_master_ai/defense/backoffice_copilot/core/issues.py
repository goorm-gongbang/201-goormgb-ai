"""Minimal warning/error contracts for Backoffice Copilot tasks."""

from __future__ import annotations

from dataclasses import dataclass, field

type IssueContext = dict[str, object]
type PipelineWarningList = list["PipelineIssue"]
type PipelineErrorList = list["PipelineIssue"]


@dataclass(slots=True)
class PipelineIssue:
    """Minimal issue item shared by warnings and errors."""

    code: str
    message: str
    context: IssueContext = field(default_factory=dict)
