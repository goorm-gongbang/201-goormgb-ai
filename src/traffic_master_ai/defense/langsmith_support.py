from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


def current_tm_ai_environment() -> str:
    value = os.getenv("TM_AI_ENV", "dev").strip().lower()
    return value or "dev"


def _langsmith_project_name() -> str:
    return os.getenv("LANGSMITH_PROJECT", "tm-ai")


def _langsmith_base_url() -> str:
    return os.getenv("LANGSMITH_ENDPOINT", "https://smith.langchain.com").rstrip("/")


def start_langsmith_llm_trace(
    *,
    name: str,
    model_name: str,
    inputs: Mapping[str, Any],
    metadata: Mapping[str, Any],
    provider: str = "openai",
    tags: Sequence[str] = (),
) -> "_LangSmithLLMTrace":
    trace_metadata = dict(metadata)
    trace_metadata.setdefault("ls_provider", provider)
    trace_metadata.setdefault("ls_model_name", model_name)
    return _LangSmithLLMTrace(
        name=name,
        inputs=dict(inputs),
        metadata=trace_metadata,
        tags=tuple(tags),
    )


@dataclass(slots=True)
class _LangSmithLLMTrace:
    name: str
    inputs: dict[str, Any]
    metadata: dict[str, Any]
    tags: tuple[str, ...] = field(default_factory=tuple)
    _trace_context: Any = field(default=None, init=False, repr=False)
    _run_tree: Any = field(default=None, init=False, repr=False)
    _output_payload: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _usage_metadata: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> "_LangSmithLLMTrace":
        if not _langsmith_tracing_enabled():
            return self
        try:
            import langsmith as ls
        except ImportError:
            return self
        try:
            self._trace_context = ls.trace(
                name=self.name,
                run_type="llm",
                inputs=self.inputs,
                metadata=self.metadata,
                tags=list(self.tags),
            )
            self._run_tree = self._trace_context.__enter__()
        except Exception:
            self._trace_context = None
            self._run_tree = None
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self._run_tree is not None:
            if exc is not None:
                self.record_error(exc)
            if self._usage_metadata is not None:
                try:
                    self._run_tree.usage_metadata = dict(self._usage_metadata)
                except Exception:
                    pass
            if self._output_payload is not None:
                try:
                    self._run_tree.end(outputs=self._output_payload)
                except Exception:
                    pass
        if self._trace_context is not None:
            return bool(self._trace_context.__exit__(exc_type, exc, tb))
        return False

    @property
    def run_id(self) -> str | None:
        """Return the LangSmith run ID if tracing is active, else None."""
        if self._run_tree is None:
            return None
        try:
            rid = getattr(self._run_tree, "id", None)
            return str(rid) if rid is not None else None
        except Exception:
            return None

    @property
    def trace_url(self) -> str | None:
        """Build the LangSmith trace URL from run_id and project name."""
        rid = self.run_id
        if rid is None:
            return None
        try:
            project = _langsmith_project_name()
            base = _langsmith_base_url()
            return f"{base}/o/{_langsmith_workspace_id()}/projects/p/{project}/r/{rid}"
        except Exception:
            return None

    def get_langsmith_link(self) -> dict[str, str]:
        """Return a dict suitable for embedding as {'runId': ..., 'traceUrl': ...}.

        Returns an empty dict if tracing is not active.
        """
        link: dict[str, str] = {}
        rid = self.run_id
        if rid:
            link["runId"] = rid
        url = self.trace_url
        if url:
            link["traceUrl"] = url
        return link

    def record_usage_metadata(self, usage_metadata: Mapping[str, Any] | None) -> None:
        if not usage_metadata:
            return
        self._usage_metadata = dict(usage_metadata)

    def record_output(self, output_payload: Mapping[str, Any] | None) -> None:
        if not output_payload:
            return
        payload = dict(output_payload)
        if self._usage_metadata is not None and "usage_metadata" not in payload:
            payload["usage_metadata"] = dict(self._usage_metadata)
        self._output_payload = payload

    def record_error(self, exc: Exception | str) -> None:
        if self._run_tree is None:
            return
        error_text = str(exc)
        try:
            self._run_tree.metadata["error"] = error_text
        except Exception:
            pass


def _langsmith_tracing_enabled() -> bool:
    raw = os.getenv("LANGSMITH_TRACING", "")
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _langsmith_workspace_id() -> str:
    """Return the workspace ID for URL construction. Falls back to 'default'."""
    return os.getenv("LANGSMITH_WORKSPACE_ID", "default")


__all__ = ["current_tm_ai_environment", "start_langsmith_llm_trace"]
