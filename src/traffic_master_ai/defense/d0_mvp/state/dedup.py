"""Dedup checker — prevents duplicate event processing.

Ref: L1/runtime/events.yaml#dedup
     key_schema: traceId|eventType|floor(tsMs/tsBucketMs)
"""

from __future__ import annotations

import math
from typing import Optional

from ..core.constants import DEDUP_TS_BUCKET_MS, DEDUP_TTL_SECONDS
from .keyspace import DEDUP_KEY_PREFIX
from .redis_client import RedisLike


class DedupChecker:
    """Check and mark events as deduplicated.

    Ref: events.yaml#dedup
    - key = traceId|eventType|floor(tsMs/tsBucketMs)
    - TTL = TM_DEDUP_TTL_SECONDS (default 600)
    - Behaviour: duplicate → no-op + audit with isDuplicate=true
    """

    def __init__(
        self,
        redis: RedisLike,
        ts_bucket_ms: int = DEDUP_TS_BUCKET_MS,
        ttl_s: int = DEDUP_TTL_SECONDS,
        key_prefix: str = DEDUP_KEY_PREFIX,
    ) -> None:
        self._redis = redis
        self._ts_bucket_ms = ts_bucket_ms
        self._ttl_s = ttl_s
        self._key_prefix = key_prefix

    def dedup_key(
        self,
        trace_id: str,
        event_type: str,
        ts_ms: int,
    ) -> str:
        """Build the dedup Redis key.

        Ref: events.yaml#dedup.key_schema
        """
        bucket = math.floor(ts_ms / self._ts_bucket_ms)
        return f"{self._key_prefix}{trace_id}|{event_type}|{bucket}"

    def is_duplicate(
        self,
        trace_id: str,
        event_type: str,
        ts_ms: int,
    ) -> bool:
        """Check if event already processed.

        Returns True if duplicate (should be no-op'd).
        """
        key = self.dedup_key(trace_id, event_type, ts_ms)
        return self._redis.exists(key) > 0

    def mark(
        self,
        trace_id: str,
        event_type: str,
        ts_ms: int,
    ) -> bool:
        """Mark event as processed. Returns True if this was the first time.

        Uses SET with EX for atomic set-if-not-exists.
        """
        key = self.dedup_key(trace_id, event_type, ts_ms)
        return self._redis.set(key, "1", ex=self._ttl_s, nx=True)

    def check_and_mark(
        self,
        trace_id: str,
        event_type: str,
        ts_ms: int,
    ) -> bool:
        """Combined check + mark.

        Returns True if event IS a duplicate (should skip processing).
        """
        return not self.mark(trace_id, event_type, ts_ms)
