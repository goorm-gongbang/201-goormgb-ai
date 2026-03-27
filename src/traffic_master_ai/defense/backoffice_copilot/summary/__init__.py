"""Window summary helpers for Backoffice Copilot."""

from .fallback import build_fallback_summary_text
from .input_builder import build_window_summary_input
from .window_summary import (
    SummaryGenerationResult,
    SummaryOutputValidationError,
    generate_summary_text,
    parse_summary_text,
)

__all__ = [
    "SummaryGenerationResult",
    "SummaryOutputValidationError",
    "build_fallback_summary_text",
    "build_window_summary_input",
    "generate_summary_text",
    "parse_summary_text",
]
