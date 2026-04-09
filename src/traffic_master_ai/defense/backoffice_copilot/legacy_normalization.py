from __future__ import annotations

_LEGACY_FLOW_STATE_MAP: dict[str, str] = {
    "S0": "F0",
    "S1": "F1",
    "S2": "F2",
    "S3": "F2",
    "S4": "F3",
    "S4R": "F3R",
    "S5": "F4",
    "S5R": "F4R",
    "S6": "FX",
    "SX": "FX",
}

_LEGACY_ACTION_MAP: dict[str, str] = {
    "CHALLENGE": "REQUIRE_S3",
}


def normalize_flow_state(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    return _LEGACY_FLOW_STATE_MAP.get(normalized, normalized)


def normalize_action(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    return _LEGACY_ACTION_MAP.get(normalized, normalized)


__all__ = ["normalize_action", "normalize_flow_state"]
