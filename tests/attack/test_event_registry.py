"""Unit tests for Event Registry - A0-2-T1.

EventType(33개), EventSource(5개), EVENT_VALID_STATES 검증.
"""

import pytest

from traffic_master_ai.attack.a0_poc import (
    EVENT_VALID_STATES,
    EventSource,
    EventType,
    State,
    get_valid_states,
    is_valid_in_state,
)


# ═══════════════════════════════════════════════════════════════════════════════
# EventType Enum 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventType:
    """EventType enum 테스트."""

    def test_event_type_count(self) -> None:
        """EventType enum이 33개 값을 가지는지 확인."""
        assert len(EventType) == 33

    def test_flow_system_events(self) -> None:
        """A. Flow/System 이벤트 (5개)."""
        flow_events = [
            EventType.FLOW_START,
            EventType.FLOW_ABORT,
            EventType.TIMEOUT,
            EventType.SESSION_EXPIRED,
            EventType.RETRY_BUDGET_EXCEEDED,
        ]
        assert len(flow_events) == 5
        for event in flow_events:
            assert event.value == event.name

    def test_entry_queue_events(self) -> None:
        """B. Entry/Queue 이벤트 (7개)."""
        entry_events = [
            EventType.ENTRY_ENABLED,
            EventType.ENTRY_NOT_READY,
            EventType.ENTRY_BLOCKED,
            EventType.QUEUE_SHOWN,
            EventType.QUEUE_PASSED,
            EventType.QUEUE_STUCK,
            EventType.POPUP_OPENED,
        ]
        assert len(entry_events) == 7

    def test_security_events(self) -> None:
        """C. Security 이벤트 (4개)."""
        security_events = [
            EventType.CHALLENGE_APPEARED,
            EventType.CHALLENGE_PASSED,
            EventType.CHALLENGE_FAILED,
            EventType.CHALLENGE_NOT_PRESENT,
        ]
        assert len(security_events) == 4

    def test_section_events(self) -> None:
        """D. Section 이벤트 (3개)."""
        section_events = [
            EventType.SECTION_LIST_READY,
            EventType.SECTION_SELECTED,
            EventType.SECTION_EMPTY,
        ]
        assert len(section_events) == 3

    def test_seat_events(self) -> None:
        """E. Seat 이벤트 (5개)."""
        seat_events = [
            EventType.SEATMAP_READY,
            EventType.SEAT_SELECTED,
            EventType.SEAT_TAKEN,
            EventType.HOLD_ACQUIRED,
            EventType.HOLD_FAILED,
        ]
        assert len(seat_events) == 5

    def test_transaction_events(self) -> None:
        """F. Transaction 이벤트 (5개)."""
        txn_events = [
            EventType.PAYMENT_PAGE_ENTERED,
            EventType.PAYMENT_COMPLETED,
            EventType.PAYMENT_ABORTED,
            EventType.PAYMENT_TIMEOUT,
            EventType.TXN_ROLLBACK_REQUIRED,
        ]
        assert len(txn_events) == 5

    def test_defense_events(self) -> None:
        """G. Defense 이벤트 (4개)."""
        defense_events = [
            EventType.DEF_CHALLENGE_FORCED,
            EventType.DEF_THROTTLED,
            EventType.DEF_SANDBOXED,
            EventType.DEF_HONEY_SHAPED,
        ]
        assert len(defense_events) == 4

    def test_eventtype_is_str_enum(self) -> None:
        """EventType은 str Enum이어야 함."""
        assert isinstance(EventType.FLOW_START, str)
        assert EventType.FLOW_START == "FLOW_START"


# ═══════════════════════════════════════════════════════════════════════════════
# EventSource Enum 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventSource:
    """EventSource enum 테스트."""

    def test_event_source_count(self) -> None:
        """EventSource enum이 5개 값을 가지는지 확인."""
        assert len(EventSource) == 5

    def test_event_source_values(self) -> None:
        """EventSource 값 확인."""
        assert EventSource.UI.value == "ui"
        assert EventSource.API.value == "api"
        assert EventSource.TIMER.value == "timer"
        assert EventSource.DEFENSE.value == "defense"
        assert EventSource.MOCK.value == "mock"

    def test_eventsource_is_str_enum(self) -> None:
        """EventSource는 str Enum이어야 함."""
        assert isinstance(EventSource.UI, str)
        assert EventSource.MOCK == "mock"


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT_VALID_STATES 매핑 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventValidStates:
    """EVENT_VALID_STATES 매핑 테스트."""

    def test_all_event_types_mapped(self) -> None:
        """모든 EventType이 매핑되어 있는지 확인."""
        for event_type in EventType:
            assert event_type in EVENT_VALID_STATES, f"{event_type} not in mapping"

    def test_flow_start_only_in_s0(self) -> None:
        """FLOW_START는 S0에서만 유효."""
        valid_states = EVENT_VALID_STATES[EventType.FLOW_START]
        assert valid_states == frozenset({State.S0})

    def test_entry_enabled_only_in_s1(self) -> None:
        """ENTRY_ENABLED는 S1에서만 유효."""
        valid_states = EVENT_VALID_STATES[EventType.ENTRY_ENABLED]
        assert valid_states == frozenset({State.S1})

    def test_queue_passed_only_in_s2(self) -> None:
        """QUEUE_PASSED는 S2에서만 유효."""
        valid_states = EVENT_VALID_STATES[EventType.QUEUE_PASSED]
        assert valid_states == frozenset({State.S2})

    def test_challenge_events_only_in_s3(self) -> None:
        """Security 이벤트는 S3에서만 유효."""
        security_events = [
            EventType.CHALLENGE_APPEARED,
            EventType.CHALLENGE_PASSED,
            EventType.CHALLENGE_FAILED,
            EventType.CHALLENGE_NOT_PRESENT,
        ]
        for event_type in security_events:
            valid_states = EVENT_VALID_STATES[event_type]
            assert valid_states == frozenset({State.S3})

    def test_section_events_only_in_s4(self) -> None:
        """Section 이벤트는 S4에서만 유효."""
        section_events = [
            EventType.SECTION_LIST_READY,
            EventType.SECTION_SELECTED,
            EventType.SECTION_EMPTY,
        ]
        for event_type in section_events:
            valid_states = EVENT_VALID_STATES[event_type]
            assert valid_states == frozenset({State.S4})

    def test_defense_events_in_interruptible_states(self) -> None:
        """Defense 이벤트는 S3 인터럽트 가능한 상태에서 유효."""
        defense_events = [
            EventType.DEF_CHALLENGE_FORCED,
            EventType.DEF_THROTTLED,
            EventType.DEF_SANDBOXED,
            EventType.DEF_HONEY_SHAPED,
        ]
        expected = frozenset({
            State.S1,
            State.S2,
            State.S4,
            State.S5,
            State.S6,
        })
        for event_type in defense_events:
            assert EVENT_VALID_STATES[event_type] == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 헬퍼 함수 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelperFunctions:
    """헬퍼 함수 테스트."""

    def test_get_valid_states(self) -> None:
        """get_valid_states 함수 테스트."""
        states = get_valid_states(EventType.FLOW_START)
        assert states == frozenset({State.S0})

    def test_is_valid_in_state_true(self) -> None:
        """is_valid_in_state - 유효한 경우."""
        assert is_valid_in_state(EventType.FLOW_START, State.S0)
        assert is_valid_in_state(EventType.ENTRY_ENABLED, State.S1)
        assert is_valid_in_state(EventType.QUEUE_PASSED, State.S2)

    def test_is_valid_in_state_false(self) -> None:
        """is_valid_in_state - 유효하지 않은 경우."""
        assert not is_valid_in_state(EventType.FLOW_START, State.S1)
        assert not is_valid_in_state(EventType.ENTRY_ENABLED, State.S0)
        assert not is_valid_in_state(EventType.QUEUE_PASSED, State.SX)
