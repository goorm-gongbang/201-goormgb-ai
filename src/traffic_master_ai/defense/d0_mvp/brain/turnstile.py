"""Turnstile signal handling for D0-MVP.

Ref: annex/turnstile_spec.yaml
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol

from ..core.constants import (
    TURNSTILE_CACHE_TTL_SECONDS,
    TURNSTILE_COOLDOWN_SECONDS,
    TURNSTILE_EXTERNAL_SCORE_ON_FAILURE,
    TURNSTILE_MAX_RUNS_PER_SESSION,
    TURNSTILE_MAX_RETRIES,
    TURNSTILE_VERIFY_BACKOFF_MS,
    TURNSTILE_VERIFY_TIMEOUT_MS,
)
from ..events.catalog import (
    TURNSTILE_VERIFIED,
    VERIFY_ERROR,
    VERIFY_INVALID_TOKEN,
    VERIFY_MISSING_TOKEN,
    VERIFY_OK,
    VERIFY_TIMEOUT,
)
from ..state.dedup import DedupChecker
from ..state.keyspace import TURNSTILE_CACHE_KEY_PREFIX, TURNSTILE_RUN_KEY_PREFIX
from ..state.redis_client import RedisLike


class TurnstileVerifier(Protocol):
    """External verifier adapter interface."""

    def verify(self, token: str, timeout_ms: int) -> Mapping[str, Any]:
        """Verify one Turnstile token."""
        ...


class StubTurnstileVerifier:
    """Default no-network verifier used in local MVP mode."""

    def verify(self, token: str, timeout_ms: int) -> Mapping[str, Any]:
        del timeout_ms
        if not token:
            return {"success": False, "verifyStatus": VERIFY_MISSING_TOKEN}
        if token.startswith("invalid"):
            return {"success": False, "verifyStatus": VERIFY_INVALID_TOKEN}
        if token.startswith("timeout"):
            raise TimeoutError("turnstile verify timeout")
        if token.startswith("error"):
            raise RuntimeError("turnstile verify error")
        return {"success": True, "score": 0.9, "verifyStatus": VERIFY_OK}


@dataclass(slots=True, frozen=True)
class TurnstileVerdict:
    """Normalized Turnstile verdict payload."""

    external_score: float
    s_ext_botlikeness: float
    verify_status: str
    verify_latency_ms: int
    cached: bool
    is_duplicate: bool
    dedup_key: Optional[str]


class TurnstileHandler:
    """Turnstile verifier with FAIL_OPEN + cache + dedup behavior."""

    _CACHE_PREFIX = TURNSTILE_CACHE_KEY_PREFIX
    _RUN_PREFIX = TURNSTILE_RUN_KEY_PREFIX

    def __init__(
        self,
        *,
        redis: RedisLike,
        dedup: Optional[DedupChecker] = None,
        verifier: Optional[TurnstileVerifier] = None,
        cache_ttl_s: int = TURNSTILE_CACHE_TTL_SECONDS,
        verify_timeout_ms: int = TURNSTILE_VERIFY_TIMEOUT_MS,
        max_retries: int = TURNSTILE_MAX_RETRIES,
        retry_backoff_ms: int = TURNSTILE_VERIFY_BACKOFF_MS,
        fail_open_score: float = TURNSTILE_EXTERNAL_SCORE_ON_FAILURE,
        max_runs_per_session: int = TURNSTILE_MAX_RUNS_PER_SESSION,
        cooldown_seconds: int = TURNSTILE_COOLDOWN_SECONDS,
    ) -> None:
        self._redis = redis
        self._dedup = dedup
        self._verifier = verifier or StubTurnstileVerifier()
        self._cache_ttl_s = cache_ttl_s
        self._verify_timeout_ms = verify_timeout_ms
        self._max_retries = max(0, max_retries)
        self._retry_backoff_ms = max(0, retry_backoff_ms)
        self._fail_open_score = fail_open_score
        self._max_runs_per_session = max(1, max_runs_per_session)
        self._cooldown_seconds = max(0, cooldown_seconds)

    def should_trigger(
        self,
        *,
        session_id: str,
        ts_ms: int,
        max_runs_per_session: Optional[int] = None,
        cooldown_seconds: Optional[int] = None,
    ) -> bool:
        """Check per-session trigger budget and cooldown."""
        max_runs = self._max_runs_per_session if max_runs_per_session is None else max(1, max_runs_per_session)
        cooldown = self._cooldown_seconds if cooldown_seconds is None else max(0, cooldown_seconds)
        state = self._read_run_state(session_id)
        if state is None:
            return True
        if int(state.get("count", 0)) >= max_runs:
            return False
        last_triggered_at_ms = int(state.get("lastTriggeredAtMs", 0))
        if cooldown <= 0:
            return True
        return ts_ms - last_triggered_at_ms >= cooldown * 1000

    def mark_triggered(
        self,
        *,
        session_id: str,
        ts_ms: int,
        cooldown_seconds: Optional[int] = None,
        cache_ttl_s: Optional[int] = None,
    ) -> dict[str, int]:
        """Record that one Turnstile verification was triggered."""
        cooldown = self._cooldown_seconds if cooldown_seconds is None else max(0, cooldown_seconds)
        ttl_override = self._cache_ttl_s if cache_ttl_s is None else max(1, cache_ttl_s)
        state = self._read_run_state(session_id)
        count = 0 if state is None else int(state.get("count", 0))
        updated = {
            "count": count + 1,
            "lastTriggeredAtMs": ts_ms,
        }
        ttl_s = max(ttl_override, (cooldown * 2) + 60)
        self._redis.set(self._run_key(session_id), json.dumps(updated), ex=ttl_s)
        return updated

    def verify(
        self,
        *,
        session_id: str,
        trace_id: str,
        trigger_id: str,
        ts_ms: int,
        token: Optional[str],
        timeout_ms: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_backoff_ms: Optional[int] = None,
        cache_ttl_s: Optional[int] = None,
        fail_open_score: Optional[float] = None,
    ) -> TurnstileVerdict:
        """Verify one token and return normalized external score.

        Ref: annex/turnstile_spec.yaml#verification_policy
        """
        dedup_key: Optional[str] = None
        is_duplicate = False
        dedup_event_type = f"{TURNSTILE_VERIFIED}:{trigger_id}"
        if self._dedup is not None:
            dedup_key = self._dedup.dedup_key(trace_id, dedup_event_type, ts_ms)
            is_duplicate = self._dedup.check_and_mark(trace_id, dedup_event_type, ts_ms)

        cache_key = self._cache_key(session_id, trigger_id)
        cached = self._read_cache(cache_key)
        cache_ttl = self._cache_ttl_s if cache_ttl_s is None else max(1, cache_ttl_s)
        retries = self._max_retries if max_retries is None else max(0, max_retries)
        backoff_ms = self._retry_backoff_ms if retry_backoff_ms is None else max(0, retry_backoff_ms)
        fail_open = (
            self._fail_open_score
            if fail_open_score is None
            else _clamp(fail_open_score, 0.0, 1.0)
        )

        if cached is not None:
            return TurnstileVerdict(
                external_score=float(cached["external_score"]),
                s_ext_botlikeness=1.0 - float(cached["external_score"]),
                verify_status=str(cached["verify_status"]),
                verify_latency_ms=int(cached["verify_latency_ms"]),
                cached=True,
                is_duplicate=is_duplicate,
                dedup_key=dedup_key,
            )

        if is_duplicate:
            return self._fallback_verdict(
                status=VERIFY_ERROR,
                dedup_key=dedup_key,
                is_duplicate=True,
                cached=False,
                latency_ms=0,
                fail_open_score=fail_open,
            )

        if not token:
            verdict = self._fallback_verdict(
                status=VERIFY_MISSING_TOKEN,
                dedup_key=dedup_key,
                is_duplicate=False,
                cached=False,
                latency_ms=0,
                fail_open_score=fail_open,
            )
            self._write_cache(cache_key, verdict, cache_ttl_s=cache_ttl)
            return verdict

        started_at = time.time()
        attempt = 0
        timeout = timeout_ms or self._verify_timeout_ms
        while True:
            try:
                raw = self._verifier.verify(token, timeout)
                if attempt < retries and _should_retry_raw_result(raw):
                    attempt += 1
                    self._sleep_backoff(backoff_ms)
                    continue
                verdict = self._normalize_verifier_result(
                    raw,
                    int((time.time() - started_at) * 1000),
                    dedup_key,
                    fail_open_score=fail_open,
                )
                break
            except TimeoutError:
                if attempt < retries:
                    attempt += 1
                    self._sleep_backoff(backoff_ms)
                    continue
                verdict = self._fallback_verdict(
                    status=VERIFY_TIMEOUT,
                    dedup_key=dedup_key,
                    is_duplicate=False,
                    cached=False,
                    latency_ms=int((time.time() - started_at) * 1000),
                    fail_open_score=fail_open,
                )
                break
            except Exception:
                if attempt < retries:
                    attempt += 1
                    self._sleep_backoff(backoff_ms)
                    continue
                verdict = self._fallback_verdict(
                    status=VERIFY_ERROR,
                    dedup_key=dedup_key,
                    is_duplicate=False,
                    cached=False,
                    latency_ms=int((time.time() - started_at) * 1000),
                    fail_open_score=fail_open,
                )
                break

        self._write_cache(cache_key, verdict, cache_ttl_s=cache_ttl)
        return verdict

    def _normalize_verifier_result(
        self,
        raw: Mapping[str, Any],
        latency_ms: int,
        dedup_key: Optional[str],
        *,
        fail_open_score: float,
    ) -> TurnstileVerdict:
        status_raw = raw.get("verifyStatus")
        success = bool(raw.get("success", False))

        if status_raw in {VERIFY_OK, VERIFY_TIMEOUT, VERIFY_ERROR, VERIFY_INVALID_TOKEN, VERIFY_MISSING_TOKEN}:
            status = str(status_raw)
        elif success:
            status = VERIFY_OK
        else:
            status = VERIFY_INVALID_TOKEN

        if not success:
            external = fail_open_score
        else:
            score = raw.get("score")
            if score is None:
                external = 1.0
            else:
                external = _clamp(_to_float(score, 1.0), 0.0, 1.0)

        return TurnstileVerdict(
            external_score=external,
            s_ext_botlikeness=1.0 - external,
            verify_status=status,
            verify_latency_ms=max(latency_ms, 0),
            cached=False,
            is_duplicate=False,
            dedup_key=dedup_key,
        )

    def _fallback_verdict(
        self,
        *,
        status: str,
        dedup_key: Optional[str],
        is_duplicate: bool,
        cached: bool,
        latency_ms: int,
        fail_open_score: float,
    ) -> TurnstileVerdict:
        external = _clamp(fail_open_score, 0.0, 1.0)
        return TurnstileVerdict(
            external_score=external,
            s_ext_botlikeness=1.0 - external,
            verify_status=status,
            verify_latency_ms=max(latency_ms, 0),
            cached=cached,
            is_duplicate=is_duplicate,
            dedup_key=dedup_key,
        )

    def _cache_key(self, session_id: str, turnstile_action: str) -> str:
        return f"{self._CACHE_PREFIX}{session_id}|{turnstile_action}"

    def _run_key(self, session_id: str) -> str:
        return f"{self._RUN_PREFIX}{session_id}"

    def _read_cache(self, key: str) -> Optional[dict[str, Any]]:
        raw = self._redis.get(key)
        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return None
        if isinstance(raw, dict):
            return raw
        return None

    def _write_cache(
        self,
        key: str,
        verdict: TurnstileVerdict,
        *,
        cache_ttl_s: int,
    ) -> None:
        payload = {
            "external_score": verdict.external_score,
            "verify_status": verdict.verify_status,
            "verify_latency_ms": verdict.verify_latency_ms,
            "verified_at_ms": int(time.time() * 1000),
        }
        self._redis.set(key, json.dumps(payload), ex=cache_ttl_s)

    def _read_run_state(self, session_id: str) -> Optional[dict[str, Any]]:
        raw = self._redis.get(self._run_key(session_id))
        if raw is None:
            return None
        return _json_dict(raw)

    def _sleep_backoff(self, backoff_ms: int) -> None:
        if backoff_ms <= 0:
            return
        time.sleep(backoff_ms / 1000.0)



def _to_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        num = float(value)
        if num != num:
            return default
        return num
    except (TypeError, ValueError):
        return default



def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))


def _should_retry_raw_result(raw: Mapping[str, Any]) -> bool:
    status_code = raw.get("status_code", raw.get("http_status", raw.get("code")))
    try:
        return 500 <= int(status_code) < 600
    except (TypeError, ValueError):
        return False


def _json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    if isinstance(raw, dict):
        return dict(raw)
    return {}


__all__ = ["TurnstileHandler", "TurnstileVerdict", "TurnstileVerifier", "StubTurnstileVerifier"]
