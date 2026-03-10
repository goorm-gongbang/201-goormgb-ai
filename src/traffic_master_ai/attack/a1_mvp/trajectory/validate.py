from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _percentile(sorted_vals: list[float], q: float) -> float:
    """q in [0,1]."""
    if not sorted_vals:
        return 0.0
    if q <= 0:
        return float(sorted_vals[0])
    if q >= 1:
        return float(sorted_vals[-1])
    idx = (len(sorted_vals) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


@dataclass(frozen=True, slots=True)
class MetricStats:
    n: int
    q05: float
    q50: float
    q95: float
    min: float
    max: float


def _stats(vals: list[float]) -> MetricStats:
    s = sorted(vals)
    return MetricStats(
        n=len(s),
        q05=_percentile(s, 0.05),
        q50=_percentile(s, 0.50),
        q95=_percentile(s, 0.95),
        min=float(s[0]) if s else 0.0,
        max=float(s[-1]) if s else 0.0,
    )


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _extract_float(d: dict[str, Any], key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def load_human_samples(raw_log: Path, *, dataset_id: str | None) -> list[dict[str, float]]:
    if not raw_log.exists():
        return []
    out: list[dict[str, float]] = []
    for obj in _iter_jsonl(raw_log):
        if dataset_id:
            if (obj.get("datasetId") or obj.get("dataset_id") or "") != dataset_id:
                continue
        feat = obj.get("features") or {}
        s: dict[str, float] = {}
        for k in ("linearityRatio", "tremorStdDev", "avgVelocity", "dwellTime"):
            fv = _extract_float(feat, k)
            if fv is not None:
                s[k] = fv
        if len(s) == 4:
            out.append(s)
    return out


def load_agent_samples(audit_log: Path, *, session_id: str) -> list[dict[str, float]]:
    if not audit_log.exists():
        return []
    out: list[dict[str, float]] = []
    for obj in _iter_jsonl(audit_log):
        if obj.get("stage") != "TELEMETRY":
            continue
        if (obj.get("sessionId") or "") != session_id:
            continue
        payload = obj.get("payload") or {}
        feat = payload.get("features") or {}
        s: dict[str, float] = {}
        for k in ("linearityRatio", "tremorStdDev", "avgVelocity", "dwellTime"):
            fv = _extract_float(feat, k)
            if fv is not None:
                s[k] = fv
        if len(s) == 4:
            out.append(s)
    return out


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="traffic-master-ac3-validate")
    p.add_argument("--agent-session-id", required=True, help="TM_SESSION_ID used by the agent run.")
    p.add_argument("--dataset-id", default="", help="Optional datasetId filter for human raw log.")
    p.add_argument(
        "--raw-log",
        default="platform/backend/logs/trajectory_raw.jsonl",
        help="Path to platform backend trajectory_raw.jsonl",
    )
    p.add_argument(
        "--audit-log",
        default="platform/backend/logs/decision_audit.jsonl",
        help="Path to platform backend decision_audit.jsonl",
    )
    p.add_argument("--min-in-range", type=float, default=0.80, help="Required fraction of agent samples in-range.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    raw_log = Path(args.raw_log)
    audit_log = Path(args.audit_log)
    dataset_id = args.dataset_id.strip() or None
    session_id = args.agent_session_id.strip()

    human = load_human_samples(raw_log, dataset_id=dataset_id)
    agent = load_agent_samples(audit_log, session_id=session_id)

    if not human:
        print(f"[AC-3] No human samples found in {raw_log} (dataset_id={dataset_id!r}).")
        return 1
    if not agent:
        print(f"[AC-3] No agent samples found in {audit_log} (session_id={session_id!r}).")
        return 1

    metrics = ("linearityRatio", "tremorStdDev", "avgVelocity", "dwellTime")

    ok = True
    for m in metrics:
        h_vals = [s[m] for s in human]
        a_vals = [s[m] for s in agent]
        hs = _stats(h_vals)
        lo, hi = hs.q05, hs.q95
        in_range = sum(1 for v in a_vals if lo <= v <= hi)
        frac = in_range / max(1, len(a_vals))

        print(
            f"[{m}] human(n={hs.n}) q05={hs.q05:.4f} q50={hs.q50:.4f} q95={hs.q95:.4f} | "
            f"agent(n={len(a_vals)}) in_range={in_range}/{len(a_vals)} frac={frac:.2f}"
        )

        if frac < float(args.min_in_range):
            ok = False

    if ok:
        print("[AC-3] PASS (agent telemetry is within human q05-q95 ranges).")
        return 0
    print("[AC-3] FAIL (one or more metrics outside human range).")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

