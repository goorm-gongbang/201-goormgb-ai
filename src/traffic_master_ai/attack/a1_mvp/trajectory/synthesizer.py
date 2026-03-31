from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class TrajectoryTarget:
    """Target distribution sample (derived from human telemetry)."""

    velocity_profile: str  # MVP: "ease-in-out" only (expand later)
    linearity_ratio: float
    tremor_std_dev: float
    avg_velocity: float  # px/ms
    dwell_time_ms: float


@dataclass(frozen=True, slots=True)
class TrajectoryFeatures:
    total_dist: float
    linear_dist: float
    linearity_ratio: float
    avg_velocity: float  # px/ms
    tremor_std_dev: float
    dwell_time_ms: float


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    points: list[tuple[float, float]]
    dt_ms: int
    target: TrajectoryTarget
    computed: TrajectoryFeatures


class _Welford:
    def __init__(self) -> None:
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, val: float) -> None:
        self.count += 1
        delta = val - self.mean
        self.mean += delta / self.count
        delta2 = val - self.mean
        self.m2 += delta * delta2

    def stddev(self) -> float:
        if self.count <= 1:
            return 0.0
        return math.sqrt(self.m2 / (self.count - 1))


def _clamp(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _perp_dist_to_line(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    """Perpendicular distance from P to infinite line AB (stable for long AB)."""
    dx = bx - ax
    dy = by - ay
    denom = math.hypot(dx, dy)
    if denom <= 1e-6:
        return 0.0
    # |(B-A) x (A-P)| / |B-A|
    return abs(dx * (ay - py) - (ax - px) * dy) / denom


def compute_features(points: Iterable[tuple[float, float]], *, dt_ms: int, dwell_time_ms: float) -> TrajectoryFeatures:
    pts = list(points)
    if len(pts) < 2:
        return TrajectoryFeatures(
            total_dist=0.0,
            linear_dist=0.0,
            linearity_ratio=1.0,
            avg_velocity=0.0,
            tremor_std_dev=0.0,
            dwell_time_ms=float(dwell_time_ms),
        )

    total_dist = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        total_dist += math.hypot(x1 - x0, y1 - y0)

    (ax, ay) = pts[0]
    (bx, by) = pts[-1]
    linear_dist = math.hypot(bx - ax, by - ay)
    linearity_ratio = linear_dist / total_dist if total_dist > 1e-6 else 1.0

    duration_ms = max(0.0, (len(pts) - 1) * float(dt_ms))
    avg_velocity = total_dist / duration_ms if duration_ms > 1e-6 else 0.0

    w = _Welford()
    if linear_dist > 20:
        for (px, py) in pts[1:-1]:
            w.update(_perp_dist_to_line(ax, ay, bx, by, px, py))
    tremor_std_dev = w.stddev()

    return TrajectoryFeatures(
        total_dist=total_dist,
        linear_dist=linear_dist,
        linearity_ratio=linearity_ratio,
        avg_velocity=avg_velocity,
        tremor_std_dev=tremor_std_dev,
        dwell_time_ms=float(dwell_time_ms),
    )


class FeatureBank:
    """Empirical sampler from collected telemetry (R&D raw capture log)."""

    def __init__(self, targets: list[TrajectoryTarget]) -> None:
        self._targets = targets

    @staticmethod
    def default() -> "FeatureBank":
        # Conservative "balanced" defaults (in case no dataset exists yet).
        return FeatureBank(
            [
                TrajectoryTarget(
                    velocity_profile="ease-in-out",
                    linearity_ratio=0.88,
                    tremor_std_dev=2.0,
                    avg_velocity=1.1,
                    dwell_time_ms=220.0,
                )
            ]
        )

    @staticmethod
    def _parse_target_from_obj(obj: dict[str, Any]) -> TrajectoryTarget | None:
        feat = obj.get("features") or {}
        try:
            linearity = float(feat.get("linearityRatio"))
            tremor = float(feat.get("tremorStdDev"))
            vel = float(feat.get("avgVelocity"))
            dwell = float(feat.get("dwellTime"))
        except Exception:
            return None

        # Clamp to sane numerical bounds to avoid poisoning the sampler.
        return TrajectoryTarget(
            velocity_profile="ease-in-out",
            linearity_ratio=_clamp(linearity, 0.55, 1.0),
            tremor_std_dev=_clamp(tremor, 0.0, 25.0),
            avg_velocity=_clamp(vel, 0.05, 6.0),
            dwell_time_ms=_clamp(dwell, 0.0, 10_000.0),
        )

    @classmethod
    def from_jsonl(cls, path: Path, *, dataset_id: str | None = None, max_lines: int = 50_000) -> "FeatureBank":
        if not path.exists() or not path.is_file():
            return cls.default()

        targets: list[TrajectoryTarget] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if dataset_id is not None and dataset_id != "":
                        if (obj.get("datasetId") or obj.get("dataset_id") or "") != dataset_id:
                            continue
                    t = cls._parse_target_from_obj(obj)
                    if t is not None:
                        targets.append(t)
        except Exception:
            return cls.default()

        if not targets:
            return cls.default()
        return cls(targets)

    def sample(self, rng) -> TrajectoryTarget:
        if not self._targets:
            return self.default().sample(rng)

        base = rng.choice(self._targets)

        # Add tiny jitter but keep within bounds.
        lin = _clamp(base.linearity_ratio + rng.gauss(0.0, 0.015), 0.55, 1.0)
        trem = _clamp(base.tremor_std_dev + rng.gauss(0.0, 0.35), 0.0, 25.0)
        vel = _clamp(base.avg_velocity + rng.gauss(0.0, 0.12), 0.05, 6.0)
        dwell = _clamp(base.dwell_time_ms + rng.gauss(0.0, 60.0), 0.0, 10_000.0)

        max_dwell = int(os.getenv("TM_TRAJ_DWELL_MAX_MS", "650") or "650")
        dwell = _clamp(dwell, 25.0, float(max(25, max_dwell)))

        return TrajectoryTarget(
            velocity_profile=base.velocity_profile,
            linearity_ratio=lin,
            tremor_std_dev=trem,
            avg_velocity=vel,
            dwell_time_ms=dwell,
        )


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _cubic_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    u: float,
) -> tuple[float, float]:
    # De Casteljau (stable)
    (x0, y0) = p0
    (x1, y1) = p1
    (x2, y2) = p2
    (x3, y3) = p3

    a0x = x0 + (x1 - x0) * u
    a0y = y0 + (y1 - y0) * u
    a1x = x1 + (x2 - x1) * u
    a1y = y1 + (y2 - y1) * u
    a2x = x2 + (x3 - x2) * u
    a2y = y2 + (y3 - y2) * u

    b0x = a0x + (a1x - a0x) * u
    b0y = a0y + (a1y - a0y) * u
    b1x = a1x + (a2x - a1x) * u
    b1y = a1y + (a2y - a1y) * u

    cx = b0x + (b1x - b0x) * u
    cy = b0y + (b1y - b0y) * u
    return (cx, cy)


class TrajectorySynthesizer:
    """Bezier + Gaussian noise trajectory generator (M-Prim)."""

    def __init__(self, rng, *, dataset_path: Path | None = None, dataset_id: str | None = None) -> None:
        self._rng = rng
        if dataset_path is None:
            dataset_path = Path(os.getenv("TM_TRAJ_RAW_LOG_PATH", "platform/backend/logs/trajectory_raw.jsonl"))
        if dataset_id is None:
            dataset_id = os.getenv("TM_TRAJ_DATASET_ID", "").strip() or None
        self._bank = FeatureBank.from_jsonl(dataset_path, dataset_id=dataset_id)

    def synthesize(self, start: tuple[float, float], end: tuple[float, float]) -> SynthesisResult:
        (sx, sy) = start
        (ex, ey) = end
        dx = ex - sx
        dy = ey - sy
        dist = math.hypot(dx, dy)

        # Degenerate / tiny movements: keep it simple.
        if dist < 2.0:
            target = self._bank.sample(self._rng)
            dt_ms = 10
            points = [(sx, sy), (ex, ey)]
            computed = compute_features(points, dt_ms=dt_ms, dwell_time_ms=target.dwell_time_ms)
            return SynthesisResult(points=points, dt_ms=dt_ms, target=target, computed=computed)

        target = self._bank.sample(self._rng)

        # Build a smooth curve skeleton (cubic bezier).
        ux = dx / dist
        uy = dy / dist
        ox = -uy
        oy = ux

        # Curvature heuristic based on target linearity.
        # Higher linearity -> smaller orthogonal offset.
        inv = max(0.0, (1.0 / max(0.56, target.linearity_ratio)) - 1.0)
        amp = dist * math.sqrt(inv) * 0.45
        amp = _clamp(amp, 0.0, min(220.0, dist * 0.65))
        sign = -1.0 if self._rng.random() < 0.5 else 1.0

        # Two control points with slightly different offsets.
        amp1 = sign * amp * (0.95 + self._rng.uniform(-0.15, 0.15))
        amp2 = sign * amp * (0.70 + self._rng.uniform(-0.15, 0.15))
        along1 = self._rng.uniform(-18.0, 18.0)
        along2 = self._rng.uniform(-18.0, 18.0)

        p0 = (sx, sy)
        p3 = (ex, ey)
        p1 = (sx + dx * 0.30 + ox * amp1 + ux * along1, sy + dy * 0.30 + oy * amp1 + uy * along1)
        p2 = (sx + dx * 0.70 + ox * amp2 + ux * along2, sy + dy * 0.70 + oy * amp2 + uy * along2)

        # Choose steps from (estimated) duration.
        # totalDist ~= linearDist / linearity_ratio
        est_total = dist / max(0.56, target.linearity_ratio)
        est_duration_ms = est_total / max(0.05, target.avg_velocity)
        est_duration_ms = _clamp(est_duration_ms, 140.0, 900.0)
        dt_ms = 10
        steps = int(_clamp(est_duration_ms / dt_ms, 14.0, 110.0))
        if steps < 2:
            steps = 2

        points: list[tuple[float, float]] = []
        points.append(p0)

        # Tremor: noise perpendicular to straight line (matches FE tremor intuition).
        trem = target.tremor_std_dev
        for i in range(1, steps):
            t = i / steps
            u = _smoothstep(t) if target.velocity_profile == "ease-in-out" else t
            (bx, by) = _cubic_bezier(p0, p1, p2, p3, u)
            n = self._rng.gauss(0.0, trem)
            px = bx + ox * n
            py = by + oy * n
            points.append((px, py))

        points.append(p3)

        computed = compute_features(points, dt_ms=dt_ms, dwell_time_ms=target.dwell_time_ms)
        return SynthesisResult(points=points, dt_ms=dt_ms, target=target, computed=computed)

