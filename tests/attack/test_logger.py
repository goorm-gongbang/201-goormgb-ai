"""Unit tests for Decision Logger - A0-1-T6.

DecisionLog 구조 정의 및 JSONL 변환 테스트.
파일 I/O 없음.
"""

import json

import pytest

from traffic_master_ai.attack.a0_poc import (
    DecisionLog,
    DecisionLogger,
    PolicySnapshot,
    SemanticEvent,
    State,
    StateSnapshot,
    TerminalReason,
    TransitionResult,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 테스트 픽스처
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def default_policy() -> PolicySnapshot:
    """기본 정책 스냅샷."""
    return PolicySnapshot(profile_name="aggressive", rules={"max_retry": 3})


@pytest.fixture
def sample_snapshot() -> StateSnapshot:
    """샘플 상태 스냅샷."""
    return StateSnapshot(
        current_state=State.S1,
        last_non_security_state=None,
        budgets={"retry": 3, "security": 2},
        counters={"attempts": 1},
        elapsed_ms=500,
    )


@pytest.fixture
def sample_event() -> SemanticEvent:
    """샘플 이벤트."""
    return SemanticEvent(type="ENTRY_ENABLED")


@pytest.fixture
def sample_result() -> TransitionResult:
    """샘플 전이 결과."""
    return TransitionResult(
        next_state=State.S2,
        notes=["입장 가능 - S2로 전이"],
    )


@pytest.fixture
def logger() -> DecisionLogger:
    """고정된 timestamp와 ID를 가진 로거."""
    return DecisionLogger(
        timestamp_provider=lambda: 1706500000000,
        id_generator=lambda: "test-decision-001",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DecisionLogger 기본 기능 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestDecisionLoggerBasic:
    """DecisionLogger 기본 기능 테스트."""

    def test_record_creates_decision_log(
        self,
        logger: DecisionLogger,
        default_policy: PolicySnapshot,
        sample_snapshot: StateSnapshot,
        sample_event: SemanticEvent,
        sample_result: TransitionResult,
    ) -> None:
        """record()가 DecisionLog를 생성하는지 확인."""
        log = logger.record(
            current_state=State.S1,
            event=sample_event,
            result=sample_result,
            policy=default_policy,
            snapshot=sample_snapshot,
        )

        assert isinstance(log, DecisionLog)
        assert log.decision_id == "test-decision-001"
        assert log.timestamp_ms == 1706500000000
        assert log.current_state == State.S1
        assert log.next_state == State.S2
        assert log.policy_profile == "aggressive"
        assert log.budgets == {"retry": 3, "security": 2}
        assert log.counters == {"attempts": 1}
        assert log.elapsed_ms == 500
        assert "입장 가능" in log.notes[0]

    def test_get_logs_returns_all_records(
        self,
        logger: DecisionLogger,
        default_policy: PolicySnapshot,
        sample_snapshot: StateSnapshot,
        sample_event: SemanticEvent,
        sample_result: TransitionResult,
    ) -> None:
        """get_logs()가 모든 기록을 반환하는지 확인."""
        logger.record(State.S1, sample_event, sample_result, default_policy, sample_snapshot)
        logger.record(State.S2, sample_event, sample_result, default_policy, sample_snapshot)

        logs = logger.get_logs()
        assert len(logs) == 2

    def test_count_returns_log_count(
        self,
        logger: DecisionLogger,
        default_policy: PolicySnapshot,
        sample_snapshot: StateSnapshot,
        sample_event: SemanticEvent,
        sample_result: TransitionResult,
    ) -> None:
        """count()가 정확한 로그 수를 반환하는지 확인."""
        assert logger.count() == 0

        logger.record(State.S1, sample_event, sample_result, default_policy, sample_snapshot)
        assert logger.count() == 1

        logger.record(State.S2, sample_event, sample_result, default_policy, sample_snapshot)
        assert logger.count() == 2

    def test_clear_removes_all_logs(
        self,
        logger: DecisionLogger,
        default_policy: PolicySnapshot,
        sample_snapshot: StateSnapshot,
        sample_event: SemanticEvent,
        sample_result: TransitionResult,
    ) -> None:
        """clear()가 모든 로그를 제거하는지 확인."""
        logger.record(State.S1, sample_event, sample_result, default_policy, sample_snapshot)
        logger.record(State.S2, sample_event, sample_result, default_policy, sample_snapshot)

        logger.clear()

        assert logger.count() == 0
        assert logger.get_logs() == []


# ═══════════════════════════════════════════════════════════════════════════════
# JSONL 변환 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestJsonlConversion:
    """JSONL 형식 변환 테스트."""

    def test_to_jsonl_returns_valid_jsonl(
        self,
        logger: DecisionLogger,
        default_policy: PolicySnapshot,
        sample_snapshot: StateSnapshot,
        sample_event: SemanticEvent,
        sample_result: TransitionResult,
    ) -> None:
        """to_jsonl()이 유효한 JSONL 문자열을 반환하는지 확인."""
        logger.record(State.S1, sample_event, sample_result, default_policy, sample_snapshot)

        jsonl = logger.to_jsonl()

        # 각 라인이 유효한 JSON인지 확인
        for line in jsonl.split("\n"):
            if line.strip():
                parsed = json.loads(line)
                assert "decision_id" in parsed
                assert "current_state" in parsed
                assert "next_state" in parsed

    def test_to_jsonl_one_line_per_decision(
        self,
        logger: DecisionLogger,
        default_policy: PolicySnapshot,
        sample_snapshot: StateSnapshot,
        sample_event: SemanticEvent,
        sample_result: TransitionResult,
    ) -> None:
        """1 line = 1 decision 구조 확인."""
        logger.record(State.S1, sample_event, sample_result, default_policy, sample_snapshot)
        logger.record(State.S2, sample_event, sample_result, default_policy, sample_snapshot)
        logger.record(State.S4, sample_event, sample_result, default_policy, sample_snapshot)

        jsonl = logger.to_jsonl()
        lines = [line for line in jsonl.split("\n") if line.strip()]

        assert len(lines) == 3

    def test_to_jsonl_empty_returns_empty_string(
        self,
        logger: DecisionLogger,
    ) -> None:
        """로그가 없으면 빈 문자열 반환."""
        assert logger.to_jsonl() == ""


# ═══════════════════════════════════════════════════════════════════════════════
# DecisionLog 필드 검증 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestDecisionLogFields:
    """DecisionLog 필드 완전성 테스트."""

    def test_all_required_fields_present(
        self,
        logger: DecisionLogger,
        default_policy: PolicySnapshot,
        sample_snapshot: StateSnapshot,
        sample_event: SemanticEvent,
        sample_result: TransitionResult,
    ) -> None:
        """SPEC에 정의된 모든 필드가 존재하는지 확인."""
        logger.record(State.S1, sample_event, sample_result, default_policy, sample_snapshot)

        jsonl = logger.to_jsonl()
        parsed = json.loads(jsonl)

        required_fields = [
            "decision_id",
            "timestamp_ms",
            "current_state",
            "event",
            "next_state",
            "policy_profile",
            "budgets",
            "counters",
            "elapsed_ms",
            "notes",
        ]

        for field in required_fields:
            assert field in parsed, f"필드 누락: {field}"

    def test_event_subfields_present(
        self,
        logger: DecisionLogger,
        default_policy: PolicySnapshot,
        sample_snapshot: StateSnapshot,
        sample_result: TransitionResult,
    ) -> None:
        """event 필드의 하위 필드가 존재하는지 확인."""
        event = SemanticEvent(
            event_type="CHALLENGE_FAILED",
            stage=State.S3,
            failure_code="CAPTCHA_TIMEOUT",
            context={"attempt": 2},
        )

        logger.record(State.S3, event, sample_result, default_policy, sample_snapshot)

        jsonl = logger.to_jsonl()
        parsed = json.loads(jsonl)

        event_data = parsed["event"]
        assert event_data["event_type"] == "CHALLENGE_FAILED"
        assert event_data["stage"] == "S3"
        assert event_data["failure_code"] == "CAPTCHA_TIMEOUT"
        assert event_data["context"] == {"attempt": 2}


# ═══════════════════════════════════════════════════════════════════════════════
# 시나리오 실행 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioExecution:
    """시나리오 1회 실행 시 이벤트 수만큼 DecisionLog 생성 테스트."""

    def test_logs_match_event_count(self) -> None:
        """처리된 이벤트 수만큼 DecisionLog가 생성되는지 확인."""
        counter = [0]

        def id_gen() -> str:
            counter[0] += 1
            return f"decision-{counter[0]:03d}"

        logger = DecisionLogger(
            timestamp_provider=lambda: 1706500000000,
            id_generator=id_gen,
        )
        policy = PolicySnapshot(profile_name="default", rules={})

        # 6개 이벤트 시뮬레이션
        events_and_transitions = [
            (State.S0, "BOOTSTRAP_COMPLETE", State.S1),
            (State.S1, "ENTRY_ENABLED", State.S2),
            (State.S2, "QUEUE_PASSED", State.S4),
            (State.S4, "SECTION_SELECTED", State.S5),
            (State.S5, "SEAT_SELECTED", State.S6),
            (State.S6, "PAYMENT_COMPLETE", State.SX),
        ]

        for current, event_type, next_state in events_and_transitions:
            event = SemanticEvent(type=event_type)
            snapshot = StateSnapshot(
                current_state=current,
                last_non_security_state=None,
                budgets={"retry": 3},
                counters={},
                elapsed_ms=0,
            )

            if next_state == State.SX:
                result = TransitionResult(
                    next_state=next_state,
                    terminal_reason=TerminalReason.DONE,
                    notes=[f"{current.value} -> {next_state.value}"],
                )
            else:
                result = TransitionResult(
                    next_state=next_state,
                    notes=[f"{current.value} -> {next_state.value}"],
                )

            logger.record(current, event, result, policy, snapshot)

        # 이벤트 수와 로그 수 일치
        assert logger.count() == 6

        # 각 로그의 ID가 순차적인지 확인
        logs = logger.get_logs()
        for i, log in enumerate(logs, 1):
            assert log.decision_id == f"decision-{i:03d}"
