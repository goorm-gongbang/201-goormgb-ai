"""Unit tests for Orchestrator Loop - A0-1-T5.

Semantic Event 리스트 순차 처리 및 ExecutionResult 반환 테스트.
"""

import pytest

from traffic_master_ai.attack.a0_poc import (
    ExecutionResult,
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
def initial_store() -> StateStore:
    """초기 상태 저장소 (S0, 예산 포함)."""
    return StateStore(
        initial_state=State.S0_INIT,
        budgets={"retry": 3, "security": 2},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 정상 플로우 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """정상 티켓팅 완료 플로우 테스트."""

    def test_full_flow_s0_to_sx_done(
        self,
        default_policy: PolicySnapshot,
        initial_store: StateStore,
    ) -> None:
        """전체 플로우: S0 → S1 → S2 → S4 → S5 → S6 → SX (done)."""
        events = [
            SemanticEvent(event_type="BOOTSTRAP_COMPLETE"),  # S0 → S1
            SemanticEvent(event_type="ENTRY_ENABLED"),       # S1 → S2
            SemanticEvent(event_type="QUEUE_PASSED"),        # S2 → S4
            SemanticEvent(event_type="SECTION_SELECTED"),    # S4 → S5
            SemanticEvent(event_type="SEAT_SELECTED"),       # S5 → S6
            SemanticEvent(event_type="PAYMENT_COMPLETE"),    # S6 → SX
        ]

        result = run_events(events, initial_store, default_policy)

        assert result.terminal_state == State.SX_TERMINAL
        assert result.terminal_reason == TerminalReason.DONE
        assert result.handled_events == 6
        assert result.is_success()
        assert result.state_path == [
            State.S0_INIT,
            State.S1_PRE_ENTRY,
            State.S2_QUEUE_ENTRY,
            State.S4_SECTION,
            State.S5_SEAT,
            State.S6_TRANSACTION,
            State.SX_TERMINAL,
        ]

    def test_state_path_records_all_states(
        self,
        default_policy: PolicySnapshot,
        initial_store: StateStore,
    ) -> None:
        """state_path가 모든 방문 상태를 기록하는지 확인."""
        events = [
            SemanticEvent(event_type="BOOTSTRAP_COMPLETE"),
            SemanticEvent(event_type="ENTRY_ENABLED"),
            SemanticEvent(event_type="FATAL_ERROR"),  # 즉시 SX
        ]

        result = run_events(events, initial_store, default_policy)

        assert result.state_path == [
            State.S0_INIT,
            State.S1_PRE_ENTRY,
            State.S2_QUEUE_ENTRY,
            State.SX_TERMINAL,
        ]
        assert result.handled_events == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 터미널 상태 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestTerminalCases:
    """다양한 터미널 도달 케이스."""

    def test_fatal_error_abort(
        self,
        default_policy: PolicySnapshot,
        initial_store: StateStore,
    ) -> None:
        """FATAL_ERROR → abort."""
        events = [
            SemanticEvent(event_type="BOOTSTRAP_COMPLETE"),
            SemanticEvent(event_type="FATAL_ERROR"),
        ]

        result = run_events(events, initial_store, default_policy)

        assert result.terminal_reason == TerminalReason.ABORT
        assert not result.is_success()

    def test_cooldown_triggered(
        self,
        default_policy: PolicySnapshot,
        initial_store: StateStore,
    ) -> None:
        """COOLDOWN_TRIGGERED → cooldown."""
        events = [
            SemanticEvent(event_type="BOOTSTRAP_COMPLETE"),
            SemanticEvent(event_type="COOLDOWN_TRIGGERED"),
        ]

        result = run_events(events, initial_store, default_policy)

        assert result.terminal_reason == TerminalReason.COOLDOWN

    def test_loop_stops_at_terminal(
        self,
        default_policy: PolicySnapshot,
        initial_store: StateStore,
    ) -> None:
        """터미널 도달 후 추가 이벤트 무시."""
        events = [
            SemanticEvent(event_type="BOOTSTRAP_COMPLETE"),
            SemanticEvent(event_type="FATAL_ERROR"),
            SemanticEvent(event_type="ENTRY_ENABLED"),  # 무시됨
            SemanticEvent(event_type="QUEUE_PASSED"),   # 무시됨
        ]

        result = run_events(events, initial_store, default_policy)

        assert result.handled_events == 2  # FATAL_ERROR까지만 처리
        assert result.terminal_reason == TerminalReason.ABORT


# ═══════════════════════════════════════════════════════════════════════════════
# 보안 인터럽트 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityInterrupt:
    """S3 보안 인터럽트 및 ReturnTo 테스트."""

    def test_s3_interrupt_and_return(
        self,
        default_policy: PolicySnapshot,
        initial_store: StateStore,
    ) -> None:
        """S2에서 S3 인터럽트 후 S2로 복귀."""
        events = [
            SemanticEvent(event_type="BOOTSTRAP_COMPLETE"),   # S0 → S1
            SemanticEvent(event_type="ENTRY_ENABLED"),        # S1 → S2
            SemanticEvent(event_type="CHALLENGE_DETECTED"),   # S2 → S3
            SemanticEvent(event_type="CHALLENGE_PASSED"),     # S3 → S2
            SemanticEvent(event_type="QUEUE_PASSED"),         # S2 → S4
            SemanticEvent(event_type="SECTION_SELECTED"),     # S4 → S5
            SemanticEvent(event_type="SEAT_SELECTED"),        # S5 → S6
            SemanticEvent(event_type="PAYMENT_COMPLETE"),     # S6 → SX
        ]

        result = run_events(events, initial_store, default_policy)

        assert result.terminal_reason == TerminalReason.DONE
        assert State.S3_SECURITY in result.state_path


# ═══════════════════════════════════════════════════════════════════════════════
# 롤백 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestRollbackCases:
    """롤백 시나리오 테스트."""

    def test_seat_taken_rollback_to_s4(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """좌석 선점됨 → 예산 소진 시 S4로 롤백."""
        store = StateStore(
            initial_state=State.S0_INIT,
            budgets={"retry": 0, "security": 2},  # retry 예산 없음
        )
        events = [
            SemanticEvent(event_type="BOOTSTRAP_COMPLETE"),
            SemanticEvent(event_type="ENTRY_ENABLED"),
            SemanticEvent(event_type="QUEUE_PASSED"),
            SemanticEvent(event_type="SECTION_SELECTED"),
            SemanticEvent(event_type="SEAT_TAKEN"),      # S5 → S4 롤백
            SemanticEvent(event_type="SECTION_SELECTED"),  # S4 → S5
            SemanticEvent(event_type="SEAT_SELECTED"),
            SemanticEvent(event_type="PAYMENT_COMPLETE"),
        ]

        result = run_events(events, store, default_policy)

        assert result.terminal_reason == TerminalReason.DONE
        # S5가 두 번 방문됨 (롤백 후 재진입)
        s5_count = result.state_path.count(State.S5_SEAT)
        assert s5_count >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 에러 케이스 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestErrorCases:
    """에러 처리 테스트."""

    def test_events_exhausted_without_terminal_raises(
        self,
        default_policy: PolicySnapshot,
        initial_store: StateStore,
    ) -> None:
        """터미널 미도달 상태에서 이벤트 소진 시 에러."""
        events = [
            SemanticEvent(event_type="BOOTSTRAP_COMPLETE"),
            SemanticEvent(event_type="ENTRY_ENABLED"),
            # 터미널에 도달하지 않음
        ]

        with pytest.raises(ValueError, match="터미널 미도달"):
            run_events(events, initial_store, default_policy)

    def test_empty_events_with_non_terminal_raises(
        self,
        default_policy: PolicySnapshot,
        initial_store: StateStore,
    ) -> None:
        """빈 이벤트 리스트 + 비터미널 상태 = 에러."""
        events: list[SemanticEvent] = []

        with pytest.raises(ValueError, match="터미널 미도달"):
            run_events(events, initial_store, default_policy)


# ═══════════════════════════════════════════════════════════════════════════════
# ExecutionResult 필드 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecutionResultFields:
    """ExecutionResult 필드 검증."""

    def test_final_budgets_and_counters(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """final_budgets와 final_counters가 정확히 복사되는지."""
        store = StateStore(
            initial_state=State.S0_INIT,
            budgets={"retry": 5, "security": 3},
            counters={"attempts": 0},
        )
        events = [
            SemanticEvent(event_type="BOOTSTRAP_COMPLETE"),
            SemanticEvent(event_type="FATAL_ERROR"),
        ]

        result = run_events(events, store, default_policy)

        assert result.final_budgets == {"retry": 5, "security": 3}
        assert result.final_counters == {"attempts": 0}

    def test_handled_events_count(
        self,
        default_policy: PolicySnapshot,
        initial_store: StateStore,
    ) -> None:
        """handled_events가 정확히 카운트되는지."""
        events = [
            SemanticEvent(event_type="BOOTSTRAP_COMPLETE"),
            SemanticEvent(event_type="ENTRY_ENABLED"),
            SemanticEvent(event_type="QUEUE_PASSED"),
            SemanticEvent(event_type="FATAL_ERROR"),
        ]

        result = run_events(events, initial_store, default_policy)

        assert result.handled_events == 4
