"""Offline LLM analysis pipeline for defense decision logs.

This module is intentionally decoupled from runtime `/evaluate`.
It consumes audit logs and produces:
- session-level LLM judgments
- policy patch candidates (manual-review-first)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

OfflineVerdict = Literal["TRUE_BOT", "HUMAN", "UNCERTAIN", "UNAVAILABLE"]
OFFLINE_PROMPT_VERSION = "offline-judge-v1.1-triage-batch"
OFFLINE_SYSTEM_PROMPT = """
You are a senior offline fraud analyst for ticketing bot detection.
Primary objective is precision-first detection:
- Avoid false positives on real humans.
- Return TRUE_BOT only when evidence is strong and consistent.

Input semantics:
- You receive session aggregate vectors with compact keys.
- Signals may be noisy or incomplete.
- Missing signals are NOT evidence.

Decision policy (strict):
1) TRUE_BOT only if:
   - At least two independent strong indicators exist, AND
   - No strong counter-human indicators dominate.
2) HUMAN if:
   - No meaningful suspicious pattern, AND
   - Human-consistent evidence is present.
3) UNCERTAIN for conflicts, sparse evidence, or ambiguous patterns.

Strong suspicious indicators (examples):
- cfb > 0, cf >= 2, blk > 0
- repetitive high-risk rule hit count
- sustained high avg risk

Human-consistent indicators (examples):
- cp > 0 with deny == 0
- low avg risk and stable benign pattern

Output requirements:
- Return strict JSON with shape:
  {"results":[{"session_id":"...", "verdict":"TRUE_BOT|HUMAN|UNCERTAIN",
               "confidence":0.0-1.0,
               "reasoning_key":"short_token",
               "anomalous_features":["token1","token2"]}]}
- No markdown. No extra top-level keys.
""".strip()


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(slots=True)
class OfflineJudgeConfig:
    enabled: bool = True
    mode: str = "mock"
    timeout_ms: int = 15000
    model_name: str = "gpt-5-mini"
    api_url: str = "https://api.openai.com/v1/responses"
    api_key: str = ""
    app_name: str = "traffic-master-ai-offline"
    llm_batch_size: int = 8
    triage_enabled: bool = True
    compact_top_k: int = 4
    reasoning_effort: str = "minimal"

    @staticmethod
    def from_env() -> OfflineJudgeConfig:
        return OfflineJudgeConfig(
            enabled=_env_bool("TM_OFFLINE_LLM_ENABLED", True),
            mode=os.getenv("TM_OFFLINE_LLM_MODE", "mock").strip().lower(),
            timeout_ms=int(os.getenv("TM_OFFLINE_LLM_TIMEOUT_MS", "15000")),
            model_name=os.getenv("TM_OFFLINE_LLM_MODEL", "gpt-5-mini"),
            api_url=os.getenv(
                "TM_OFFLINE_LLM_API_URL",
                "https://api.openai.com/v1/responses",
            ),
            api_key=os.getenv("TM_OFFLINE_LLM_API_KEY", ""),
            app_name=os.getenv("TM_OFFLINE_LLM_APP_NAME", "traffic-master-ai-offline"),
            llm_batch_size=max(1, int(os.getenv("TM_OFFLINE_LLM_BATCH_SIZE", "8"))),
            triage_enabled=_env_bool("TM_OFFLINE_TRIAGE_ENABLED", True),
            compact_top_k=max(1, int(os.getenv("TM_OFFLINE_COMPACT_TOP_K", "4"))),
            reasoning_effort=os.getenv("TM_OFFLINE_LLM_REASONING_EFFORT", "minimal").strip().lower(),
        )


@dataclass(slots=True)
class SessionAggregate:
    session_id: str
    decision_count: int = 0
    deny_count: int = 0
    allow_count: int = 0
    challenge_verified_fail_count: int = 0
    challenge_verified_block_count: int = 0
    challenge_verified_pass_count: int = 0
    gate_count: int = 0
    throttle_count: int = 0
    block_count: int = 0
    avg_risk_score: float = 0.0
    _risk_sum: float = 0.0
    _risk_n: int = 0
    rule_hits: dict[str, int] = field(default_factory=dict)
    methods: dict[str, int] = field(default_factory=dict)
    paths: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "decision_count": self.decision_count,
            "deny_count": self.deny_count,
            "allow_count": self.allow_count,
            "challenge_verified_fail_count": self.challenge_verified_fail_count,
            "challenge_verified_block_count": self.challenge_verified_block_count,
            "challenge_verified_pass_count": self.challenge_verified_pass_count,
            "gate_count": self.gate_count,
            "throttle_count": self.throttle_count,
            "block_count": self.block_count,
            "avg_risk_score": round(self.avg_risk_score, 4),
            "rule_hits": self.rule_hits,
            "methods": self.methods,
            "paths": self.paths,
        }

    def to_session_aggregate_vector(self, *, top_k: int = 4) -> dict[str, Any]:
        top_hits = sorted(
            self.rule_hits.items(),
            key=lambda item: item[1],
            reverse=True,
        )[: max(1, top_k)]
        top_paths = sorted(
            self.paths.items(),
            key=lambda item: item[1],
            reverse=True,
        )[: max(1, top_k)]
        top_methods = sorted(
            self.methods.items(),
            key=lambda item: item[1],
            reverse=True,
        )[: max(1, top_k)]
        # Compact schema to reduce prompt tokens while preserving key evidence.
        return {
            "sid": self.session_id,
            "dc": self.decision_count,
            "deny": self.deny_count,
            "allow": self.allow_count,
            "cf": self.challenge_verified_fail_count,
            "cfb": self.challenge_verified_block_count,
            "cp": self.challenge_verified_pass_count,
            "gate": self.gate_count,
            "thr": self.throttle_count,
            "blk": self.block_count,
            "r_avg": round(self.avg_risk_score, 4),
            "hits": top_hits,
            "paths": top_paths,
            "mth": top_methods,
        }


@dataclass(slots=True)
class OfflineJudgeResult:
    session_id: str
    verdict: OfflineVerdict
    confidence: float
    reasoning_key: str
    anomalous_features: list[str]
    fallback_reason: str | None = None
    source: str = "offline_llm"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "verdict": self.verdict,
            "confidence": round(max(0.0, min(self.confidence, 1.0)), 4),
            "reasoning_key": self.reasoning_key,
            "anomalous_features": self.anomalous_features,
            "fallback_reason": self.fallback_reason,
            "source": self.source,
        }


def load_decision_audit(path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    audit_path = Path(path)
    if not audit_path.exists():
        return records
    with audit_path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    return records


def aggregate_sessions(records: list[dict[str, Any]]) -> dict[str, SessionAggregate]:
    out: dict[str, SessionAggregate] = {}
    for rec in records:
        session_id = str(rec.get("session_id") or "")
        if not session_id:
            continue
        agg = out.get(session_id)
        if agg is None:
            agg = SessionAggregate(session_id=session_id)
            out[session_id] = agg

        event_type = str(rec.get("event_type") or "")
        if event_type == "EVALUATE":
            agg.decision_count += 1
            allow = bool(rec.get("allow", True))
            if allow:
                agg.allow_count += 1
            else:
                agg.deny_count += 1

            action = str(rec.get("action") or "").upper()
            if action == "GATE":
                agg.gate_count += 1
            elif action == "THROTTLE":
                agg.throttle_count += 1
            elif action == "BLOCK":
                agg.block_count += 1

            risk = rec.get("risk_score")
            if isinstance(risk, (int, float)):
                agg._risk_sum += float(risk)
                agg._risk_n += 1
                agg.avg_risk_score = agg._risk_sum / max(1, agg._risk_n)

            for hit in rec.get("rule_hits") or []:
                key = str(hit)
                agg.rule_hits[key] = agg.rule_hits.get(key, 0) + 1

            method = str(rec.get("method") or "").upper()
            if method:
                agg.methods[method] = agg.methods.get(method, 0) + 1
            path = str(rec.get("path") or "")
            if path:
                agg.paths[path] = agg.paths.get(path, 0) + 1
            continue

        if event_type == "CHALLENGE_VERIFIED":
            payload = rec.get("payload") or {}
            result = str(payload.get("result") or "").upper()
            if result == "FAILED":
                agg.challenge_verified_fail_count += 1
            elif result == "BLOCKED":
                agg.challenge_verified_block_count += 1
            elif result == "PASSED":
                agg.challenge_verified_pass_count += 1
    return out


def select_candidates(
    aggregates: dict[str, SessionAggregate],
    *,
    min_decisions: int,
    limit: int,
) -> list[SessionAggregate]:
    candidates: list[SessionAggregate] = []
    for agg in aggregates.values():
        if agg.decision_count < min_decisions:
            continue
        if _is_suspicious_session(agg) or _is_human_like_session(agg):
            candidates.append(agg)
    candidates.sort(
        key=lambda item: (
            item.block_count + item.challenge_verified_block_count,
            item.challenge_verified_fail_count,
            item.avg_risk_score,
            item.deny_count,
        ),
        reverse=True,
    )
    return candidates[:limit]


def _is_suspicious_session(agg: SessionAggregate) -> bool:
    repetitive_t2 = agg.rule_hits.get("R1_REPETITIVE_PATTERN_T2", 0)
    moderate_suspicion = (
        agg.deny_count >= 1
        and (agg.gate_count >= 1 or agg.throttle_count >= 1 or agg.avg_risk_score >= 0.35)
    )
    return (
        agg.block_count > 0
        or agg.challenge_verified_block_count > 0
        or agg.challenge_verified_fail_count >= 2
        or repetitive_t2 > 0
        or agg.avg_risk_score >= 0.65
        or moderate_suspicion
    )


def _is_human_like_session(agg: SessionAggregate) -> bool:
    return (
        agg.deny_count == 0
        and agg.challenge_verified_pass_count > 0
        and agg.avg_risk_score <= 0.25
    )


def triage_candidates(
    candidates: list[SessionAggregate],
) -> tuple[list[OfflineJudgeResult], list[SessionAggregate], dict[str, int]]:
    auto_results: list[OfflineJudgeResult] = []
    llm_candidates: list[SessionAggregate] = []
    for agg in candidates:
        if _is_strong_auto_bot(agg):
            auto_results.append(
                OfflineJudgeResult(
                    session_id=agg.session_id,
                    verdict="TRUE_BOT",
                    confidence=0.93,
                    reasoning_key="triage_auto_bot_strong_evidence",
                    anomalous_features=_top_rule_hit_tokens(agg),
                    source="offline_triage",
                )
            )
            continue
        if _is_strong_auto_human(agg):
            auto_results.append(
                OfflineJudgeResult(
                    session_id=agg.session_id,
                    verdict="HUMAN",
                    confidence=0.88,
                    reasoning_key="triage_auto_human_consistent",
                    anomalous_features=[],
                    source="offline_triage",
                )
            )
            continue
        llm_candidates.append(agg)
    stats = {
        "auto_bot_count": sum(1 for row in auto_results if row.verdict == "TRUE_BOT"),
        "auto_human_count": sum(1 for row in auto_results if row.verdict == "HUMAN"),
        "llm_count": len(llm_candidates),
        "total": len(candidates),
    }
    return auto_results, llm_candidates, stats


def _top_rule_hit_tokens(agg: SessionAggregate, *, limit: int = 4) -> list[str]:
    return [
        key
        for key, _count in sorted(
            agg.rule_hits.items(),
            key=lambda item: item[1],
            reverse=True,
        )[: max(1, limit)]
    ]


def _is_strong_auto_bot(agg: SessionAggregate) -> bool:
    repetitive_t2 = agg.rule_hits.get("R1_REPETITIVE_PATTERN_T2", 0)
    queue_exit_only = (
        bool(agg.rule_hits)
        and all(key == "S3_QUEUE_EXIT_VQA_REQUIRED" for key in agg.rule_hits.keys())
    )
    strong_hit_count = 0
    if agg.block_count > 0 or agg.challenge_verified_block_count > 0:
        strong_hit_count += 1
    if agg.challenge_verified_fail_count >= 2:
        strong_hit_count += 1
    if repetitive_t2 >= 2:
        strong_hit_count += 1
    if agg.avg_risk_score >= 0.82 and agg.deny_count >= 2:
        strong_hit_count += 1
    # Single fail + challenge-block is already strong in mandatory VQA gate context.
    if agg.challenge_verified_block_count > 0 and agg.challenge_verified_fail_count >= 1:
        strong_hit_count += 1
    # Single repetitive high-risk rule with sustained risk should be suspicious unless it's queue-gate-only.
    if (not queue_exit_only) and repetitive_t2 >= 1 and agg.avg_risk_score >= 0.7 and agg.deny_count >= 1:
        strong_hit_count += 1
    return strong_hit_count >= 2


def _is_strong_auto_human(agg: SessionAggregate) -> bool:
    repetitive_t2 = agg.rule_hits.get("R1_REPETITIVE_PATTERN_T2", 0)
    return (
        agg.deny_count == 0
        and agg.challenge_verified_pass_count >= 1
        and agg.block_count == 0
        and agg.challenge_verified_block_count == 0
        and agg.challenge_verified_fail_count == 0
        and repetitive_t2 == 0
        and agg.avg_risk_score <= 0.2
    )


class OfflineJudge:
    def __init__(self, cfg: OfflineJudgeConfig) -> None:
        self._cfg = cfg

    def judge(self, agg: SessionAggregate) -> OfflineJudgeResult:
        return self.judge_many([agg])[0]

    def judge_many(self, aggregates: list[SessionAggregate]) -> list[OfflineJudgeResult]:
        if not aggregates:
            return []
        if not self._cfg.enabled:
            return [
                OfflineJudgeResult(
                    session_id=agg.session_id,
                    verdict="UNAVAILABLE",
                    confidence=0.0,
                    reasoning_key="offline_llm_disabled",
                    anomalous_features=[],
                    fallback_reason="DISABLED",
                )
                for agg in aggregates
            ]
        if self._cfg.mode == "mock":
            return [self._judge_mock(agg) for agg in aggregates]
        if self._cfg.mode == "openai_compatible":
            return self._judge_openai_compatible_many(aggregates)
        return [
            OfflineJudgeResult(
                session_id=agg.session_id,
                verdict="UNAVAILABLE",
                confidence=0.0,
                reasoning_key="unsupported_offline_mode",
                anomalous_features=[],
                fallback_reason="UNSUPPORTED_MODE",
            )
            for agg in aggregates
        ]

    def _judge_mock(self, agg: SessionAggregate) -> OfflineJudgeResult:
        score = 0.0
        feats: list[str] = []
        if agg.block_count + agg.challenge_verified_block_count > 0:
            score += 0.45
            feats.append("blocked_or_challenge_blocked")
        if agg.challenge_verified_fail_count >= 2:
            score += 0.3
            feats.append("challenge_fail_ge_2")
        if agg.rule_hits.get("R1_REPETITIVE_PATTERN_T2", 0) > 0:
            score += 0.25
            feats.append("repetitive_pattern_t2")
        if agg.avg_risk_score >= 0.65:
            score += 0.2
            feats.append("avg_risk_score_high")
        if agg.gate_count >= 2:
            score += 0.15
            feats.append("gate_repeated")

        score = max(0.0, min(score, 0.99))
        if score >= 0.72:
            return OfflineJudgeResult(
                session_id=agg.session_id,
                verdict="TRUE_BOT",
                confidence=round(score, 2),
                reasoning_key="offline_mock_high_risk",
                anomalous_features=feats,
            )
        if score <= 0.15 and agg.challenge_verified_pass_count > 0 and agg.deny_count == 0:
            return OfflineJudgeResult(
                session_id=agg.session_id,
                verdict="HUMAN",
                confidence=0.75,
                reasoning_key="offline_mock_low_risk",
                anomalous_features=[],
            )
        return OfflineJudgeResult(
            session_id=agg.session_id,
            verdict="UNCERTAIN",
            confidence=round(max(0.4, 1.0 - score), 2),
            reasoning_key="offline_mock_uncertain",
            anomalous_features=feats,
        )

    def _judge_openai_compatible_many(
        self,
        aggregates: list[SessionAggregate],
    ) -> list[OfflineJudgeResult]:
        if not self._cfg.api_key:
            return [
                OfflineJudgeResult(
                    session_id=agg.session_id,
                    verdict="UNAVAILABLE",
                    confidence=0.0,
                    reasoning_key="offline_missing_api_key",
                    anomalous_features=[],
                    fallback_reason="MISSING_API_KEY",
                )
                for agg in aggregates
            ]

        out: list[OfflineJudgeResult] = []
        batch_size = max(1, self._cfg.llm_batch_size)
        use_responses_api = _is_responses_api(self._cfg.api_url)
        for start in range(0, len(aggregates), batch_size):
            batch = aggregates[start : start + batch_size]
            vectors = [
                agg.to_session_aggregate_vector(top_k=self._cfg.compact_top_k)
                for agg in batch
            ]
            payload_input = {
                "prompt_version": OFFLINE_PROMPT_VERSION,
                "sessions": vectors,
            }
            if use_responses_api:
                body = {
                    "model": self._cfg.model_name,
                    "instructions": OFFLINE_SYSTEM_PROMPT,
                    "input": json.dumps(payload_input, ensure_ascii=False),
                }
                if _should_send_reasoning(self._cfg):
                    body["reasoning"] = {"effort": self._cfg.reasoning_effort}
            else:
                body = {
                    "model": self._cfg.model_name,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": OFFLINE_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": json.dumps(payload_input, ensure_ascii=False),
                        },
                    ],
                }
            raw = json.dumps(body).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._cfg.api_key}",
            }
            # OpenRouter uses routing metadata headers; OpenAI ignores/doesn't require them.
            if "openrouter.ai" in self._cfg.api_url:
                headers["HTTP-Referer"] = "https://traffic-master.local"
                headers["X-Title"] = self._cfg.app_name
            req = urllib.request.Request(
                self._cfg.api_url,
                data=raw,
                method="POST",
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=self._cfg.timeout_ms / 1000.0) as resp:
                    text = resp.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                try:
                    _ = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                fallback = f"HTTP_{int(getattr(e, 'code', 0) or 0)}"
                out.extend(
                    _unavailable_results_for_batch(
                        batch,
                        fallback_reason=fallback,
                        reasoning_key="offline_http_error",
                    )
                )
                continue
            except urllib.error.URLError:
                out.extend(
                    _unavailable_results_for_batch(
                        batch,
                        fallback_reason="NETWORK_ERROR",
                        reasoning_key="offline_network_error",
                    )
                )
                continue
            except TimeoutError:
                out.extend(
                    _unavailable_results_for_batch(
                        batch,
                        fallback_reason="TIMEOUT",
                        reasoning_key="offline_timeout",
                    )
                )
                continue

            out.extend(
                _parse_openai_batch_response(
                    text=text,
                    batch=batch,
                    use_responses_api=use_responses_api,
                )
            )
        return out


def _unavailable_results_for_batch(
    batch: list[SessionAggregate],
    *,
    fallback_reason: str,
    reasoning_key: str,
) -> list[OfflineJudgeResult]:
    return [
        OfflineJudgeResult(
            session_id=agg.session_id,
            verdict="UNAVAILABLE",
            confidence=0.0,
            reasoning_key=reasoning_key,
            anomalous_features=[],
            fallback_reason=fallback_reason,
        )
        for agg in batch
    ]


def _parse_openai_batch_response(
    *,
    text: str,
    batch: list[SessionAggregate],
    use_responses_api: bool,
) -> list[OfflineJudgeResult]:
    try:
        parsed = json.loads(text)
        if use_responses_api:
            payload = _extract_responses_payload(parsed)
        else:
            content = parsed["choices"][0]["message"]["content"]
            payload = _extract_json_payload(content)
        rows = payload.get("results", [])
        if not isinstance(rows, list):
            raise ValueError("results is not list")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return _unavailable_results_for_batch(
            batch,
            fallback_reason="PARSE_ERROR",
            reasoning_key="offline_parse_error",
        )

    by_session: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        session_id = str(row.get("session_id") or "")
        if session_id:
            by_session[session_id] = row

    out: list[OfflineJudgeResult] = []
    for agg in batch:
        row = by_session.get(agg.session_id)
        if row is None:
            out.append(
                OfflineJudgeResult(
                    session_id=agg.session_id,
                    verdict="UNAVAILABLE",
                    confidence=0.0,
                    reasoning_key="offline_missing_batch_item",
                    anomalous_features=[],
                    fallback_reason="MISSING_BATCH_ITEM",
                )
            )
            continue
        verdict_raw = str(row.get("verdict", "UNCERTAIN")).upper()
        if verdict_raw not in {"TRUE_BOT", "HUMAN", "UNCERTAIN"}:
            verdict_raw = "UNCERTAIN"
        try:
            confidence = float(row.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(confidence, 1.0))
        reasoning_key = str(row.get("reasoning_key", "offline_no_reasoning_key"))
        af_raw = row.get("anomalous_features", [])
        if not isinstance(af_raw, list):
            af_raw = []
        feats = [str(v) for v in af_raw[:20]]
        out.append(
            OfflineJudgeResult(
                session_id=agg.session_id,
                verdict=verdict_raw,  # type: ignore[arg-type]
                confidence=confidence,
                reasoning_key=reasoning_key,
                anomalous_features=feats,
            )
        )
    return out


def _is_responses_api(api_url: str) -> bool:
    normalized = api_url.strip().lower()
    return "/responses" in normalized


def _should_send_reasoning(cfg: OfflineJudgeConfig) -> bool:
    effort = cfg.reasoning_effort.strip().lower()
    if not effort:
        return False
    model = cfg.model_name.strip().lower()
    return model.startswith("gpt-5") or model.startswith("o")


def _extract_responses_payload(parsed: dict[str, Any]) -> dict[str, Any]:
    output_text = parsed.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return _extract_json_payload(output_text)
    output = parsed.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "output_text":
                    text = c.get("text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text)
        if chunks:
            return _extract_json_payload("\n".join(chunks))
    raise ValueError("responses_output_missing")


def _extract_json_payload(text: str) -> dict[str, Any]:
    raw = text.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        sliced = raw[start : end + 1]
        parsed = json.loads(sliced)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("json_payload_not_found")


def build_policy_patch_candidates(results: list[OfflineJudgeResult]) -> list[dict[str, Any]]:
    total = len(results)
    if total == 0:
        return []
    true_bot = [r for r in results if r.verdict == "TRUE_BOT"]
    human = [r for r in results if r.verdict == "HUMAN"]
    uncertain = [r for r in results if r.verdict == "UNCERTAIN"]

    patches: list[dict[str, Any]] = []
    if len(true_bot) >= max(3, int(total * 0.4)):
        patches.append(
            {
                "id": "suggest-tighten-t2-throttle",
                "target": "TM_T2_THROTTLE_MS",
                "current": 1800,
                "proposed": 2200,
                "reason": "offline_true_bot_ratio_high",
                "manual_review_required": True,
            }
        )
    if len(human) >= max(3, int(total * 0.5)):
        patches.append(
            {
                "id": "suggest-relax-t1-throttle",
                "target": "TM_T1_THROTTLE_MS",
                "current": 200,
                "proposed": 120,
                "reason": "offline_human_ratio_high",
                "manual_review_required": True,
            }
        )
    if len(uncertain) >= max(3, int(total * 0.5)):
        patches.append(
            {
                "id": "suggest-more-data-before-policy-change",
                "target": "NO_CHANGE",
                "reason": "offline_uncertain_ratio_high",
                "manual_review_required": True,
            }
        )
    return patches


def write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: str, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_offline_batch(
    *,
    decision_audit_path: str,
    min_log_count: int,
    min_decisions_per_session: int,
    candidate_limit: int,
    cfg: OfflineJudgeConfig,
) -> dict[str, Any]:
    records = load_decision_audit(decision_audit_path)
    if len(records) < max(0, min_log_count):
        return {
            "status": "SKIPPED",
            "reason": "NOT_ENOUGH_LOGS",
            "decision_log_path": decision_audit_path,
            "record_count": len(records),
            "min_log_count": max(0, min_log_count),
            "candidate_count": 0,
            "results": [],
            "patches": [],
        }

    aggregates = aggregate_sessions(records)
    candidates = select_candidates(
        aggregates,
        min_decisions=max(1, min_decisions_per_session),
        limit=max(1, candidate_limit),
    )
    judge = OfflineJudge(cfg)
    triage_stats = {
        "enabled": bool(cfg.triage_enabled),
        "auto_bot_count": 0,
        "auto_human_count": 0,
        "llm_count": len(candidates),
        "total": len(candidates),
    }
    if cfg.triage_enabled:
        triage_auto, llm_candidates, stats = triage_candidates(candidates)
        triage_stats.update(stats)
    else:
        triage_auto = []
        llm_candidates = candidates
    judged = triage_auto + judge.judge_many(llm_candidates)
    patches = build_policy_patch_candidates(judged)
    return {
        "status": "OK",
        "reason": None,
        "decision_log_path": decision_audit_path,
        "record_count": len(records),
        "session_count": len(aggregates),
        "candidate_count": len(candidates),
        "llm_candidate_count": len(llm_candidates),
        "prompt_version": OFFLINE_PROMPT_VERSION,
        "llm_batch_size": max(1, cfg.llm_batch_size),
        "triage": triage_stats,
        "results": [item.to_dict() for item in judged],
        "patches": patches,
    }
