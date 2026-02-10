"""Integration tests for A0-3 Failure Handling.

Orchestrator, FailureMatrix, and ROILogger integration check.
"""

from pathlib import Path

import pytest

from traffic_master_ai.attack.a0_poc import (
    EventType,
    FailureMatrix,
    PolicySnapshot,
    ROILogger,
    SemanticEvent,
    State,
    StateStore,
    TerminalReason,
)
from traffic_master_ai.attack.a0_poc.orchestrator import run_events


class TestFailureHandlingIntegration:
    """실패 처리 매트릭스 및 ROI 로거 통합 테스트."""

    @pytest.fixture
    def store(self) -> StateStore:
        # 초기 예산 설정
        budgets = {
            "N_seat": 2,
            "N_challenge": 1,
            "N_hold": 1,
            "security": 1,  # 기존 transition.py에서 참조하는 키
            "retry": 5,     # 기존 transition.py에서 참조하는 키
        }
        return StateStore(initial_state=State.S0, budgets=budgets)

    @pytest.fixture
    def policy(self) -> PolicySnapshot:
        return PolicySnapshot(profile_name="default", rules={})

    @pytest.fixture
    def failure_matrix(self) -> FailureMatrix:
        return FailureMatrix()

    @pytest.fixture
    def roi_logger(self, tmp_path: Path) -> ROILogger:
        return ROILogger(tmp_path / "evidence.jsonl")

    def test_seat_taken_flow_with_matrix(
        self, store: StateStore, policy: PolicySnapshot, failure_matrix: FailureMatrix, roi_logger: ROILogger
    ) -> None:
        """이선좌(SEAT_TAKEN) 발생 시 Matrix 규칙에 따라 예산 차감 및 전이 확인."""
        events = [
            SemanticEvent(type=EventType.FLOW_START),
            SemanticEvent(type=EventType.ENTRY_ENABLED),
            SemanticEvent(type=EventType.QUEUE_PASSED),
            SemanticEvent(type=EventType.SECTION_SELECTED),
            # S5 진입 후 이선좌 발생
            SemanticEvent(type=EventType.SEAT_TAKEN),
            # 다시 성공
            SemanticEvent(type=EventType.SEAT_SELECTED),
            SemanticEvent(type=EventType.PAYMENT_COMPLETED),
        ]

        # Orchestrator 실행 (새로운 인자 matrix, roi_logger 추가 예정)
        result = run_events(
            events=events,
            store=store,
            policy=policy,
            failure_matrix=failure_matrix,
            roi_logger=roi_logger,
        )

        assert result.terminal_state == State.SX
        # N_seat 예산이 2 -> 1로 차감되었는지 확인 (Matrix 규칙: retry_budget_key="N_seat")
        assert result.final_budgets["N_seat"] == 1
        # ROI 요약에 attempts가 기록되었는지 확인
        summary = roi_logger.get_roi_summary()
        assert summary["total_attempts"] >= 1
        assert summary["detailed_counters"]["seatTakenCount"] == 1

    def test_seat_taken_exhaustion_rollback_to_s4(
        self, store: StateStore, policy: PolicySnapshot, failure_matrix: FailureMatrix, roi_logger: ROILogger
    ) -> None:
        """이선좌 예산 소진 시 S4로 롤백되는지 확인 (Spec SCN-09 유사)."""
        # N_seat를 1로 설정
        store.set_budget("N_seat", 1)
        
        events = [
            SemanticEvent(type=EventType.FLOW_START),
            SemanticEvent(type=EventType.ENTRY_ENABLED),
            SemanticEvent(type=EventType.QUEUE_PASSED),
            SemanticEvent(type=EventType.SECTION_SELECTED),
            # S5 진입
            SemanticEvent(type=EventType.SEAT_TAKEN), # 1 -> 0 (S5 유지)
            SemanticEvent(type=EventType.SEAT_TAKEN), # 0 (소진) -> S4 롤백
            # S4에서 다시 구역 선택 시도 (이벤트 리스트 소진 방지를 위해 SX까지 진행)
            SemanticEvent(type=EventType.SECTION_SELECTED),
            SemanticEvent(type=EventType.SEAT_SELECTED),
            SemanticEvent(type=EventType.PAYMENT_COMPLETED),
        ]

        result = run_events(events, store, policy, failure_matrix, roi_logger)
        
        assert "S4" in [s.value for s in result.state_path]
        assert result.final_budgets["N_seat"] == 0
        assert roi_logger.get_roi_summary()["detailed_counters"]["rollbackCount"] >= 1

    def test_challenge_fail_exhaustion_abort(
        self, store: StateStore, policy: PolicySnapshot, failure_matrix: FailureMatrix, roi_logger: ROILogger
    ) -> None:
        """챌린지 예산 소진 시 SX(ABORT)로 전이되는지 확인 (Spec SCN-06)."""
        store.set_budget("N_challenge", 1)
        
        events = [
            SemanticEvent(type=EventType.FLOW_START),
            SemanticEvent(type=EventType.ENTRY_ENABLED),
            SemanticEvent(type=EventType.QUEUE_PASSED),
            # S4에서 인터럽트 발생 시뮬레이션
            SemanticEvent(type=EventType.DEF_CHALLENGE_FORCED),
            SemanticEvent(type=EventType.CHALLENGE_FAILED), # 1 -> 0 (S3 유지)
            SemanticEvent(type=EventType.CHALLENGE_FAILED), # 0 -> SX(Abort)
        ]

        result = run_events(events, store, policy, failure_matrix, roi_logger)
        
        # 검증: 예산 소진으로 인한 Abort 확인
        assert result.terminal_state == State.SX
        assert result.terminal_reason == TerminalReason.ABORT
        assert result.failure_code == "F_CHALLENGE_FAILED"
        # TerminalReason이 Matrix나 stop_condition에 따라 설정되어야 함
        # SCN-06 등은 cooldown이나 abort를 요구함.
        summary = roi_logger.get_roi_summary()
        assert summary["detailed_counters"]["challengeFailCount"] == 2
