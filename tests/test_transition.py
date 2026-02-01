"""Unit tests for transition function - A0-1-T4.

Spec v1.0 기반 전이 함수 테스트.
최소 10개 이상의 유닛 테스트 포함:
- SCN-03/SCN-04: Security ReturnTo
- 롤백 케이스
"""

import pytest

from traffic_master_ai.attack.a0_poc import (
    PolicySnapshot,
    SemanticEvent,
    State,
    StateSnapshot,
    transition,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 테스트 픽스처
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def default_policy() -> PolicySnapshot:
    """기본 정책 스냅샷."""
    return PolicySnapshot(profile_name="default", rules={})


@pytest.fixture
def default_snapshot() -> StateSnapshot:
    """기본 상태 스냅샷."""
    return StateSnapshot(
        current_state=State.S0_INIT,
        last_non_security_state=None,
        budgets={"retry": 3, "security": 2},
        counters={},
        elapsed_ms=0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 정상 전이 테스트 (Normal Transitions)
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalTransitions:
    """정상 플로우 전이 테스트."""

    def test_s0_to_s1_bootstrap_complete(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """S0 → S1: BOOTSTRAP_COMPLETE."""
        event = SemanticEvent(event_type="BOOTSTRAP_COMPLETE")
        result = transition(State.S0_INIT, event, default_policy, default_snapshot)

        assert result.next_state == State.S1_PRE_ENTRY
        assert not result.is_terminal()

    def test_s1_to_s2_entry_enabled(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """S1 → S2: ENTRY_ENABLED."""
        event = SemanticEvent(event_type="ENTRY_ENABLED")
        result = transition(State.S1_PRE_ENTRY, event, default_policy, default_snapshot)

        assert result.next_state == State.S2_QUEUE_ENTRY

    def test_s2_to_s4_queue_passed(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """S2 → S4: QUEUE_PASSED."""
        event = SemanticEvent(event_type="QUEUE_PASSED")
        result = transition(State.S2_QUEUE_ENTRY, event, default_policy, default_snapshot)

        assert result.next_state == State.S4_SECTION

    def test_s4_to_s5_section_selected(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """S4 → S5: SECTION_SELECTED."""
        event = SemanticEvent(event_type="SECTION_SELECTED")
        result = transition(State.S4_SECTION, event, default_policy, default_snapshot)

        assert result.next_state == State.S5_SEAT

    def test_s5_to_s6_seat_selected(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """S5 → S6: SEAT_SELECTED."""
        event = SemanticEvent(event_type="SEAT_SELECTED")
        result = transition(State.S5_SEAT, event, default_policy, default_snapshot)

        assert result.next_state == State.S6_TRANSACTION

    def test_s6_to_sx_payment_complete(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """S6 → SX: PAYMENT_COMPLETE (티켓팅 성공)."""
        event = SemanticEvent(event_type="PAYMENT_COMPLETE")
        result = transition(State.S6_TRANSACTION, event, default_policy, default_snapshot)

        assert result.next_state == State.SX_TERMINAL
        assert result.terminal_reason == "done"
        assert result.is_terminal()


# ═══════════════════════════════════════════════════════════════════════════════
# 보안 인터럽트 및 복귀 테스트 (SCN-03/SCN-04)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityInterrupt:
    """S3 보안 검증 인터럽트 및 ReturnTo 테스트."""

    def test_scn03_security_interrupt_from_s2(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """SCN-03: S2에서 CHALLENGE_DETECTED → S3 인터럽트."""
        event = SemanticEvent(event_type="CHALLENGE_DETECTED")
        result = transition(State.S2_QUEUE_ENTRY, event, default_policy, default_snapshot)

        assert result.next_state == State.S3_SECURITY

    def test_scn03_security_interrupt_from_s5(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """SCN-03: S5에서 CHALLENGE_DETECTED → S3 인터럽트."""
        event = SemanticEvent(event_type="CHALLENGE_DETECTED")
        result = transition(State.S5_SEAT, event, default_policy, default_snapshot)

        assert result.next_state == State.S3_SECURITY

    def test_scn04_return_to_last_non_security_state(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """SCN-04: S3에서 CHALLENGE_PASSED → last_non_security_state로 복귀."""
        snapshot = StateSnapshot(
            current_state=State.S3_SECURITY,
            last_non_security_state=State.S5_SEAT,  # S5에서 인터럽트됨
            budgets={"security": 2},
            counters={},
            elapsed_ms=0,
        )
        event = SemanticEvent(event_type="CHALLENGE_PASSED")
        result = transition(State.S3_SECURITY, event, default_policy, snapshot)

        assert result.next_state == State.S5_SEAT

    def test_scn04_return_to_s2(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """SCN-04: S3에서 CHALLENGE_PASSED → S2로 복귀."""
        snapshot = StateSnapshot(
            current_state=State.S3_SECURITY,
            last_non_security_state=State.S2_QUEUE_ENTRY,
            budgets={"security": 2},
            counters={},
            elapsed_ms=0,
        )
        event = SemanticEvent(event_type="CHALLENGE_PASSED")
        result = transition(State.S3_SECURITY, event, default_policy, snapshot)

        assert result.next_state == State.S2_QUEUE_ENTRY

    def test_security_challenge_failed_with_budget(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """보안 챌린지 실패 - 예산 남음 → S3 유지."""
        snapshot = StateSnapshot(
            current_state=State.S3_SECURITY,
            last_non_security_state=State.S2_QUEUE_ENTRY,
            budgets={"security": 2},
            counters={},
            elapsed_ms=0,
        )
        event = SemanticEvent(event_type="CHALLENGE_FAILED")
        result = transition(State.S3_SECURITY, event, default_policy, snapshot)

        assert result.next_state == State.S3_SECURITY
        assert not result.is_terminal()

    def test_security_challenge_failed_budget_exhausted(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """보안 챌린지 실패 - 예산 소진 → abort."""
        snapshot = StateSnapshot(
            current_state=State.S3_SECURITY,
            last_non_security_state=State.S2_QUEUE_ENTRY,
            budgets={"security": 0},  # 예산 소진
            counters={},
            elapsed_ms=0,
        )
        event = SemanticEvent(event_type="CHALLENGE_FAILED")
        result = transition(State.S3_SECURITY, event, default_policy, snapshot)

        assert result.next_state == State.SX_TERMINAL
        assert result.terminal_reason == "abort"
        assert result.failure_code == "SECURITY_BUDGET_EXHAUSTED"


# ═══════════════════════════════════════════════════════════════════════════════
# 롤백 테스트 (Rollback Cases)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRollbackCases:
    """롤백 전이 테스트."""

    def test_s5_seat_taken_with_budget_stay(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """S5: SEAT_TAKEN + 예산 남음 → S5 유지."""
        snapshot = StateSnapshot(
            current_state=State.S5_SEAT,
            last_non_security_state=State.S4_SECTION,
            budgets={"retry": 3},
            counters={},
            elapsed_ms=0,
        )
        event = SemanticEvent(event_type="SEAT_TAKEN")
        result = transition(State.S5_SEAT, event, default_policy, snapshot)

        assert result.next_state == State.S5_SEAT

    def test_s5_seat_taken_budget_exhausted_rollback(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """S5: SEAT_TAKEN + 예산 소진 → S4로 롤백."""
        snapshot = StateSnapshot(
            current_state=State.S5_SEAT,
            last_non_security_state=State.S4_SECTION,
            budgets={"retry": 0},  # 예산 소진
            counters={},
            elapsed_ms=0,
        )
        event = SemanticEvent(event_type="SEAT_TAKEN")
        result = transition(State.S5_SEAT, event, default_policy, snapshot)

        assert result.next_state == State.S4_SECTION

    def test_s6_hold_failed_with_budget_rollback_to_s5(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """S6: HOLD_FAILED + 예산 남음 → S5로 롤백."""
        snapshot = StateSnapshot(
            current_state=State.S6_TRANSACTION,
            last_non_security_state=State.S5_SEAT,
            budgets={"retry": 2},
            counters={},
            elapsed_ms=0,
        )
        event = SemanticEvent(event_type="HOLD_FAILED")
        result = transition(State.S6_TRANSACTION, event, default_policy, snapshot)

        assert result.next_state == State.S5_SEAT

    def test_s6_hold_failed_budget_exhausted_rollback_to_s4(
        self,
        default_policy: PolicySnapshot,
    ) -> None:
        """S6: HOLD_FAILED + 예산 소진 → S4로 롤백."""
        snapshot = StateSnapshot(
            current_state=State.S6_TRANSACTION,
            last_non_security_state=State.S5_SEAT,
            budgets={"retry": 0},
            counters={},
            elapsed_ms=0,
        )
        event = SemanticEvent(event_type="HOLD_FAILED")
        result = transition(State.S6_TRANSACTION, event, default_policy, snapshot)

        assert result.next_state == State.S4_SECTION

    def test_s6_txn_rollback_required(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """S6: TXN_ROLLBACK_REQUIRED → S5로 롤백."""
        event = SemanticEvent(event_type="TXN_ROLLBACK_REQUIRED")
        result = transition(State.S6_TRANSACTION, event, default_policy, default_snapshot)

        assert result.next_state == State.S5_SEAT


# ═══════════════════════════════════════════════════════════════════════════════
# 터미널 전이 테스트 (Terminal Transitions)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTerminalTransitions:
    """터미널 상태 전이 테스트."""

    def test_fatal_error_from_any_state(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """어떤 상태에서든 FATAL_ERROR → SX (abort)."""
        event = SemanticEvent(event_type="FATAL_ERROR", failure_code="NETWORK_ERROR")

        for state in [State.S0_INIT, State.S2_QUEUE_ENTRY, State.S5_SEAT]:
            result = transition(state, event, default_policy, default_snapshot)
            assert result.next_state == State.SX_TERMINAL
            assert result.terminal_reason == "abort"

    def test_policy_abort(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """POLICY_ABORT → SX (abort)."""
        event = SemanticEvent(event_type="POLICY_ABORT")
        result = transition(State.S4_SECTION, event, default_policy, default_snapshot)

        assert result.next_state == State.SX_TERMINAL
        assert result.terminal_reason == "abort"

    def test_cooldown_triggered(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """COOLDOWN_TRIGGERED → SX (cooldown)."""
        event = SemanticEvent(event_type="COOLDOWN_TRIGGERED")
        result = transition(State.S2_QUEUE_ENTRY, event, default_policy, default_snapshot)

        assert result.next_state == State.SX_TERMINAL
        assert result.terminal_reason == "cooldown"

    def test_payment_timeout(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """S6: PAYMENT_TIMEOUT → SX (abort)."""
        event = SemanticEvent(event_type="PAYMENT_TIMEOUT")
        result = transition(State.S6_TRANSACTION, event, default_policy, default_snapshot)

        assert result.next_state == State.SX_TERMINAL
        assert result.terminal_reason == "abort"
        assert result.failure_code == "PAYMENT_TIMEOUT"


# ═══════════════════════════════════════════════════════════════════════════════
# 유효하지 않은 이벤트 테스트 (Invalid Event Handling)
# ═══════════════════════════════════════════════════════════════════════════════


class TestInvalidEventHandling:
    """유효하지 않은 이벤트 처리 테스트 - log + ignore (상태 유지)."""

    def test_invalid_event_in_s0_ignored(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """S0에서 유효하지 않은 이벤트 → 무시하고 S0 유지."""
        event = SemanticEvent(event_type="QUEUE_PASSED")  # S0에서 유효하지 않음
        result = transition(State.S0_INIT, event, default_policy, default_snapshot)

        assert result.next_state == State.S0_INIT
        assert "무시" in result.notes[0]

    def test_invalid_event_in_s4_ignored(
        self,
        default_policy: PolicySnapshot,
        default_snapshot: StateSnapshot,
    ) -> None:
        """S4에서 유효하지 않은 이벤트 → 무시하고 S4 유지."""
        event = SemanticEvent(event_type="PAYMENT_COMPLETE")  # S4에서 유효하지 않음
        result = transition(State.S4_SECTION, event, default_policy, default_snapshot)

        assert result.next_state == State.S4_SECTION
        assert "무시" in result.notes[0]
