"""Budget & Timebox Runtime - A0-2-T4 구현.

Policy Profile 기반의 예산 및 시간 제한 관리자.
"""

from __future__ import annotations

import logging
from typing import Any

from traffic_master_ai.attack.a0_poc.policy_loader import PolicyProfile
from traffic_master_ai.attack.a0_poc.states import State

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# BudgetManager - 예산 관리자
# ═══════════════════════════════════════════════════════════════════════════════


class BudgetManager:
    """Policy Profile에서 초기 예산 정보를 추출/매핑하는 관리자.
    
    Spec 명칭(N_challenge 등)을 런타임 명칭(security 등)으로 변환하여
    A0-1 StateStore와 연동 가능한 딕셔너리를 생성함.
    
    매핑 규칙:
        - N_challenge -> security
        - N_section   -> section
        - N_seat      -> seat
        - N_hold      -> hold
        - max_retries  -> retry
    """

    # Spec 키 -> 런타임 키 매핑
    _KEY_MAP = {
        "N_challenge": "security",
        "N_section": "section",
        "N_seat": "seat",
        "N_hold": "hold",
        "max_retries": "retry",
        "seat_taken_threshold": "seat_taken_threshold",
    }

    def __init__(self, profile: PolicyProfile) -> None:
        """
        Args:
            profile: 사용할 PolicyProfile 인스턴스
        """
        self._profile = profile

    def get_initial_budgets(self) -> dict[str, int]:
        """A0-1 StateStore 초기화에 사용할 예산 딕셔너리 반환.
        
        Returns:
            dict[str, int]: 매핑된 예산 정보 (예: {"security": 2, "retry": 3, ...})
        """
        budgets: dict[str, int] = {}
        
        # 정의된 매핑에 따라 초기값 추출
        for spec_key, runtime_key in self._KEY_MAP.items():
            value = self._profile.get_budget(spec_key, default=0)
            budgets[runtime_key] = value
            
        logger.debug(
            "Generated initial budgets from profile '%s': %s",
            self._profile.profile_name,
            budgets,
        )
        return budgets

    def get_budget_names(self) -> list[str]:
        """관리하는 런타임 예산 이름 목록 반환."""
        return list(self._KEY_MAP.values())


# ═══════════════════════════════════════════════════════════════════════════════
# TimeboxManager - 시간 제한 관리자
# ═══════════════════════════════════════════════════════════════════════════════


class TimeboxManager:
    """Policy Profile에서 스테이지별 시간 제한(Timebox) 정보를 추출하는 관리자.
    
    A0-1 엔진에서 각 상태 전이 시 해당 스테이지의 제한 시간을 조회할 때 사용.
    """

    # State -> Profile 키 매핑
    _STATE_MAP = {
        State.S0_INIT: "S0_timeout_ms",
        State.S1_PRE_ENTRY: "S1_timeout_ms",
        State.S2_QUEUE_ENTRY: "S2_timeout_ms",
        State.S3_SECURITY: "S3_timeout_ms",
        State.S4_SECTION: "S4_timeout_ms",
        State.S5_SEAT: "S5_timeout_ms",
        State.S6_TRANSACTION: "S6_timeout_ms",
    }

    def __init__(self, profile: PolicyProfile) -> None:
        """
        Args:
            profile: 사용할 PolicyProfile 인스턴스
        """
        self._profile = profile

    def get_stage_timebox(self, stage: State) -> int:
        """주어진 스테이지의 제한 시간(ms) 반환.
        
        Args:
            stage: 조회할 상태
            
        Returns:
            int: 제한 시간 (ms), 설정이 없으면 0 반환
        """
        key = self._STATE_MAP.get(stage)
        if not key:
            return 0
            
        return self._profile.get_timebox(key, default=0)

    def get_global_timebox(self) -> int:
        """전체 Flow의 글로벌 제한 시간(ms) 반환."""
        return self._profile.get_timebox("global_timeout_ms", default=0)

    def get_all_timeboxes(self) -> dict[str, int]:
        """모든 스테이지의 타임박스 정보를 딕셔너리로 반환."""
        return dict(self._profile.timeboxes)
