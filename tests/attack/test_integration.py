"""Integration Tests for A0-1-T7.

핵심 통합 테스트: ReturnTo / Rollback / Terminal 시나리오 검증.
Transition Function + Orchestrator 조합의 안정성을 검증한다.

IN SCOPE:
- SCN-03: Queue 직후 Security Challenge
- SCN-04: S5에서 Security Challenge
- SCN-09: Seat Taken 반복 → S4 롤백
- SCN-13: Transaction Rollback → S5 롤백
- Terminal 전이 검증 (done, abort, cooldown, reset)
"""

import pytest

from traffic_master_ai.attack.a0_poc import (
    PolicySnapshot,
    SemanticEvent,
    State,
    StateStore,
    TerminalReason,
    run_events,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 테스트 픽스처
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def default_policy() -> PolicySnapshot:
    """기본 정책 스냅샷."""
    return PolicySnapshot(profile_name="default", rules={})


@pytest.fixture
def default_store() -> StateStore:
    """기본 상태 저장소 (S0, 예산 포함)."""
    return StateStore(
        initial_state=State.S0,
        budgets={"retry": 3, "security": 2},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SCN-03: Forced Challenge right after Queue Pass
# S2 직후 → S3 → ReturnTo = last_non_security_state (S4 기대)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSCN03ForcedChallengeAfterQueuePass:
    """SCN-03: Queue 직후 Security Challenge 테스트."""

    def test_scn03_challenge_after_queue_pass_returns_to_s4(
        self,
        default_policy: PolicySnapshot,
        default_store: StateStore,
    ) -> None:
        """
        SCN-03: Queue 통과 직후 DEF_CHALLENGE_FORCED 발생.

        Accept:
        - DEF_CHALLENGE_FORCED 수신 즉시 S3 진입
        - CHALLENGE_PASSED 후 ReturnTo=S4로 복귀
        - 최종 SX(done)
        """
        events = [
            SemanticEvent(type="FLOW_START"),
            SemanticEvent(type="ENTRY_ENABLED"),
            SemanticEvent(type="QUEUE_PASSED"),
            SemanticEvent(type="DEF_CHALLENGE_FORCED"),  # S4 → S3
            SemanticEvent(type="CHALLENGE_PASSED"),       # S3 → S4
            SemanticEvent(type="SECTION_SELECTED"),
            SemanticEvent(type="SEAT_SELECTED"),
            SemanticEvent(type="HOLD_ACQUIRED"),
            SemanticEvent(type="PAYMENT_COMPLETED"),
        ]

        result = run_events(events, default_store, default_policy)

        # Accept 조건 검증
        assert result.terminal_state == State.SX
        assert result.terminal_reason == TerminalReason.DONE
        assert State.S3 in result.state_path
        # S3 진입 후 S4로 복귀 확인
        s3_index = result.state_path.index(State.S3)
        assert result.state_path[s3_index + 1] == State.S4


# ═══════════════════════════════════════════════════════════════════════════════
# SCN-04: Forced Challenge during Seat Selection
# S5 → S3 → ReturnTo = S5
# ═══════════════════════════════════════════════════════════════════════════════


class TestSCN04ForcedChallengeDuringSeatSelection:
    """SCN-04: S5에서 Security Challenge 테스트."""

    def test_scn04_challenge_during_seat_selection_returns_to_s5(
        self,
        default_policy: PolicySnapshot,
        default_store: StateStore,
    ) -> None:
        """
        SCN-04: 좌석 선택 중 DEF_CHALLENGE_FORCED 발생.

        Accept:
        - 인터럽트 직전 last_non_security_state=S5
        - CHALLENGE_PASSED 후 S5로 복귀
        - 최종 SX(done)
        """
        events = [
            SemanticEvent(type="FLOW_START"),
            SemanticEvent(type="ENTRY_ENABLED"),
            SemanticEvent(type="QUEUE_PASSED"),
            SemanticEvent(type="SECTION_SELECTED"),
            SemanticEvent(type="DEF_CHALLENGE_FORCED"),  # S5 → S3
            SemanticEvent(type="CHALLENGE_PASSED"),       # S3 → S5
            SemanticEvent(type="SEAT_SELECTED"),
            SemanticEvent(type="HOLD_ACQUIRED"),
            SemanticEvent(type="PAYMENT_COMPLETED"),
        ]

        result = run_events(events, default_store, default_policy)

        # Accept 조건 검증
        assert result.terminal_state == State.SX
        assert result.terminal_reason == TerminalReason.DONE
        assert State.S3 in result.state_path
        # S3 진입 후 S5로 복귀 확인
        s3_index = result.state_path.index(State.S3)
        assert result.state_path[s3_index + 1] == State.S5


# ═══════════════════════════════════════════════════════════════════════════════
# SCN-09: Seat Taken N times → Rollback to S4
# ═══════════════════════════════════════════════════════════════════════════════


class TestSCN09SeatTakenRollback:
    """SCN-09: 좌석 선점 반복 시 S4 롤백 테스트."""

    def test_scn09_seat_taken_budget_exhausted_rollback_to_s4(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """
        SCN-09: SEAT_TAKEN 반복으로 retry budget 소진 시 S4로 롤백.

        Accept:
        - seat_taken_threshold 또는 N_seat 소진 시 S4로 롤백
        - seatTakenCount 누적 기록
        """
        # retry budget 0으로 시작 → 첫 SEAT_TAKEN에서 즉시 롤백
        store = StateStore(
            initial_state=State.S0,
            budgets={"retry": 0, "security": 2},
        )
        events = [
            SemanticEvent(type="FLOW_START"),
            SemanticEvent(type="ENTRY_ENABLED"),
            SemanticEvent(type="QUEUE_PASSED"),
            SemanticEvent(type="SECTION_SELECTED"),
            SemanticEvent(type="SEAT_TAKEN"),  # S5 → S4 롤백
            # S4에서 다시 진행
            SemanticEvent(type="SECTION_SELECTED"),
            SemanticEvent(type="SEAT_SELECTED"),
            SemanticEvent(type="HOLD_ACQUIRED"),
            SemanticEvent(type="PAYMENT_COMPLETED"),
        ]

        result = run_events(events, store, default_policy)

        # Accept 조건 검증
        assert result.terminal_state == State.SX
        assert result.terminal_reason == TerminalReason.DONE
        # S5 → S4 롤백 경로 확인
        assert State.S5 in result.state_path
        assert State.S4 in result.state_path
        # 롤백 발생 확인: S5 이후 S4가 다시 등장
        s5_first_index = result.state_path.index(State.S5)
        s4_after_s5 = [
            i for i, s in enumerate(result.state_path)
            if s == State.S4 and i > s5_first_index
        ]
        assert len(s4_after_s5) > 0, "SEAT_TAKEN 후 S4 롤백이 발생해야 함"


# ═══════════════════════════════════════════════════════════════════════════════
# SCN-13: Transaction Rollback Required → Back to S5
# ═══════════════════════════════════════════════════════════════════════════════


class TestSCN13TransactionRollback:
    """SCN-13: 트랜잭션 롤백 테스트."""

    def test_scn13_txn_rollback_returns_to_s5_then_completes(
        self,
        default_policy: PolicySnapshot,
        default_store: StateStore,
    ) -> None:
        """
        SCN-13: TXN_ROLLBACK_REQUIRED 발생 시 S5로 롤백 후 정상 완료.

        Accept:
        - TXN_ROLLBACK_REQUIRED 발생 시 S5로 롤백
        - rollbackCount 기록
        - 최종 SX(done)
        """
        events = [
            SemanticEvent(type="FLOW_START"),
            SemanticEvent(type="ENTRY_ENABLED"),
            SemanticEvent(type="QUEUE_PASSED"),
            SemanticEvent(type="SECTION_SELECTED"),
            SemanticEvent(type="SEAT_SELECTED"),
            SemanticEvent(type="HOLD_ACQUIRED"),
            SemanticEvent(type="TXN_ROLLBACK_REQUIRED"),  # S6 → S5
            # S5에서 다시 진행
            SemanticEvent(type="SEAT_SELECTED"),
            SemanticEvent(type="HOLD_ACQUIRED"),
            SemanticEvent(type="PAYMENT_COMPLETED"),
        ]

        result = run_events(events, default_store, default_policy)

        # Accept 조건 검증
        assert result.terminal_state == State.SX
        assert result.terminal_reason == TerminalReason.DONE
        # S6 → S5 롤백 경로 확인 (state_path에 S6, S5, S6 순서 포함)
        path_str = "".join([s.value for s in result.state_path])
        assert "S6S5S6" in path_str, "S6 → S5 → S6 롤백 경로가 있어야 함"


# ═══════════════════════════════════════════════════════════════════════════════
# Terminal 전이 검증: done, abort, cooldown, reset
# ═══════════════════════════════════════════════════════════════════════════════


class TestTerminalReasons:
    """terminal_reason 분기 검증."""

    def test_terminal_done_happy_path(
        self,
        default_policy: PolicySnapshot,
        default_store: StateStore,
    ) -> None:
        """terminal_reason = done: 정상 완료."""
        events = [
            SemanticEvent(type="FLOW_START"),
            SemanticEvent(type="ENTRY_ENABLED"),
            SemanticEvent(type="QUEUE_PASSED"),
            SemanticEvent(type="SECTION_SELECTED"),
            SemanticEvent(type="SEAT_SELECTED"),
            SemanticEvent(type="HOLD_ACQUIRED"),
            SemanticEvent(type="PAYMENT_COMPLETED"),
        ]

        result = run_events(events, default_store, default_policy)

        assert result.terminal_reason == TerminalReason.DONE
        assert result.is_success()

    def test_terminal_abort_fatal_error(
        self,
        default_policy: PolicySnapshot,
        default_store: StateStore,
    ) -> None:
        """terminal_reason = abort: FATAL_ERROR 발생."""
        events = [
            SemanticEvent(type="FLOW_START"),
            SemanticEvent(type="ENTRY_ENABLED"),
            SemanticEvent(type="FATAL_ERROR", failure_code="NETWORK_FAILURE"),
        ]

        result = run_events(events, default_store, default_policy)

        assert result.terminal_reason == TerminalReason.ABORT
        assert not result.is_success()

    def test_terminal_cooldown_triggered(
        self,
        default_policy: PolicySnapshot,
        default_store: StateStore,
    ) -> None:
        """terminal_reason = cooldown: 쿨다운 트리거."""
        events = [
            SemanticEvent(type="FLOW_START"),
            SemanticEvent(type="ENTRY_ENABLED"),
            SemanticEvent(type="COOLDOWN_TRIGGERED"),
        ]

        result = run_events(events, default_store, default_policy)

        assert result.terminal_reason == TerminalReason.COOLDOWN
        assert not result.is_success()

    def test_terminal_reset_session_expired(
        self,
        default_policy: PolicySnapshot,
        default_store: StateStore,
    ) -> None:
        """terminal_reason = reset: 세션 만료."""
        events = [
            SemanticEvent(type="FLOW_START"),
            SemanticEvent(type="ENTRY_ENABLED"),
            SemanticEvent(type="QUEUE_PASSED"),
            SemanticEvent(type="SECTION_SELECTED"),
            SemanticEvent(type="SESSION_EXPIRED"),
        ]

        result = run_events(events, default_store, default_policy)

        assert result.terminal_reason == TerminalReason.RESET
        assert not result.is_success()


# ═══════════════════════════════════════════════════════════════════════════════
# 추가 통합 테스트: 상태 경로 완전성
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatePathIntegrity:
    """상태 경로 완전성 검증."""

    def test_full_happy_path_state_sequence(
        self,
        default_policy: PolicySnapshot,
        default_store: StateStore,
    ) -> None:
        """전체 Happy Path 상태 시퀀스 검증."""
        events = [
            SemanticEvent(type="FLOW_START"),
            SemanticEvent(type="ENTRY_ENABLED"),
            SemanticEvent(type="QUEUE_PASSED"),
            SemanticEvent(type="SECTION_SELECTED"),
            SemanticEvent(type="SEAT_SELECTED"),
            SemanticEvent(type="HOLD_ACQUIRED"),
            SemanticEvent(type="PAYMENT_COMPLETED"),
        ]

        result = run_events(events, default_store, default_policy)

        expected_path = [
            State.S0,
            State.S1,
            State.S2,
            State.S4,
            State.S5,
            State.S6,
            State.SX,
        ]
        assert result.state_path == expected_path

    def test_handled_events_count_matches(
        self,
        default_policy: PolicySnapshot,
        default_store: StateStore,
    ) -> None:
        """처리된 이벤트 수가 입력 이벤트 수와 일치."""
        events = [
            SemanticEvent(type="FLOW_START"),
            SemanticEvent(type="ENTRY_ENABLED"),
            SemanticEvent(type="QUEUE_PASSED"),
            SemanticEvent(type="SECTION_SELECTED"),
            SemanticEvent(type="SEAT_SELECTED"),
            SemanticEvent(type="HOLD_ACQUIRED"),
            SemanticEvent(type="PAYMENT_COMPLETED"),
        ]

        result = run_events(events, default_store, default_policy)

        assert result.handled_events == len(events)
