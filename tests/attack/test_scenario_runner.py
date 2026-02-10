"""Unit tests for ScenarioRunner."""

import pytest
from traffic_master_ai.attack.a0_poc import (
    Scenario,
    ScenarioRunner,
    StateStore,
    PolicySnapshot,
    State,
    TerminalReason,
)


class TestScenarioRunner:
    """ScenarioRunner 시뮬레이션 테스트."""

    @pytest.fixture
    def runner(self) -> ScenarioRunner:
        return ScenarioRunner()

    @pytest.fixture
    def basic_policy(self) -> PolicySnapshot:
        return PolicySnapshot(profile_name="test-policy", rules={})

    def test_run_happy_path_scn_01(self, runner: ScenarioRunner, basic_policy: PolicySnapshot) -> None:
        """SCN-01 (Normal Flow) 시나리오 실행 테스트."""
        # 1. 시나리오 객체 수동 생성 (로더 의존성 분리)
        scn = Scenario.model_validate({
            "id": "SCN-01",
            "name": "Normal Ticket Flow",
            "initial_state": "S0",
            "policy_profile": "default",
            "events": [
                { "type": "FLOW_START", "source": "ui", "delay_ms": 100 },
                { "type": "ENTRY_ENABLED", "source": "api", "stage": "S1", "delay_ms": 200 },
                { "type": "QUEUE_PASSED", "source": "ui", "stage": "S2", "delay_ms": 300 },
                { "type": "SECTION_SELECTED", "source": "ui", "stage": "S4", "delay_ms": 100 },
                { "type": "SEAT_SELECTED", "source": "ui", "stage": "S5", "delay_ms": 50 },
                { "type": "PAYMENT_COMPLETED", "source": "api", "stage": "S6", "delay_ms": 500 }
            ],
            "accept": {
                "final_state": "SX",
                "terminal_reason": "done",
                "asserts": [{"type": "state_path_equals", "value": ["S0", "S1", "S2", "S4", "S5", "S6", "SX"]}]
            }
        })

        store = StateStore() # default S0
        result = runner.run(scn, store, basic_policy)

        # 2. 결과 검증
        assert result.terminal_state == State.SX
        assert result.terminal_reason == TerminalReason.DONE
        assert result.handled_events == 6
        
        # 가상 시간 합산 검증: 100+200+300+100+50+500 = 1250ms
        assert result.total_elapsed_ms == 1250
        
        # 상태 경로 검증
        expected_path = [State.S0, State.S1, State.S2, 
                         State.S4, State.S5, State.S6, State.SX]
        assert result.state_path == expected_path

    def test_run_shorter_than_events_reaches_terminal(self, runner: ScenarioRunner, basic_policy: PolicySnapshot) -> None:
        """시나리오 이벤트가 남아있어도 터미널(Abort) 도달 시 루프 종료 확인."""
        scn = Scenario.model_validate({
            "id": "SCN-02",
            "name": "Quick Abort",
            "initial_state": "S0",
            "policy_profile": "default",
            "events": [
                { "type": "FLOW_START", "source": "ui", "delay_ms": 10 },
                { "type": "FATAL_ERROR", "source": "api", "delay_ms": 10 }, # 즉시 SX (Abort)
                { "type": "ENTRY_ENABLED", "source": "api", "delay_ms": 10 } # 처리되지 않아야 함
            ],
            "accept": {
                "final_state": "SX",
                "terminal_reason": "abort",
                "asserts": [{"type": "counter_equals", "value": 2}]
            }
        })

        store = StateStore()
        result = runner.run(scn, store, basic_policy)

        assert result.terminal_state == State.SX
        assert result.terminal_reason == TerminalReason.ABORT
        assert result.handled_events == 2 # FATAL_ERROR까지만 처리
        assert result.total_elapsed_ms == 20
