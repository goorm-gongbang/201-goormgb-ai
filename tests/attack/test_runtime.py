"""Unit tests for Budget & Timebox Runtime - A0-2-T4.

BudgetManager, TimeboxManager 및 A0-1 StateStore 연동 검증.
"""

import pytest

from traffic_master_ai.attack.a0_poc import (
    BudgetManager,
    PolicyProfile,
    State,
    StateStore,
    TimeboxManager,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_profile() -> PolicyProfile:
    """테스트용 PolicyProfile."""
    return PolicyProfile(
        profile_name="test_runtime",
        budgets={
            "N_challenge": 2,
            "N_section": 4,
            "N_seat": 6,
            "N_hold": 3,
            "max_retries": 5,
            "seat_taken_threshold": 4,
        },
        timeboxes={
            "S1_timeout_ms": 30000,
            "S2_timeout_ms": 120000,
            "global_timeout_ms": 600000,
        },
        policies={"payment_timeout_policy": "abort"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BudgetManager 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestBudgetManager:
    """BudgetManager 테스트."""

    def test_initial_budgets_mapping(self, sample_profile: PolicyProfile) -> None:
        """Spec 키가 Runtime 키로 올바르게 매핑되는지 확인."""
        manager = BudgetManager(sample_profile)
        budgets = manager.get_initial_budgets()

        assert budgets["security"] == 2  # N_challenge
        assert budgets["section"] == 4   # N_section
        assert budgets["seat"] == 6      # N_seat
        assert budgets["hold"] == 3      # N_hold
        assert budgets["retry"] == 5     # max_retries
        assert budgets["seat_taken_threshold"] == 4

    def test_default_values(self) -> None:
        """설정값이 없을 때 기본값(0) 반환 확인."""
        empty_profile = PolicyProfile(profile_name="empty")
        manager = BudgetManager(empty_profile)
        budgets = manager.get_initial_budgets()

        for value in budgets.values():
            assert value == 0

    def test_get_budget_names(self, sample_profile: PolicyProfile) -> None:
        """관리하는 작업 이름 목록 확인."""
        manager = BudgetManager(sample_profile)
        names = manager.get_budget_names()
        expected = ["security", "section", "seat", "hold", "retry", "seat_taken_threshold"]
        for name in expected:
            assert name in names


# ═══════════════════════════════════════════════════════════════════════════════
# TimeboxManager 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestTimeboxManager:
    """TimeboxManager 테스트."""

    def test_stage_timebox_lookup(self, sample_profile: PolicyProfile) -> None:
        """스테이지별 타임박스 조회 확인."""
        manager = TimeboxManager(sample_profile)
        
        assert manager.get_stage_timebox(State.S1_PRE_ENTRY) == 30000
        assert manager.get_stage_timebox(State.S2_QUEUE_ENTRY) == 120000
        assert manager.get_stage_timebox(State.S4_SECTION) == 0  # 미설정 시

    def test_global_timebox(self, sample_profile: PolicyProfile) -> None:
        """글로벌 타임박스 조회 확인."""
        manager = TimeboxManager(sample_profile)
        assert manager.get_global_timebox() == 600000

    def test_unknown_state_returns_zero(self, sample_profile: PolicyProfile) -> None:
        """정의되지 않은 상태 요청 시 0 반환."""
        manager = TimeboxManager(sample_profile)
        assert manager.get_stage_timebox(State.SX_TERMINAL) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# A0-1 Integration 테스트 (StateStore)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRuntimeIntegration:
    """runtime 매니저와 A0-1 구성요소 간 연동 테스트."""

    def test_statestore_initialization(self, sample_profile: PolicyProfile) -> None:
        """BudgetManager.get_initial_budgets() 결과를 StateStore에 직접 주입 가능해야 함."""
        budget_manager = BudgetManager(sample_profile)
        initial_budgets = budget_manager.get_initial_budgets()

        # A0-1 StateStore 생성 및 연동
        store = StateStore(
            initial_state=State.S0_INIT,
            budgets=initial_budgets,
        )

        # 주입된 예산이 올바르게 반영되었는지 확인
        snapshot = store.get_snapshot()
        assert snapshot.budgets["security"] == 2
        assert snapshot.budgets["retry"] == 5
        assert snapshot.budgets["seat_taken_threshold"] == 4
