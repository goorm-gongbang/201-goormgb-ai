from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from traffic_master_ai.defense.backoffice_copilot.core.models import (
    SessionAnalysis,
    SessionReviewResult,
    SessionSummary,
)
from traffic_master_ai.defense.backoffice_copilot.output.backend_adapter import build_backend_request
from traffic_master_ai.defense.backoffice_copilot.output.exporter import build_export_artifacts
from traffic_master_ai.defense.backoffice_copilot.output.persistence import execute_output_stage
from traffic_master_ai.defense.backoffice_copilot.storage.validators import (
    validate_session_result_record,
    validate_summary_text_json,
)
import traffic_master_ai.defense.backoffice_copilot.output.persistence as persistence_module


def _session_analysis(session_id: str, *, suspicious: bool) -> SessionAnalysis:
    return SessionAnalysis(
        session_id=session_id,
        latest_flow_state="F4M",
        latest_action="THROTTLE" if suspicious else "NONE",
        latest_tier="T2" if suspicious else "T1",
        terminal_outcome="NOT_BLOCKED",
        seen_t1=True,
        seen_t2=suspicious,
        vqa_fail_count=1 if suspicious else 0,
        throttle_event_count=1 if suspicious else 0,
        suspicious_signals=["Reached T2 during session"] if suspicious else [],
        timeline_summary=["Session reviewed within window."],
        needs_raw_fallback=False,
    )


def _review_result(session_id: str, review_result: str, evidence_summary: str) -> SessionReviewResult:
    return SessionReviewResult(
        session_id=session_id,
        review_result=review_result,
        evidence_summary=evidence_summary,
    )


def _candidate(session_id: str, *, suspicious: bool) -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        seen_t1=True,
        seen_t2=suspicious,
        block_event_count=0,
        vqa_fail_count=1 if suspicious else 0,
        throttle_event_count=1 if suspicious else 0,
        latest_flow_state="F4M",
        latest_action="THROTTLE" if suspicious else "NONE",
        latest_tier="T2" if suspicious else "T1",
        terminal_outcome="NOT_BLOCKED",
    )


class _FakeRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def save_run(self, run_record) -> None:
        self.calls.append(("save_run", run_record))

    def save_session_results(self, session_records) -> None:
        self.calls.append(("save_session_results", tuple(session_records)))

    def save_bundle(self, run_record, session_records) -> None:
        self.calls.append(("save_bundle", run_record, tuple(session_records)))


class OutputStageTests(unittest.TestCase):
    def test_execute_output_stage_persists_first_and_exports_from_rows(self) -> None:
        repository = _FakeRepository()
        now = datetime(2026, 3, 27, 1, 2, 3, tzinfo=UTC)
        review_results = (
            _review_result("sess-1", "SUSPICIOUS", "Observed repeated T2 activity."),
            _review_result("sess-2", "NORMAL", "Observed baseline activity only."),
        )
        session_analysis_list = (
            _session_analysis("sess-1", suspicious=True),
            _session_analysis("sess-2", suspicious=False),
        )
        candidate_sessions = (
            _candidate("sess-1", suspicious=True),
            _candidate("sess-2", suspicious=False),
        )
        summary_text = [
            "Window reviewed 2 candidate sessions.",
            "1 session remained suspicious after review.",
            "Summary was generated before persistence output assembly.",
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            real_build_export_artifacts = persistence_module.build_export_artifacts

            def wrapped_export_artifacts(*, run_row, session_rows, output_dir=None):
                self.assertEqual([call[0] for call in repository.calls], ["save_bundle", "save_session_results"])
                return real_build_export_artifacts(
                    run_row=run_row,
                    session_rows=session_rows,
                    output_dir=output_dir,
                )

            with patch.object(
                persistence_module,
                "build_export_artifacts",
                side_effect=wrapped_export_artifacts,
            ):
                result = execute_output_stage(
                    repository=repository,
                    match_id="match-1",
                    window_start_ms=100,
                    window_end_ms=200,
                    candidate_sessions=candidate_sessions,
                    review_results=review_results,
                    session_analysis_list=session_analysis_list,
                    summary_text=summary_text,
                    backend_adapter=lambda request: {
                        "match_id": request.match_id,
                        "accepted_count": request.suspicious_count,
                        "rejected_count": 0,
                        "status": "accepted",
                        "received_at": "2026-03-27T01:02:05+00:00",
                    },
                    export_dir=tmpdir,
                    now=now,
                )

            summary_path = Path(result.export_artifacts.written_files[0])
            written_summary_json = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(result.post_review_runs_row.candidate_count, 2)
        self.assertEqual(result.post_review_runs_row.suspicious_count, 1)
        validate_summary_text_json(result.post_review_runs_row.summary_text_json)
        self.assertEqual(len(result.backend_request.candidates), 1)
        self.assertEqual(result.backend_request.candidates[0].session_id, "sess-1")
        self.assertEqual(result.backend_response.accepted_count, 1)
        self.assertEqual(
            [row.backend_delivery_status for row in result.post_review_session_result_rows],
            ["SENT", "PENDING"],
        )
        for row in result.post_review_session_result_rows:
            validate_session_result_record(row)
        self.assertEqual(len(result.export_artifacts.written_files), 3)
        self.assertEqual(written_summary_json["suspicious_count"], 1)
        self.assertEqual(len(result.export_artifacts.suspicious_sessions_jsonl), 1)
        self.assertIn("sess-1", result.export_artifacts.suspicious_sessions_csv)
        self.assertNotIn("sess-2", result.export_artifacts.suspicious_sessions_csv)
        self.assertEqual(result.warnings, ())

    def test_execute_output_stage_marks_failed_when_backend_adapter_missing(self) -> None:
        repository = _FakeRepository()
        result = execute_output_stage(
            repository=repository,
            match_id="match-2",
            window_start_ms=10,
            window_end_ms=20,
            candidate_sessions=(_candidate("sess-1", suspicious=True),),
            review_results=(_review_result("sess-1", "SUSPICIOUS", "Observed repeated T2 activity."),),
            session_analysis_list=(_session_analysis("sess-1", suspicious=True),),
            summary_text=[
                "Window reviewed 1 candidate session.",
                "1 session remained suspicious after review.",
                "Summary stayed independent from persistence output assembly.",
            ],
            backend_adapter=None,
            now=datetime(2026, 3, 27, 2, 0, 0, tzinfo=UTC),
        )

        self.assertEqual([call[0] for call in repository.calls], ["save_bundle", "save_session_results"])
        self.assertEqual(result.backend_request.suspicious_count, 1)
        self.assertIsNone(result.backend_response)
        self.assertEqual(result.post_review_session_result_rows[0].backend_delivery_status, "FAILED")
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.warnings[0].code, "backend_delivery_failed")
        self.assertEqual(result.warnings[0].context["fallback_reason"], "adapter_missing")

    def test_execute_output_stage_keeps_db_success_when_export_write_fails(self) -> None:
        repository = _FakeRepository()

        with patch.object(
            persistence_module,
            "build_export_artifacts",
            side_effect=OSError("disk full"),
        ):
            result = execute_output_stage(
                repository=repository,
                match_id="match-3",
                window_start_ms=30,
                window_end_ms=40,
                candidate_sessions=(_candidate("sess-1", suspicious=True),),
                review_results=(_review_result("sess-1", "SUSPICIOUS", "Observed repeated T2 activity."),),
                session_analysis_list=(_session_analysis("sess-1", suspicious=True),),
                summary_text=[
                    "Window reviewed 1 candidate session.",
                    "1 session remained suspicious after review.",
                    "Summary stayed independent from persistence output assembly.",
                ],
                backend_adapter=lambda request: {
                    "match_id": request.match_id,
                    "accepted_count": request.suspicious_count,
                    "rejected_count": 0,
                    "status": "accepted",
                    "received_at": "2026-03-27T02:03:05+00:00",
                },
                now=datetime(2026, 3, 27, 2, 3, 0, tzinfo=UTC),
            )

        self.assertEqual([call[0] for call in repository.calls], ["save_bundle", "save_session_results"])
        self.assertIsNone(result.export_artifacts)
        self.assertEqual(result.post_review_session_result_rows[0].backend_delivery_status, "SENT")
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.warnings[0].code, "post_review_export_failed")

    def test_backend_request_is_suspicious_only(self) -> None:
        result = execute_output_stage(
            repository=_FakeRepository(),
            match_id="match-4",
            window_start_ms=50,
            window_end_ms=60,
            candidate_sessions=(
                _candidate("sess-1", suspicious=True),
                _candidate("sess-2", suspicious=False),
            ),
            review_results=(
                _review_result("sess-1", "SUSPICIOUS", "Observed repeated T2 activity."),
                _review_result("sess-2", "NORMAL", "Observed baseline activity only."),
            ),
            session_analysis_list=(
                _session_analysis("sess-1", suspicious=True),
                _session_analysis("sess-2", suspicious=False),
            ),
            summary_text=[
                "Window reviewed 2 candidate sessions.",
                "1 session remained suspicious after review.",
                "Summary stayed independent from persistence output assembly.",
            ],
            backend_adapter=None,
            now=datetime(2026, 3, 27, 2, 30, 0, tzinfo=UTC),
        )

        backend_request = build_backend_request(
            match_id="match-4",
            window_start_ms=50,
            window_end_ms=60,
            session_rows=result.post_review_session_result_rows,
        )

        self.assertEqual(backend_request.suspicious_count, 1)
        self.assertEqual([candidate.session_id for candidate in backend_request.candidates], ["sess-1"])

        export_artifacts = build_export_artifacts(
            run_row=result.post_review_runs_row,
            session_rows=result.post_review_session_result_rows,
        )
        self.assertEqual(len(export_artifacts.suspicious_sessions_jsonl), 1)
        self.assertIn("sess-1", export_artifacts.suspicious_sessions_jsonl[0])


if __name__ == "__main__":
    unittest.main()
