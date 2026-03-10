from __future__ import annotations

import random
from pathlib import Path

from traffic_master_ai.attack.a1_mvp.trajectory.synthesizer import (
    FeatureBank,
    TrajectoryTarget,
    TrajectorySynthesizer,
    compute_features,
)


def test_compute_features_straight_line() -> None:
    pts = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
    feat = compute_features(pts, dt_ms=10, dwell_time_ms=100.0)
    assert feat.total_dist == 100.0
    assert feat.linear_dist == 100.0
    assert feat.linearity_ratio == 1.0
    assert feat.tremor_std_dev == 0.0


def test_feature_bank_from_jsonl_dataset_filter(tmp_path: Path) -> None:
    p = tmp_path / "traj.jsonl"
    p.write_text(
        "\n".join(
            [
                '{"datasetId":"A","features":{"linearityRatio":0.91,"tremorStdDev":1.2,"avgVelocity":1.0,"dwellTime":120}}',
                '{"datasetId":"B","features":{"linearityRatio":0.62,"tremorStdDev":6.0,"avgVelocity":0.4,"dwellTime":900}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    bank = FeatureBank.from_jsonl(p, dataset_id="A")
    rng = random.Random(7)
    t = bank.sample(rng)
    assert isinstance(t, TrajectoryTarget)
    assert 0.80 <= t.linearity_ratio <= 1.0


def test_synthesizer_generates_non_degenerate_path(tmp_path: Path, monkeypatch) -> None:
    # Ensure it doesn't accidentally pick up any local developer dataset.
    monkeypatch.delenv("TM_TRAJ_RAW_LOG_PATH", raising=False)
    monkeypatch.delenv("TM_TRAJ_DATASET_ID", raising=False)

    rng = random.Random(123)
    synth = TrajectorySynthesizer(rng, dataset_path=tmp_path / "missing.jsonl")

    res = synth.synthesize((10.0, 10.0), (210.0, 110.0))
    assert res.dt_ms == 10
    assert len(res.points) >= 10
    assert res.points[0] == (10.0, 10.0)
    assert res.points[-1] == (210.0, 110.0)
    assert 0.55 <= res.computed.linearity_ratio <= 1.0
    assert res.computed.tremor_std_dev >= 0.0

