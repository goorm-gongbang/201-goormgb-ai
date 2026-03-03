from __future__ import annotations

from pathlib import Path

from traffic_master_ai.attack.a1_mvp.config import RunConfig
from traffic_master_ai.attack.a1_mvp.main import main


def test_run_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TM_ATTACK_MODE", raising=False)
    monkeypatch.delenv("TM_FRONTEND_URL", raising=False)
    monkeypatch.delenv("TM_GAME_ID", raising=False)
    monkeypatch.delenv("TM_HEADLESS", raising=False)
    monkeypatch.delenv("TM_SLOW_MO_MS", raising=False)
    monkeypatch.delenv("TM_ATTACK_LOG_DIR", raising=False)

    cfg = RunConfig.from_env()
    assert cfg.mode == "MAP"
    assert cfg.frontend_url == "http://localhost:3000"
    assert cfg.game_id == "game-001"


def test_main_writes_audit_log(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TM_ATTACK_LOG_DIR", str(tmp_path))
    rc = main(["--mode", "MAP", "--dry-run"])
    assert rc == 0

    logs = list(tmp_path.glob("attack_mvp_*.jsonl"))
    assert len(logs) == 1
    assert logs[0].read_text(encoding="utf-8").strip()
