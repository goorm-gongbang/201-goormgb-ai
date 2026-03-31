"""Minimal config skeleton for Backoffice Copilot post-review tasks."""

from __future__ import annotations

from dataclasses import dataclass

from .state import PostReviewGraphState, PostReviewRunContext, PostReviewRunInput


@dataclass(slots=True, frozen=True)
class BackofficeCopilotConfig:
    """Cross-task config skeleton limited to fixed Task 1 inputs."""

    match_id: str
    window_start_ms: int
    window_end_ms: int
    limit: int = 1000
    use_raw_audit_fallback: bool = True

    def to_run_input(self) -> PostReviewRunInput:
        return PostReviewRunInput(
            match_id=self.match_id,
            window_start_ms=self.window_start_ms,
            window_end_ms=self.window_end_ms,
            limit=self.limit,
            use_raw_audit_fallback=self.use_raw_audit_fallback,
        )

    def to_run_context(self) -> PostReviewRunContext:
        return PostReviewRunContext.from_input(self.to_run_input())

    def to_graph_state(self) -> PostReviewGraphState:
        return PostReviewGraphState.from_input(self.to_run_input())
