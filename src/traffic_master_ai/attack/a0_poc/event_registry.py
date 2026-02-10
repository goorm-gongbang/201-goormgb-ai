"""Event Registry - Event Dictionary Spec v1.0 완전 구현.

A0-2-T1: EventType enum (33개), EventSource enum, EVENT_VALID_STATES 매핑.
"""

from enum import Enum

from traffic_master_ai.attack.a0_poc.states import State


# ═══════════════════════════════════════════════════════════════════════════════
# EventType Enum (33개 이벤트)
# Event Dictionary Spec v1.0 §2.5 Event Definitions
# ═══════════════════════════════════════════════════════════════════════════════


from traffic_master_ai.common.models.events import EventType
from traffic_master_ai.attack.a0_poc.states import State


# ═══════════════════════════════════════════════════════════════════════════════
# EventSource Enum
# ═══════════════════════════════════════════════════════════════════════════════


class EventSource(str, Enum):
    """이벤트 발생 소스."""
    
    UI = "ui"           # 브라우저 UI 이벤트
    API = "api"         # API 응답
    TIMER = "timer"     # 타이머/타임아웃
    DEFENSE = "defense" # 방어 시스템 감지
    MOCK = "mock"       # 테스트/시뮬레이션


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT_VALID_STATES 매핑
# 각 EventType이 발생할 수 있는 유효한 State 집합
# ═══════════════════════════════════════════════════════════════════════════════


# 편의를 위한 상태 그룹
_ALL_STATES = frozenset(State)
_NON_TERMINAL = frozenset({
    State.S0, State.S1, State.S2, 
    State.S3, State.S4, State.S5, State.S6
})
_SECURITY_INTERRUPTIBLE = frozenset({
    State.S1, State.S2, 
    State.S4, State.S5, State.S6
})


EVENT_VALID_STATES: dict[EventType, frozenset[State]] = {
    # ─────────────────────────────────────────────────────────────────
    # A. Flow/System Events
    # ─────────────────────────────────────────────────────────────────
    EventType.FLOW_START: frozenset({State.S0}),
    EventType.FLOW_ABORT: _NON_TERMINAL,
    EventType.TIMEOUT: _NON_TERMINAL,
    EventType.SESSION_EXPIRED: _NON_TERMINAL,
    EventType.RETRY_BUDGET_EXCEEDED: _NON_TERMINAL,
    
    # ─────────────────────────────────────────────────────────────────
    # B. Entry/Queue Events
    # ─────────────────────────────────────────────────────────────────
    EventType.ENTRY_ENABLED: frozenset({State.S1}),
    EventType.ENTRY_NOT_READY: frozenset({State.S1}),
    EventType.ENTRY_BLOCKED: frozenset({State.S1}),
    EventType.QUEUE_SHOWN: frozenset({State.S2}),
    EventType.QUEUE_PASSED: frozenset({State.S2}),
    EventType.QUEUE_STUCK: frozenset({State.S2}),
    EventType.POPUP_OPENED: frozenset({State.S1, State.S2}),
    
    # ─────────────────────────────────────────────────────────────────
    # C. Security Events
    # ─────────────────────────────────────────────────────────────────
    EventType.CHALLENGE_APPEARED: frozenset({State.S3}),
    EventType.CHALLENGE_PASSED: frozenset({State.S3}),
    EventType.CHALLENGE_FAILED: frozenset({State.S3}),
    EventType.CHALLENGE_NOT_PRESENT: frozenset({State.S3}),
    
    # ─────────────────────────────────────────────────────────────────
    # D. Section Events
    # ─────────────────────────────────────────────────────────────────
    EventType.SECTION_LIST_READY: frozenset({State.S4}),
    EventType.SECTION_SELECTED: frozenset({State.S4}),
    EventType.SECTION_EMPTY: frozenset({State.S4}),
    
    # ─────────────────────────────────────────────────────────────────
    # E. Seat Events
    # ─────────────────────────────────────────────────────────────────
    EventType.SEATMAP_READY: frozenset({State.S5}),
    EventType.SEAT_SELECTED: frozenset({State.S5}),
    EventType.SEAT_TAKEN: frozenset({State.S5}),
    EventType.HOLD_ACQUIRED: frozenset({State.S5, State.S6}),
    EventType.HOLD_FAILED: frozenset({State.S5, State.S6}),
    
    # ─────────────────────────────────────────────────────────────────
    # F. Transaction Events
    # ─────────────────────────────────────────────────────────────────
    EventType.PAYMENT_PAGE_ENTERED: frozenset({State.S6}),
    EventType.PAYMENT_COMPLETED: frozenset({State.S6}),
    EventType.PAYMENT_ABORTED: frozenset({State.S6}),
    EventType.PAYMENT_TIMEOUT: frozenset({State.S6}),
    EventType.TXN_ROLLBACK_REQUIRED: frozenset({State.S6}),
    
    # ─────────────────────────────────────────────────────────────────
    # G. Defense Events (S3 인터럽트 가능한 상태에서 발생)
    # ─────────────────────────────────────────────────────────────────
    EventType.DEF_CHALLENGE_FORCED: _SECURITY_INTERRUPTIBLE,
    EventType.DEF_THROTTLED: _SECURITY_INTERRUPTIBLE,
    EventType.DEF_SANDBOXED: _SECURITY_INTERRUPTIBLE,
    EventType.DEF_HONEY_SHAPED: _SECURITY_INTERRUPTIBLE,
}


def get_valid_states(event_type: EventType) -> frozenset[State]:
    """주어진 이벤트 타입이 유효한 상태 집합을 반환한다."""
    return EVENT_VALID_STATES.get(event_type, frozenset())


def is_valid_in_state(event_type: EventType, state: State) -> bool:
    """주어진 이벤트가 해당 상태에서 유효한지 확인한다."""
    return state in get_valid_states(event_type)
