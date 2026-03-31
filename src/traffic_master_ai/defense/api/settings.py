"""Local settings loader for defense/api."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

ENV_FILE_PATH = Path(__file__).resolve().parent / ".env.local"


def _strip_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


@lru_cache(maxsize=1)
def load_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE_PATH.is_file():
        return values

    for raw_line in ENV_FILE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_env_value(value)
    return values


def read_str(key: str, default: str = "") -> str:
    value = load_env_file().get(key)
    if value is None:
        return default
    return value


def read_int(key: str, default: int) -> int:
    value = load_env_file().get(key)
    if value is None or value == "":
        return default
    return int(value)


def read_float(key: str, default: float) -> float:
    value = load_env_file().get(key)
    if value is None or value == "":
        return default
    return float(value)
