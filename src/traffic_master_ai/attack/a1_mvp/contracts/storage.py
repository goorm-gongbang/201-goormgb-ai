"""Local/session storage contract used by attack runner."""

from __future__ import annotations

from typing import Final

from ..state import SeatMode


TM_SESSION_ID_KEY: Final[str] = "TM_SESSION_ID"
TM_VQA_PASSED_SESSION_ID_KEY: Final[str] = "TM_VQA_PASSED_SESSION_ID"
TM_PREFERENCES_KEY: Final[str] = "TM_PREFERENCES"


def build_default_tm_preferences(mode: SeatMode) -> dict[str, object]:
    """Return conservative defaults aligned with FE expectations."""
    return {
        "recommendEnabled": mode == "RECOMMEND",
        "partySize": 2,
        "priceFilterEnabled": False,
        "priceRange": {"min": 20000, "max": 100000},
    }
