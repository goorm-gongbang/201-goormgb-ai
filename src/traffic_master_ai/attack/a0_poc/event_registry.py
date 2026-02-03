"""Event Registry - Event Dictionary Spec v1.0 완전 구현.

A0-2-T1: EventType enum (33개), EventSource enum, EVENT_VALID_STATES 매핑.
"""

from enum import Enum

from traffic_master_ai.attack.a0_poc.states import State


# ═══════════════════════════════════════════════════════════════════════════════
# EventType Enum (33개 이벤트)
# Event Dictionary Spec v1.0 §2.5 Event Definitions
# ═══════════════════════════════════════════════════════════════════════════════


class EventType(str, Enum):
    """
    Event Dictionary Spec v1.0에 정의된 33개 시맨틱 이벤트.
    
    Categories:
        A. Flow/System (5개)
        B. Entry/Queue (7개)
        C. Security (4개)
        D. Section (3개)
        E. Seat (5개)
        F. Transaction (5개)
        G. Defense (4개)
    """
    
    # ─────────────────────────────────────────────────────────────────
    # A. Flow/System Events (5개)
    # ─────────────────────────────────────────────────────────────────
    FLOW_START = "FLOW_START"
    FLOW_ABORT = "FLOW_ABORT"
    TIMEOUT = "TIMEOUT"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    RETRY_BUDGET_EXCEEDED = "RETRY_BUDGET_EXCEEDED"
    
    # ─────────────────────────────────────────────────────────────────
    # B. Entry/Queue Events (7개)
    # ─────────────────────────────────────────────────────────────────
    ENTRY_ENABLED = "ENTRY_ENABLED"
    ENTRY_NOT_READY = "ENTRY_NOT_READY"
    ENTRY_BLOCKED = "ENTRY_BLOCKED"
    QUEUE_SHOWN = "QUEUE_SHOWN"
    QUEUE_PASSED = "QUEUE_PASSED"
    QUEUE_STUCK = "QUEUE_STUCK"
    POPUP_OPENED = "POPUP_OPENED"
    
    # ─────────────────────────────────────────────────────────────────
    # C. Security Events (4개)
    # ─────────────────────────────────────────────────────────────────
    CHALLENGE_APPEARED = "CHALLENGE_APPEARED"
    CHALLENGE_PASSED = "CHALLENGE_PASSED"
    CHALLENGE_FAILED = "CHALLENGE_FAILED"
    CHALLENGE_NOT_PRESENT = "CHALLENGE_NOT_PRESENT"
    
    # ─────────────────────────────────────────────────────────────────
    # D. Section Events (3개)
    # ─────────────────────────────────────────────────────────────────
    SECTION_LIST_READY = "SECTION_LIST_READY"
    SECTION_SELECTED = "SECTION_SELECTED"
    SECTION_EMPTY = "SECTION_EMPTY"
    
    # ─────────────────────────────────────────────────────────────────
    # E. Seat Events (5개)
    # ─────────────────────────────────────────────────────────────────
    SEATMAP_READY = "SEATMAP_READY"
    SEAT_SELECTED = "SEAT_SELECTED"
    SEAT_TAKEN = "SEAT_TAKEN"
    HOLD_ACQUIRED = "HOLD_ACQUIRED"
    HOLD_FAILED = "HOLD_FAILED"
    
    # ─────────────────────────────────────────────────────────────────
    # F. Transaction Events (5개)
    # ─────────────────────────────────────────────────────────────────
    PAYMENT_PAGE_ENTERED = "PAYMENT_PAGE_ENTERED"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    PAYMENT_ABORTED = "PAYMENT_ABORTED"
    PAYMENT_TIMEOUT = "PAYMENT_TIMEOUT"
    TXN_ROLLBACK_REQUIRED = "TXN_ROLLBACK_REQUIRED"
    
    # ─────────────────────────────────────────────────────────────────
    # G. Defense Events (4개)
    # ─────────────────────────────────────────────────────────────────
    DEF_CHALLENGE_FORCED = "DEF_CHALLENGE_FORCED"
    DEF_THROTTLED = "DEF_THROTTLED"
    DEF_SANDBOXED = "DEF_SANDBOXED"
    DEF_HONEY_SHAPED = "DEF_HONEY_SHAPED"


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
    State.S0_INIT, State.S1_PRE_ENTRY, State.S2_QUEUE_ENTRY, 
    State.S3_SECURITY, State.S4_SECTION, State.S5_SEAT, State.S6_TRANSACTION
})
_SECURITY_INTERRUPTIBLE = frozenset({
    State.S1_PRE_ENTRY, State.S2_QUEUE_ENTRY, 
    State.S4_SECTION, State.S5_SEAT, State.S6_TRANSACTION
})


EVENT_VALID_STATES: dict[EventType, frozenset[State]] = {
    # ─────────────────────────────────────────────────────────────────
    # A. Flow/System Events
    # ─────────────────────────────────────────────────────────────────
    EventType.FLOW_START: frozenset({State.S0_INIT}),
    EventType.FLOW_ABORT: _NON_TERMINAL,
    EventType.TIMEOUT: _NON_TERMINAL,
    EventType.SESSION_EXPIRED: _NON_TERMINAL,
    EventType.RETRY_BUDGET_EXCEEDED: _NON_TERMINAL,
    
    # ─────────────────────────────────────────────────────────────────
    # B. Entry/Queue Events
    # ─────────────────────────────────────────────────────────────────
    EventType.ENTRY_ENABLED: frozenset({State.S1_PRE_ENTRY}),
    EventType.ENTRY_NOT_READY: frozenset({State.S1_PRE_ENTRY}),
    EventType.ENTRY_BLOCKED: frozenset({State.S1_PRE_ENTRY}),
    EventType.QUEUE_SHOWN: frozenset({State.S2_QUEUE_ENTRY}),
    EventType.QUEUE_PASSED: frozenset({State.S2_QUEUE_ENTRY}),
    EventType.QUEUE_STUCK: frozenset({State.S2_QUEUE_ENTRY}),
    EventType.POPUP_OPENED: frozenset({State.S1_PRE_ENTRY, State.S2_QUEUE_ENTRY}),
    
    # ─────────────────────────────────────────────────────────────────
    # C. Security Events
    # ─────────────────────────────────────────────────────────────────
    EventType.CHALLENGE_APPEARED: frozenset({State.S3_SECURITY}),
    EventType.CHALLENGE_PASSED: frozenset({State.S3_SECURITY}),
    EventType.CHALLENGE_FAILED: frozenset({State.S3_SECURITY}),
    EventType.CHALLENGE_NOT_PRESENT: frozenset({State.S3_SECURITY}),
    
    # ─────────────────────────────────────────────────────────────────
    # D. Section Events
    # ─────────────────────────────────────────────────────────────────
    EventType.SECTION_LIST_READY: frozenset({State.S4_SECTION}),
    EventType.SECTION_SELECTED: frozenset({State.S4_SECTION}),
    EventType.SECTION_EMPTY: frozenset({State.S4_SECTION}),
    
    # ─────────────────────────────────────────────────────────────────
    # E. Seat Events
    # ─────────────────────────────────────────────────────────────────
    EventType.SEATMAP_READY: frozenset({State.S5_SEAT}),
    EventType.SEAT_SELECTED: frozenset({State.S5_SEAT}),
    EventType.SEAT_TAKEN: frozenset({State.S5_SEAT}),
    EventType.HOLD_ACQUIRED: frozenset({State.S5_SEAT, State.S6_TRANSACTION}),
    EventType.HOLD_FAILED: frozenset({State.S5_SEAT, State.S6_TRANSACTION}),
    
    # ─────────────────────────────────────────────────────────────────
    # F. Transaction Events
    # ─────────────────────────────────────────────────────────────────
    EventType.PAYMENT_PAGE_ENTERED: frozenset({State.S6_TRANSACTION}),
    EventType.PAYMENT_COMPLETED: frozenset({State.S6_TRANSACTION}),
    EventType.PAYMENT_ABORTED: frozenset({State.S6_TRANSACTION}),
    EventType.PAYMENT_TIMEOUT: frozenset({State.S6_TRANSACTION}),
    EventType.TXN_ROLLBACK_REQUIRED: frozenset({State.S6_TRANSACTION}),
    
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
