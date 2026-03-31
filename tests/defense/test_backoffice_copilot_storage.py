from __future__ import annotations

import re
import unittest
from datetime import UTC, datetime
from pathlib import Path

from traffic_master_ai.defense.backoffice_copilot.core.models import (
    PostReviewRunRecord,
    PostReviewSessionResultRecord,
    SessionAnalysis,
)
from traffic_master_ai.defense.backoffice_copilot.storage.repository import PkConflictPolicy
from traffic_master_ai.defense.backoffice_copilot.storage.validators import (
    ALLOWED_BACKEND_DELIVERY_STATUSES,
    ALLOWED_REVIEW_RESULTS,
    ALLOWED_RUN_STATUSES,
    StorageValidationError,
    serialize_run_record,
    serialize_session_result_record,
    validate_session_analysis_json,
    validate_summary_text_json,
)


def _session_analysis() -> SessionAnalysis:
    return SessionAnalysis(
        session_id="sess-1",
        latest_flow_state="F4M",
        latest_action="THROTTLE",
        latest_tier="T2",
        terminal_outcome="NOT_BLOCKED",
        seen_t1=True,
        seen_t2=True,
        vqa_fail_count=1,
        throttle_event_count=1,
        suspicious_signals=["Reached T2 during session"],
        timeline_summary=["Session reached T2 during evaluation."],
        needs_raw_fallback=False,
    )


def _run_record() -> PostReviewRunRecord:
    now = datetime(2026, 3, 27, 1, 0, 0, tzinfo=UTC)
    return PostReviewRunRecord(
        match_id="match-1",
        window_start_ms=100,
        window_end_ms=200,
        candidate_count=1,
        suspicious_count=1,
        summary_text_json=[
            "Window reviewed 1 candidate session.",
            "1 session remained suspicious after review.",
            "Summary stayed independent from DB write orchestration.",
        ],
        status="SUCCESS",
        created_at=now,
        updated_at=now,
    )


def _session_record() -> PostReviewSessionResultRecord:
    now = datetime(2026, 3, 27, 1, 0, 0, tzinfo=UTC)
    return PostReviewSessionResultRecord(
        match_id="match-1",
        session_id="sess-1",
        review_result="SUSPICIOUS",
        evidence_summary="Observed repeated T2 throttle activity.",
        session_analysis_json=_session_analysis(),
        backend_delivery_status="PENDING",
        created_at=now,
        updated_at=now,
    )


class BackofficeCopilotStorageTests(unittest.TestCase):
    def test_task_2_sql_contract_keeps_exactly_two_tables(self) -> None:
        sql_path = Path(
            "src/traffic_master_ai/defense/backoffice_copilot/storage/sql/001_post_review_tables.sql"
        )
        sql_text = sql_path.read_text(encoding="utf-8")

        create_tables = re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", sql_text)
        self.assertEqual(create_tables, ["post_review_runs", "post_review_session_results"])
        self.assertEqual(sql_text.count("CREATE TABLE IF NOT EXISTS"), 2)
        self.assertIn("CHECK (status IN ('SUCCESS', 'PARTIAL_SUCCESS', 'FAILED'))", sql_text)
        self.assertIn("CHECK (review_result IN ('NORMAL', 'SUSPICIOUS'))", sql_text)
        self.assertIn("CHECK (backend_delivery_status IN ('PENDING', 'SENT', 'FAILED'))", sql_text)

    def test_allowed_value_sets_match_documented_contract(self) -> None:
        self.assertEqual(ALLOWED_RUN_STATUSES, frozenset({"SUCCESS", "PARTIAL_SUCCESS", "FAILED"}))
        self.assertEqual(ALLOWED_REVIEW_RESULTS, frozenset({"NORMAL", "SUSPICIOUS"}))
        self.assertEqual(ALLOWED_BACKEND_DELIVERY_STATUSES, frozenset({"PENDING", "SENT", "FAILED"}))
        self.assertEqual(PkConflictPolicy.FAIL_FAST.value, "fail_fast")
        self.assertEqual(PkConflictPolicy.UPSERT.value, "upsert")

    def test_validators_accept_storage_compatible_json_payloads(self) -> None:
        validated_summary = validate_summary_text_json(_run_record().summary_text_json)
        validated_session_analysis = validate_session_analysis_json(_session_analysis())
        serialized_run = serialize_run_record(_run_record())
        serialized_session = serialize_session_result_record(_session_record())

        self.assertEqual(len(validated_summary), 3)
        self.assertEqual(validated_session_analysis["session_id"], "sess-1")
        self.assertEqual(serialized_run["status"], "SUCCESS")
        self.assertEqual(serialized_session["review_result"], "SUSPICIOUS")
        self.assertEqual(serialized_session["backend_delivery_status"], "PENDING")

    def test_validators_reject_invalid_summary_and_session_analysis_shapes(self) -> None:
        with self.assertRaises(StorageValidationError):
            validate_summary_text_json(["only", "two"])

        with self.assertRaises(StorageValidationError):
            validate_session_analysis_json(
                {
                    "session_id": "sess-1",
                    "latest_flow_state": "F4M",
                    "latest_action": "THROTTLE",
                    "latest_tier": "T2",
                    "terminal_outcome": "NOT_BLOCKED",
                    "seen_t1": True,
                    "seen_t2": True,
                    "vqa_fail_count": 1,
                    "throttle_event_count": 1,
                    "suspicious_signals": ["Reached T2 during session"],
                    "timeline_summary": "not-a-list",
                    "needs_raw_fallback": False,
                }
            )

        invalid_session_record = _session_record()
        invalid_session_record.backend_delivery_status = ""
        with self.assertRaises(StorageValidationError):
            serialize_session_result_record(invalid_session_record)


if __name__ == "__main__":
    unittest.main()
