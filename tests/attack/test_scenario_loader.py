"""Unit tests for ScenarioLoader and Scenario models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from traffic_master_ai.attack.a0_poc import ScenarioLoader, State


class TestScenarioLoader:
    """ScenarioLoader 유효성 및 로딩 테스트."""

    @pytest.fixture
    def scenario_dir(self, tmp_path: Path) -> Path:
        """임시 테스트 데이터 디렉토리 생성."""
        d = tmp_path / "scenarios"
        d.mkdir()
        return d

    def test_load_valid_scenario(self, scenario_dir: Path) -> None:
        """정상적인 시나리오 JSON 로딩 성공 확인."""
        scn_path = scenario_dir / "SCN-01.json"
        data = {
            "id": "SCN-01",
            "name": "Valid Test",
            "initial_state": "S0",
            "policy_profile": "default",
            "events": [{"type": "FLOW_START", "source": "UI"}],
            "accept": {
                "final_state": "SX",
                "asserts": [{"type": "state_path_contains", "value": ["S1"]}]
            }
        }
        scn_path.write_text(json.dumps(data))

        loader = ScenarioLoader(scenario_dir)
        scenario = loader.load_one(scn_path)

        assert scenario.id == "SCN-01"
        assert scenario.initial_state == State.S0
        assert len(scenario.events) == 1
        assert scenario.accept.final_state == State.SX

    def test_load_all_filters_invalid_files(self, scenario_dir: Path) -> None:
        """load_all이 유효한 SCN-*.json 파일만 수집하는지 확인."""
        (scenario_dir / "SCN-01.json").write_text(json.dumps({
            "id": "SCN-01", "name": "Valid", "initial_state": "S0", "policy_profile": "p", 
            "events": [{"type": "FLOW_START"}], "accept": {"final_state": "SX", "asserts": [{"type": "no_invalid_events"}]}
        }))
        (scenario_dir / "OTHER.json").write_text("invalid") # 무시되어야 함
        (scenario_dir / "SCN-99.json").write_text("invalid json") # 에러 로그 남기고 건너뜀

        loader = ScenarioLoader(scenario_dir)
        scenarios = loader.load_all()

        assert len(scenarios) == 1
        assert scenarios[0].id == "SCN-01"

    def test_missing_required_field_fails(self, scenario_dir: Path) -> None:
        """필수 필드 누락 시 ValidationError 발생 확인."""
        scn_path = scenario_dir / "SCN-02.json"
        data = {"id": "SCN-02", "name": "Missing Required"} # events, accept 등 누락
        scn_path.write_text(json.dumps(data))

        loader = ScenarioLoader(scenario_dir)
        with pytest.raises(ValidationError):
            loader.load_one(scn_path)

    def test_invalid_enum_value_fails(self, scenario_dir: Path) -> None:
        """잘못된 Enum 값(State, AssertionType 등) 입력 시 검증 실패."""
        scn_path = scenario_dir / "SCN-03.json"
        data = {
            "id": "SCN-03",
            "name": "Invalid Enum",
            "initial_state": "INVALID_STATE", # Error
            "policy_profile": "default",
            "events": [{"type": "FLOW_START"}],
            "accept": {"final_state": "SX", "asserts": [{"type": "no_invalid_events"}]}
        }
        scn_path.write_text(json.dumps(data))

        loader = ScenarioLoader(scenario_dir)
        with pytest.raises(ValidationError) as excinfo:
            loader.load_one(scn_path)
        
        # 상세 에러 메시지에 원인이 포함되는지 확인 (Pydantic default message)
        assert "initial_state" in str(excinfo.value)

    def test_duplicate_id_warning(self, scenario_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
        """중복 ID 시나리오 존재 시 경고 발생 확인."""
        content = json.dumps({
            "id": "SCN-01", "name": "Dup", "initial_state": "S0", "policy_profile": "p", 
            "events": [{"type": "FLOW_START"}], "accept": {"final_state": "SX", "asserts": [{"type": "no_invalid_events"}]}
        })
        (scenario_dir / "SCN-01a.json").write_text(content)
        (scenario_dir / "SCN-01b.json").write_text(content)

        loader = ScenarioLoader(scenario_dir)
        loader.load_all()

        assert "Duplicate scenario IDs detected" in caplog.text
