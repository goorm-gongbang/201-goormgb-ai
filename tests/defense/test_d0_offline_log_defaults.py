from __future__ import annotations

import importlib

import pytest

from traffic_master_ai.defense.d0_mvp.core import constants as constants_module


def test_offline_file_defaults_use_tmp(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        monkeypatch.delenv("TM_OFFLINE_OPT_AUDIT_FILENAME", raising=False)
        monkeypatch.delenv("TM_OFFLINE_LLM_AUDIT_PATH", raising=False)
        monkeypatch.delenv("TM_OFFLINE_AUDIT_SUMMARY_FILENAME", raising=False)
        monkeypatch.delenv("TM_POLICY_STORE_FILENAME", raising=False)

        constants = importlib.reload(constants_module)

        assert constants.OFFLINE_OPT_AUDIT_FILENAME == "/tmp/logs/offline_optimization_audit.jsonl"
        assert constants.OFFLINE_AUDIT_SUMMARY_FILENAME == "/tmp/logs/offline_audit_summary.jsonl"
        assert constants.POLICY_STORE_FILENAME == "/tmp/logs/policy_store.json"
    finally:
        monkeypatch.undo()
        importlib.reload(constants_module)


def test_offline_opt_audit_filename_supports_primary_and_legacy_env_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        monkeypatch.setenv("TM_OFFLINE_LLM_AUDIT_PATH", "/tmp/legacy-audit.jsonl")
        constants = importlib.reload(constants_module)
        assert constants.OFFLINE_OPT_AUDIT_FILENAME == "/tmp/legacy-audit.jsonl"

        monkeypatch.setenv("TM_OFFLINE_OPT_AUDIT_FILENAME", "/tmp/primary-audit.jsonl")
        constants = importlib.reload(constants_module)
        assert constants.OFFLINE_OPT_AUDIT_FILENAME == "/tmp/primary-audit.jsonl"
    finally:
        monkeypatch.undo()
        importlib.reload(constants_module)
