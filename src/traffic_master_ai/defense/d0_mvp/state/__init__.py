"""State management package — Redis state abstraction.

Ref: L1/runtime/state.yaml
"""

from .dedup import DedupChecker
from .etl_processed_ledger import (
    ETLProcessedS3ObjectIdentity,
    ETLProcessedS3ObjectLedger,
    ETLProcessedS3ObjectRecord,
    build_etl_processed_s3_object_ledger_key,
)
from .session_state import SessionStateManager
from .block_state import BlockStateManager

__all__ = [
    "DedupChecker",
    "ETLProcessedS3ObjectIdentity",
    "ETLProcessedS3ObjectLedger",
    "ETLProcessedS3ObjectRecord",
    "SessionStateManager",
    "BlockStateManager",
    "build_etl_processed_s3_object_ledger_key",
]
