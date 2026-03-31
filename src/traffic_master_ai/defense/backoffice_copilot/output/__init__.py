"""Output-stage helpers for Backoffice Copilot Task 8."""

from .backend_adapter import (
    BackendAdapterError,
    BackendDeliveryResult,
    BackendRequestAdapter,
    build_backend_request,
    deliver_backend_request,
)
from .exporter import ExportArtifacts, build_export_artifacts
from .persistence import (
    OutputStageResult,
    build_post_review_run_record,
    build_post_review_session_result_rows,
    execute_output_stage,
)

__all__ = [
    "BackendAdapterError",
    "BackendDeliveryResult",
    "BackendRequestAdapter",
    "ExportArtifacts",
    "OutputStageResult",
    "build_backend_request",
    "build_export_artifacts",
    "build_post_review_run_record",
    "build_post_review_session_result_rows",
    "deliver_backend_request",
    "execute_output_stage",
]
