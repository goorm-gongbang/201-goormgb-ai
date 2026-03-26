"""Runtime state store abstractions for defense decision service."""

from __future__ import annotations

import json
import time
from threading import Lock
from typing import Protocol

from .models import RuntimeStateSnapshot
from .settings import read_int, read_str


class RuntimeStateStore(Protocol):
    """Minimal interface for session runtime state."""

    def get(self, session_id: str) -> RuntimeStateSnapshot | None:
        """Return the current session state, or None when missing."""

    def upsert(self, session_id: str, snapshot: RuntimeStateSnapshot) -> None:
        """Write session state with TTL semantics."""


class InMemoryStateStore(RuntimeStateStore):
    """In-memory fallback store with TTL support."""

    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = Lock()
        self._data: dict[str, tuple[RuntimeStateSnapshot, float]] = {}

    def get(self, session_id: str) -> RuntimeStateSnapshot | None:
        now = time.time()
        with self._lock:
            item = self._data.get(session_id)
            if item is None:
                return None
            snapshot, expires_at = item
            if expires_at <= now:
                self._data.pop(session_id, None)
                return None
            return snapshot

    def upsert(self, session_id: str, snapshot: RuntimeStateSnapshot) -> None:
        expires_at = time.time() + self.ttl_seconds
        with self._lock:
            self._data[session_id] = (snapshot, expires_at)


class RedisStateStore(RuntimeStateStore):
    """Redis-backed session state store.

    Uses key format: tm:sess:{sessionId}
    """

    def __init__(self, redis_url: str, ttl_seconds: int, key_prefix: str = "tm:sess:") -> None:
        try:
            import redis  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - import error path
            raise RuntimeError(
                "redis package is required for RedisStateStore; install with "
                "pip install redis"
            ) from exc

        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}{session_id}"

    def get(self, session_id: str) -> RuntimeStateSnapshot | None:
        raw = self._redis.get(self._key(session_id))
        if raw is None:
            return None
        payload = json.loads(raw)
        return RuntimeStateSnapshot.model_validate(payload)

    def upsert(self, session_id: str, snapshot: RuntimeStateSnapshot) -> None:
        self._redis.setex(
            self._key(session_id),
            self._ttl_seconds,
            snapshot.model_dump_json(by_alias=True),
        )


def build_runtime_store_from_settings() -> tuple[RuntimeStateStore, str]:
    """Build runtime state store from `.env.local` settings.

    Returns:
        Tuple of (store, backend_name).
    """
    ttl = read_int("TM_SESSION_STATE_TTL_SECONDS", 1800)
    redis_url = read_str("TM_REDIS_URL", "").strip()

    if redis_url:
        try:
            store = RedisStateStore(redis_url=redis_url, ttl_seconds=ttl)
            return store, "redis"
        except Exception:
            # Fallback is intentional for local development.
            pass

    return InMemoryStateStore(ttl_seconds=ttl), "memory"
