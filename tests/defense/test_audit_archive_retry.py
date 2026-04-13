from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from traffic_master_ai.defense.api.audit import (
    DefenseDecisionAuditLogger,
    flush_audit_log_to_archive,
    upload_pending_rotated_audit_logs,
)


class _FakeUploader:
    def __init__(self, outcomes: dict[str, bool] | None = None) -> None:
        self._outcomes = outcomes or {}
        self.uploaded_paths: list[Path] = []

    def upload_file(self, local_path: Path) -> bool:
        self.uploaded_paths.append(local_path)
        return self._outcomes.get(local_path.name, True)


class AuditArchiveRetryTests(unittest.TestCase):
    def test_upload_pending_rotated_audit_logs_retries_rotated_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "decision_audit.jsonl"
            logger = DefenseDecisionAuditLogger(str(log_path))
            log_path.write_text('{"current":true}\n', encoding="utf-8")

            failed_path = log_path.with_name("decision_audit_20260410_000001.jsonl")
            succeeded_path = log_path.with_name("decision_audit_20260410_000002.jsonl")
            failed_path.write_text('{"stale":1}\n', encoding="utf-8")
            succeeded_path.write_text('{"stale":2}\n', encoding="utf-8")

            uploader = _FakeUploader(
                outcomes={
                    failed_path.name: False,
                    succeeded_path.name: True,
                }
            )

            uploaded = upload_pending_rotated_audit_logs(logger, uploader)

            self.assertEqual(uploaded, (succeeded_path,))
            self.assertEqual(
                [path.name for path in uploader.uploaded_paths],
                [failed_path.name, succeeded_path.name],
            )
            self.assertTrue(log_path.exists())
            self.assertTrue(failed_path.exists())
            self.assertFalse(succeeded_path.exists())

    def test_flush_audit_log_to_archive_uploads_pending_and_current_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "decision_audit.jsonl"
            logger = DefenseDecisionAuditLogger(str(log_path))
            log_path.write_text('{"current":true}\n', encoding="utf-8")

            stale_rotated_path = log_path.with_name("decision_audit_20260410_000003.jsonl")
            stale_rotated_path.write_text('{"stale":true}\n', encoding="utf-8")

            uploader = _FakeUploader()

            flush_audit_log_to_archive(logger, uploader)

            self.assertFalse(log_path.exists())
            self.assertFalse(stale_rotated_path.exists())
            self.assertEqual(len(uploader.uploaded_paths), 2)
            self.assertEqual(uploader.uploaded_paths[0].name, stale_rotated_path.name)
            self.assertTrue(uploader.uploaded_paths[1].name.startswith("decision_audit_"))
            self.assertNotEqual(uploader.uploaded_paths[1].name, stale_rotated_path.name)


if __name__ == "__main__":
    unittest.main()
