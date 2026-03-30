"""DB-row-based export helpers for Task 8."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from ..core.models import PostReviewRunRecord, PostReviewSessionResultRecord


@dataclass(slots=True, frozen=True)
class ExportArtifacts:
    """Optional export payloads generated strictly from persisted DB row DTOs."""

    summary_json: dict[str, object]
    suspicious_sessions_jsonl: tuple[str, ...]
    suspicious_sessions_csv: str
    written_files: tuple[str, ...] = field(default_factory=tuple)


def build_export_artifacts(
    *,
    run_row: PostReviewRunRecord,
    session_rows: tuple[PostReviewSessionResultRecord, ...] | list[PostReviewSessionResultRecord],
    output_dir: str | Path | None = None,
) -> ExportArtifacts:
    """Build optional export artifacts after DB-row assembly/saving."""

    suspicious_rows = [row for row in session_rows if row.review_result == "SUSPICIOUS"]
    summary_json = {
        "match_id": run_row.match_id,
        "window_start_ms": run_row.window_start_ms,
        "window_end_ms": run_row.window_end_ms,
        "total_candidate_sessions": run_row.candidate_count,
        "suspicious_count": run_row.suspicious_count,
        "summary_text": list(run_row.summary_text_json),
        "status": run_row.status,
    }

    suspicious_jsonl_lines = tuple(
        json.dumps(_serialize_suspicious_row(row), ensure_ascii=True, sort_keys=True)
        for row in suspicious_rows
    )
    suspicious_csv = _build_suspicious_csv(suspicious_rows)

    written_files: list[str] = []
    if output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        summary_path = output_path / "summary.json"
        jsonl_path = output_path / "suspicious_sessions.jsonl"
        csv_path = output_path / "suspicious_sessions.csv"

        summary_path.write_text(json.dumps(summary_json, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        jsonl_payload = "\n".join(suspicious_jsonl_lines)
        jsonl_path.write_text((jsonl_payload + "\n") if jsonl_payload else "", encoding="utf-8")
        csv_path.write_text(suspicious_csv, encoding="utf-8")
        written_files.extend([str(summary_path), str(jsonl_path), str(csv_path)])

    return ExportArtifacts(
        summary_json=summary_json,
        suspicious_sessions_jsonl=suspicious_jsonl_lines,
        suspicious_sessions_csv=suspicious_csv,
        written_files=tuple(written_files),
    )


def _serialize_suspicious_row(row: PostReviewSessionResultRecord) -> dict[str, Any]:
    return {
        "match_id": row.match_id,
        "session_id": row.session_id,
        "review_result": row.review_result,
        "evidence_summary": row.evidence_summary,
        "backend_delivery_status": row.backend_delivery_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _build_suspicious_csv(
    suspicious_rows: list[PostReviewSessionResultRecord],
) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "match_id",
            "session_id",
            "review_result",
            "evidence_summary",
            "backend_delivery_status",
            "created_at",
            "updated_at",
        ],
    )
    writer.writeheader()
    for row in suspicious_rows:
        writer.writerow(_serialize_suspicious_row(row))
    return buffer.getvalue()


__all__ = ["ExportArtifacts", "build_export_artifacts"]
