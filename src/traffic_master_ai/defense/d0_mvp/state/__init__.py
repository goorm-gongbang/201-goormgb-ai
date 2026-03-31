"""State management package — Redis state abstraction.

Ref: L1/runtime/state.yaml
"""

from .dedup import DedupChecker
from .session_state import SessionStateManager
from .block_state import BlockStateManager

__all__ = ["DedupChecker", "SessionStateManager", "BlockStateManager"]
