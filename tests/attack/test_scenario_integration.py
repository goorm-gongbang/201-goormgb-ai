"""Integration tests for Scenario Harness - Loader, Runner, Assertion, Report."""

from pathlib import Path
import pytest
from traffic_master_ai.attack.a0_poc import (
    ScenarioLoader,
    ScenarioRunner,
    ScenarioReport,
    StateStore,
    PolicySnapshot,
)


def test_scenario_full_pipe(tmp_path: Path) -> None:
    """Loader -> Runner -> Assertion -> Report 전체 흐름 통합 테스트."""
    
    # 1. 테스트용 시나리오 파일 생성
    scn_dir = tmp_path / "scenarios"
    scn_dir.mkdir()
    scn_file = scn_dir / "SCN-01.json"
    scn_file.write_text("""
    {
        "id": "SCN-01",
        "name": "Integration Pass Test",
        "initial_state": "S0",
        "policy_profile": "default",
        "events": [
            { "event_type": "FLOW_START", "delay_ms": 100 },
            { "event_type": "ENTRY_ENABLED", "delay_ms": 100 },
            { "event_type": "QUEUE_PASSED", "delay_ms": 100 },
            { "event_type": "SECTION_SELECTED", "delay_ms": 100 },
            { "event_type": "SEAT_SELECTED", "delay_ms": 100 },
            { "event_type": "PAYMENT_COMPLETED", "delay_ms": 100 }
        ],
        "accept": {
            "final_state": "SX",
            "terminal_reason": "done",
            "asserts": [
                { "type": "state_path_contains", "value": "S1" },
                { "type": "event_handled_count_at_least", "value": 3 }
            ]
        }
    }
    """)

    # 2. 로딩
    loader = ScenarioLoader(scn_dir)
    scenarios = loader.load_all()
    assert len(scenarios) == 1
    scn = scenarios[0]

    # 3. 브레인 컴포넌트 준비
    runner = ScenarioRunner()
    store = StateStore()
    policy = PolicySnapshot(profile_name="integration-test", rules={})
    report = ScenarioReport()

    # 4. 실행 및 결과 집계
    result = runner.run(scn, store, policy)
    report.add_result(result)

    # 5. 검증
    assert result.is_success is True
    assert result.total_elapsed_ms == 600
    assert len(result.assertion_results) == 3 # terminal_reason + 2 custom assertions
    
    # 리포트 출력 확인 (콘솔 출력용)
    report.print_summary()
