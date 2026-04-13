from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import MagicMock, patch

from traffic_master_ai.defense.api.archive_runtime import (
    load_archive_interval_seconds,
    run_s3_archive_loop,
)
from traffic_master_ai.defense.api.audit import DefenseDecisionAuditLogger


class ArchiveLoopIntervalTests(unittest.IsolatedAsyncioTestCase):
    async def test_archive_loop_loads_interval_from_shared_env_loader(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TM_S3_ARCHIVE_INTERVAL_SECONDS": "60",
            },
            clear=True,
        ):
            self.assertEqual(load_archive_interval_seconds(), 60)

    async def test_archive_loop_sleeps_using_configured_interval(self) -> None:
        sleep_calls: list[float] = []
        audit_logger = DefenseDecisionAuditLogger("/tmp/archive-loop-interval-test.jsonl")
        uploader = MagicMock()

        async def _fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with (
            patch.dict(
                os.environ,
                {
                    "TM_S3_ARCHIVE_INTERVAL_SECONDS": "60",
                },
                clear=True,
            ),
            patch(
                "traffic_master_ai.defense.api.archive_runtime.flush_audit_log_to_archive",
                side_effect=asyncio.CancelledError,
            ) as rotate_mock,
        ):
            await run_s3_archive_loop(
                audit_logger=audit_logger,
                uploader=uploader,
                sleep=_fake_sleep,
            )

        self.assertEqual(sleep_calls, [60])
        rotate_mock.assert_called_once_with(audit_logger, uploader)

    async def test_archive_loop_returns_immediately_when_s3_is_disabled(self) -> None:
        audit_logger = DefenseDecisionAuditLogger("/tmp/archive-loop-disabled-test.jsonl")
        sleep_mock = MagicMock()

        await run_s3_archive_loop(
            audit_logger=audit_logger,
            uploader=None,
            sleep=sleep_mock,
        )

        sleep_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
