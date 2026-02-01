"""
StateStore - 상태 스냅샷 저장소 계층.

상태 머신 스냅샷을 위한 순수 저장소 계층을 제공합니다.
이 저장소는 상태를 관리하지만 전이 판단은 하지 않습니다.

A0-1-T3: StateStore 구현.
"""

from traffic_master_ai.attack.a0_poc.snapshots import StateSnapshot
from traffic_master_ai.attack.a0_poc.states import State


class StateStore:
    """
    상태 스냅샷 저장소 계층.
    
    전이 판단 없이 현재 상태 스냅샷을 관리합니다.
    순수 저장소 컴포넌트로, 모든 판단 로직은 다른 곳에 있습니다.
    
    책임:
    - current_state 관리
    - last_non_security_state 관리
    - budgets / counters 저장 및 조작
    - elapsed_ms 추적
    - 스냅샷 복사 / 조회 기능
    """
    
    __slots__ = ("_snapshot",)
    
    def __init__(
        self,
        initial_state: State = State.S0_INIT,
        budgets: dict[str, int] | None = None,
        counters: dict[str, int] | None = None,
    ) -> None:
        """
        선택적 초기 설정으로 StateStore를 초기화합니다.
        
        Args:
            initial_state: 시작 상태 (기본값: S0_INIT)
            budgets: 초기 예산 값 (기본값: 빈 딕셔너리)
            counters: 초기 카운터 값 (기본값: 빈 딕셔너리)
        """
        self._snapshot = StateSnapshot(
            current_state=initial_state,
            last_non_security_state=None,
            budgets=dict(budgets) if budgets else {},
            counters=dict(counters) if counters else {},
            elapsed_ms=0,
        )
    
    # ─────────────────────────────────────────────────────────────────
    # 상태 관리
    # ─────────────────────────────────────────────────────────────────
    
    @property
    def current_state(self) -> State:
        """현재 상태를 반환합니다."""
        return self._snapshot.current_state
    
    def set_state(self, state: State) -> None:
        """
        현재 상태를 설정합니다.
        
        주의: last_non_security_state를 자동으로 업데이트하지 않습니다.
        호출자(전이 로직)가 직접 처리해야 합니다.
        """
        self._snapshot.current_state = state
    
    @property
    def last_non_security_state(self) -> State | None:
        """마지막 비보안 상태를 반환합니다 (S3 복귀용)."""
        return self._snapshot.last_non_security_state
    
    def set_last_non_security_state(self, state: State | None) -> None:
        """마지막 비보안 상태를 설정합니다."""
        self._snapshot.last_non_security_state = state
    
    # ─────────────────────────────────────────────────────────────────
    # 예산(Budget) 관리
    # ─────────────────────────────────────────────────────────────────
    
    def get_budget(self, key: str, default: int = 0) -> int:
        """키로 예산 값을 조회합니다."""
        return self._snapshot.budgets.get(key, default)
    
    def set_budget(self, key: str, value: int) -> None:
        """예산 값을 설정합니다."""
        self._snapshot.budgets[key] = value
    
    def increment_budget(self, key: str, amount: int = 1) -> int:
        """
        예산을 증가시키고 새 값을 반환합니다.
        
        키가 없으면 amount 값으로 생성합니다.
        """
        current = self._snapshot.budgets.get(key, 0)
        new_value = current + amount
        self._snapshot.budgets[key] = new_value
        return new_value
    
    def decrement_budget(self, key: str, amount: int = 1) -> int:
        """
        예산을 감소시키고 새 값을 반환합니다.
        
        음수 값을 방지하지 않습니다 (호출자가 확인해야 함).
        키가 없으면 -amount 값으로 생성합니다.
        """
        current = self._snapshot.budgets.get(key, 0)
        new_value = current - amount
        self._snapshot.budgets[key] = new_value
        return new_value
    
    def reset_budget(self, key: str, value: int = 0) -> None:
        """예산을 지정된 값으로 리셋합니다 (기본값: 0)."""
        self._snapshot.budgets[key] = value
    
    def reset_all_budgets(self, initial_values: dict[str, int] | None = None) -> None:
        """모든 예산을 초기값으로 리셋하거나 비웁니다."""
        self._snapshot.budgets.clear()
        if initial_values:
            self._snapshot.budgets.update(initial_values)
    
    # ─────────────────────────────────────────────────────────────────
    # 카운터(Counter) 관리
    # ─────────────────────────────────────────────────────────────────
    
    def get_counter(self, key: str, default: int = 0) -> int:
        """키로 카운터 값을 조회합니다."""
        return self._snapshot.counters.get(key, default)
    
    def set_counter(self, key: str, value: int) -> None:
        """카운터 값을 설정합니다."""
        self._snapshot.counters[key] = value
    
    def increment_counter(self, key: str, amount: int = 1) -> int:
        """
        카운터를 증가시키고 새 값을 반환합니다.
        
        키가 없으면 amount 값으로 생성합니다.
        """
        current = self._snapshot.counters.get(key, 0)
        new_value = current + amount
        self._snapshot.counters[key] = new_value
        return new_value
    
    def decrement_counter(self, key: str, amount: int = 1) -> int:
        """
        카운터를 감소시키고 새 값을 반환합니다.
        
        음수 값을 방지하지 않습니다.
        """
        current = self._snapshot.counters.get(key, 0)
        new_value = current - amount
        self._snapshot.counters[key] = new_value
        return new_value
    
    def reset_counter(self, key: str, value: int = 0) -> None:
        """카운터를 지정된 값으로 리셋합니다 (기본값: 0)."""
        self._snapshot.counters[key] = value
    
    def reset_all_counters(self) -> None:
        """모든 카운터를 비웁니다."""
        self._snapshot.counters.clear()
    
    # ─────────────────────────────────────────────────────────────────
    # 경과 시간 관리
    # ─────────────────────────────────────────────────────────────────
    
    @property
    def elapsed_ms(self) -> int:
        """경과 시간을 밀리초 단위로 반환합니다."""
        return self._snapshot.elapsed_ms
    
    def add_elapsed_ms(self, delta_ms: int) -> int:
        """
        경과 시간을 추가하고 새 총합을 반환합니다.
        
        Args:
            delta_ms: 추가할 밀리초 (음수 불가)
            
        Returns:
            새 총 elapsed_ms
            
        Raises:
            ValueError: delta_ms가 음수인 경우
        """
        if delta_ms < 0:
            raise ValueError("delta_ms는 음수일 수 없습니다")
        self._snapshot.elapsed_ms += delta_ms
        return self._snapshot.elapsed_ms
    
    def reset_elapsed_ms(self) -> None:
        """경과 시간을 0으로 리셋합니다."""
        self._snapshot.elapsed_ms = 0
    
    # ─────────────────────────────────────────────────────────────────
    # 스냅샷 연산
    # ─────────────────────────────────────────────────────────────────
    
    def get_snapshot(self) -> StateSnapshot:
        """
        현재 스냅샷의 복사본을 반환합니다.
        
        외부 수정을 방지하기 위해 복사본을 반환합니다.
        """
        return self._snapshot.copy()
    
    def copy(self) -> "StateStore":
        """
        이 StateStore와 동일한 상태를 가진 새 인스턴스를 생성합니다.
        
        체크포인트 생성이나 테스트에 유용합니다.
        """
        new_store = StateStore.__new__(StateStore)
        new_store._snapshot = self._snapshot.copy()
        return new_store
    
    @classmethod
    def from_snapshot(cls, snapshot: StateSnapshot) -> "StateStore":
        """
        기존 스냅샷으로부터 StateStore를 생성합니다.
        
        원본을 참조하지 않고 스냅샷의 복사본을 생성합니다.
        """
        store = cls.__new__(cls)
        store._snapshot = snapshot.copy()
        return store
    
    # ─────────────────────────────────────────────────────────────────
    # 유틸리티
    # ─────────────────────────────────────────────────────────────────
    
    def __repr__(self) -> str:
        """디버깅용 문자열 표현을 반환합니다."""
        return (
            f"StateStore("
            f"state={self._snapshot.current_state.value}, "
            f"elapsed_ms={self._snapshot.elapsed_ms}, "
            f"budgets={self._snapshot.budgets}, "
            f"counters={self._snapshot.counters})"
        )
