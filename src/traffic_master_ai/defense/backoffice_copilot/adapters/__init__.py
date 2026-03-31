"""LLM adapters for Backoffice Copilot."""

from .openai import build_openai_review_adapter, build_openai_summary_adapter

__all__ = ["build_openai_review_adapter", "build_openai_summary_adapter"]
