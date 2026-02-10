"""Unit tests for Failure Code Registry & Matrix Mapping - A0-3-T1.

FailureCode Enum 및 FailureMatrix 매핑 규칙 검증.
"""

import pytest

from traffic_master_ai.attack.a0_poc import (
    EventType,
    FailureCode,
    FailureMatrix,
    State,
)


class TestFailureMatrix:
    """FailureMatrix 매핑 검증 테스트."""

    @pytest.fixture
    def matrix(self) -> FailureMatrix:
        return FailureMatrix()

    def test_failure_code_enum_count(self) -> None:
        """12종 이상의 실패 코드가 정의되었는지 확인 (v1.0 Taxonomy)."""
        # Spec에 명시된 주요 실패 코드들 포함 여부 체크
        codes = {c.value for c in FailureCode}
        expected = {
            "F_SEAT_TAKEN", "F_HOLD_FAILED", "F_HOLD_EXPIRED", "F_SECTION_EMPTY",
            "F_CHALLENGE_FAILED", "F_THROTTLED_TIMEOUT", "F_SANDBOX_STUCK",
            "F_SESSION_EXPIRED", "F_NETWORK_TIMEOUT", "F_SERVER_ERROR",
            "F_CLIENT_ERROR", "F_UI_INCONSISTENT", "F_PAYMENT_TIMEOUT",
            "F_TXN_ROLLBACK"
        }
        # 14개가 정의됨 (v1.0 상세 분류 기준)
        for code in expected:
            assert code in codes

    def test_seat_taken_policy(self, matrix: FailureMatrix) -> None:
        """이선좌(S5, SEAT_TAKEN) 정책 검증."""
        policy = matrix.get_policy(State.S5, EventType.SEAT_TAKEN)
        assert policy is not None
        assert policy.failure_code == FailureCode.F_SEAT_TAKEN
        assert policy.recover_path == State.S5
        assert policy.retry_budget_key == "N_seat"

    def test_challenge_failed_policy(self, matrix: FailureMatrix) -> None:
        """챌린지 실패(S3, CHALLENGE_FAILED) 정책 검증."""
        policy = matrix.get_policy(State.S3, EventType.CHALLENGE_FAILED)
        assert policy is not None
        assert policy.failure_code == FailureCode.F_CHALLENGE_FAILED
        assert policy.recover_path == State.S3
        assert policy.retry_budget_key == "N_challenge"
        assert "cooldown" in policy.backoff_strategy

    def test_timeout_self_path(self, matrix: FailureMatrix) -> None:
        """TIMEOUT 시 'Self' 경로가 현재 상태로 치환되는지 검증."""
        # S4에서 타임아웃
        policy_s4 = matrix.get_policy(State.S4, EventType.TIMEOUT)
        assert policy_s4 is not None
        assert policy_s4.recover_path == State.S4

        # S1에서 타임아웃
        policy_s1 = matrix.get_policy(State.S1, EventType.TIMEOUT)
        assert policy_s1 is not None
        assert policy_s1.recover_path == State.S1

    def test_session_expired_rollback_to_s0(self, matrix: FailureMatrix) -> None:
        """세션 만료 시 어느 상태에서나 S0로 가는지 검증."""
        for state in [State.S2, State.S5, State.S6]:
            policy = matrix.get_policy(state, EventType.SESSION_EXPIRED)
            assert policy is not None
            assert policy.recover_path == State.S0
            assert policy.failure_code == FailureCode.F_SESSION_EXPIRED

    def test_unknown_event_returns_none(self, matrix: FailureMatrix) -> None:
        """실패가 아닌 일반 이벤트는 정책을 반환하지 않음."""
        policy = matrix.get_policy(State.S4, EventType.SECTION_SELECTED)
        assert policy is None

    def test_payment_timeout_leads_to_sx(self, matrix: FailureMatrix) -> None:
        """결제 타임아웃(S6) 시 SX로 종료되는지 확인."""
        policy = matrix.get_policy(State.S6, EventType.PAYMENT_TIMEOUT)
        assert policy is not None
        assert policy.recover_path == State.SX
        assert policy.failure_code == FailureCode.F_PAYMENT_TIMEOUT
