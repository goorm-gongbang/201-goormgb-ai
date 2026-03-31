"""Redis client abstraction for D0-MVP.

Provides a thin wrapper around redis.Redis (sync) or a dict-backed
in-memory fake for tests (MVP default when Redis is unavailable).

Ref: L1/runtime/state.yaml#redis, L1/runtime/state.yaml#atomicity_and_concurrency
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


class RedisLike(Protocol):
    """Minimal Redis-compatible protocol for testability."""

    def hgetall(self, name: str) -> dict[str, Any]: ...
    def hset(self, name: str, mapping: dict[str, Any]) -> int: ...
    def hincrby(self, name: str, key: str, amount: int = 1) -> int: ...
    def expire(self, name: str, time: int) -> bool: ...
    def exists(self, name: str) -> int: ...
    def delete(self, *names: str) -> int: ...
    def set(
        self,
        name: str,
        value: Any,
        ex: Optional[int] = None,
        nx: bool = False,
    ) -> bool: ...
    def get(self, name: str) -> Optional[Any]: ...
    def incr(self, name: str) -> int: ...
    def ttl(self, name: str) -> int: ...


class InMemoryRedis:
    """Dict-backed Redis fake for testing and MVP local mode.

    Supports HGETALL/HSET/HINCRBY/EXPIRE/EXISTS/DELETE/SET/GET/INCR/TTL.
    Does NOT support Lua scripts or WATCH/MULTI.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}

    def _is_expired(self, name: str) -> bool:
        exp = self._expiry.get(name)
        if exp is not None and time.time() > exp:
            self._data.pop(name, None)
            self._expiry.pop(name, None)
            return True
        return False

    def hgetall(self, name: str) -> dict[str, Any]:
        if self._is_expired(name):
            return {}
        val = self._data.get(name)
        if isinstance(val, dict):
            return dict(val)
        return {}

    def hset(self, name: str, mapping: dict[str, Any]) -> int:
        if self._is_expired(name):
            self._data[name] = {}
        if name not in self._data:
            self._data[name] = {}
        existing = self._data[name]
        if not isinstance(existing, dict):
            existing = {}
            self._data[name] = existing
        existing.update(mapping)
        return len(mapping)

    def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        if self._is_expired(name):
            self._data[name] = {}
        if name not in self._data or not isinstance(self._data.get(name), dict):
            self._data[name] = {}
        existing = self._data[name]
        current = int(existing.get(key, 0))
        new_val = current + int(amount)
        existing[key] = new_val
        return new_val

    def expire(self, name: str, time_s: int) -> bool:
        if name in self._data:
            self._expiry[name] = time.time() + time_s
            return True
        return False

    def exists(self, name: str) -> int:
        if self._is_expired(name):
            return 0
        return 1 if name in self._data else 0

    def delete(self, *names: str) -> int:
        count = 0
        for name in names:
            if name in self._data:
                del self._data[name]
                self._expiry.pop(name, None)
                count += 1
        return count

    def set(
        self,
        name: str,
        value: Any,
        ex: Optional[int] = None,
        nx: bool = False,
    ) -> bool:
        if nx and self.exists(name) > 0:
            return False
        self._data[name] = value
        if ex is not None:
            self._expiry[name] = time.time() + ex
        return True

    def get(self, name: str) -> Optional[Any]:
        if self._is_expired(name):
            return None
        return self._data.get(name)

    def incr(self, name: str) -> int:
        if self._is_expired(name):
            self._data[name] = 0
        val = self._data.get(name, 0)
        new_val = int(val) + 1
        self._data[name] = new_val
        return new_val

    def ttl(self, name: str) -> int:
        if self._is_expired(name):
            return -2
        exp = self._expiry.get(name)
        if exp is None:
            return -1 if name in self._data else -2
        return max(0, int(exp - time.time()))
