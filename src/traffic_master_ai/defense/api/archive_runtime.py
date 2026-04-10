from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ..storage_env import load_s3_archive_config_from_env
from .audit import DefenseDecisionAuditLogger, S3Uploader, flush_audit_log_to_archive

logger = logging.getLogger(__name__)


def load_archive_interval_seconds() -> int:
    return load_s3_archive_config_from_env().archive_interval_seconds


async def run_s3_archive_loop(
    *,
    audit_logger: DefenseDecisionAuditLogger,
    uploader: S3Uploader | None,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> None:
    if not uploader:
        logger.info("S3 Archiving is disabled (TM_S3_BUCKET not set).")
        return

    interval_seconds = load_archive_interval_seconds()
    logger.info("Starting S3 Archiving Loop (Interval: %ds)", interval_seconds)
    while True:
        try:
            await sleep(interval_seconds)
            flush_audit_log_to_archive(audit_logger, uploader)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Error in S3 archiving loop: %s", exc)


__all__ = ["load_archive_interval_seconds", "run_s3_archive_loop"]
