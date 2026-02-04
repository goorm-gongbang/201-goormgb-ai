"""Unit tests for Event Validator - A0-2-T2.

EventValidator, ValidationResult, ValidationError 검증.
"""

import pytest

from traffic_master_ai.attack.a0_poc import (
    EVENT_VALID_STATES,
    EventType,
    EventValidator,
    SemanticEvent,
    State,
    ValidationError,
    ValidationResult,
)


# ═══════════════════════════════════════════════════════════════════════════════
# ValidationResult 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidationResult:
    """ValidationResult 테스트."""

    def test_success_result(self) -> None:
        """성공 결과 생성 테스트."""
        result = ValidationResult.success("FLOW_START")
        assert result.is_valid is True
        assert result.errors == []
        assert result.event_type == "FLOW_START"

    def test_failure_result(self) -> None:
        """실패 결과 생성 테스트."""
        errors = ["error1", "error2"]
        result = ValidationResult.failure(errors, "UNKNOWN")
        assert result.is_valid is False
        assert result.errors == errors
        assert result.event_type == "UNKNOWN"

    def test_result_is_immutable(self) -> None:
        """ValidationResult가 frozen인지 확인."""
        result = ValidationResult.success("FLOW_START")
        with pytest.raises(AttributeError):
            result.is_valid = False  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════════
# EventValidator.validate_schema 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateSchema:
    """validate_schema 메서드 테스트."""

    def setup_method(self) -> None:
        """테스트 설정."""
        self.validator = EventValidator()

    def test_valid_event_type(self) -> None:
        """유효한 event_type 검증."""
        event = SemanticEvent(event_type="FLOW_START")
        result = self.validator.validate_schema(event)
        assert result.is_valid is True
        assert result.errors == []

    def test_unknown_event_type(self) -> None:
        """알 수 없는 event_type 검증."""
        event = SemanticEvent(event_type="UNKNOWN_EVENT")
        result = self.validator.validate_schema(event)
        assert result.is_valid is False
        assert "unknown event_type" in result.errors[0]

    def test_valid_source_in_context(self) -> None:
        """유효한 source 검증."""
        event = SemanticEvent(
            event_type="FLOW_START",
            context={"source": "ui"},
        )
        result = self.validator.validate_schema(event)
        assert result.is_valid is True

    def test_invalid_source_in_context(self) -> None:
        """유효하지 않은 source 검증."""
        event = SemanticEvent(
            event_type="FLOW_START",
            context={"source": "invalid_source"},
        )
        result = self.validator.validate_schema(event)
        assert result.is_valid is False
        assert "invalid source" in result.errors[0]

    def test_valid_stage(self) -> None:
        """유효한 stage 검증."""
        event = SemanticEvent(
            event_type="FLOW_START",
            stage=State.S0_INIT,
        )
        result = self.validator.validate_schema(event)
        assert result.is_valid is True

    def test_all_valid_sources(self) -> None:
        """모든 유효한 source 값 테스트."""
        valid_sources = ["ui", "api", "timer", "defense", "mock"]
        for source in valid_sources:
            event = SemanticEvent(
                event_type="FLOW_START",
                context={"source": source},
            )
            result = self.validator.validate_schema(event)
            assert result.is_valid is True, f"source '{source}' should be valid"


# ═══════════════════════════════════════════════════════════════════════════════
# EventValidator.validate_state_validity 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateStateValidity:
    """validate_state_validity 메서드 테스트."""

    def setup_method(self) -> None:
        """테스트 설정."""
        self.validator = EventValidator()

    def test_flow_start_valid_in_s0(self) -> None:
        """FLOW_START는 S0에서만 유효."""
        event = SemanticEvent(event_type="FLOW_START")
        result = self.validator.validate_state_validity(event, State.S0_INIT)
        assert result.is_valid is True

    def test_flow_start_invalid_in_s1(self) -> None:
        """FLOW_START는 S1에서 유효하지 않음."""
        event = SemanticEvent(event_type="FLOW_START")
        result = self.validator.validate_state_validity(event, State.S1_PRE_ENTRY)
        assert result.is_valid is False
        assert "not valid in state" in result.errors[0]

    def test_entry_enabled_valid_in_s1(self) -> None:
        """ENTRY_ENABLED는 S1에서 유효."""
        event = SemanticEvent(event_type="ENTRY_ENABLED")
        result = self.validator.validate_state_validity(event, State.S1_PRE_ENTRY)
        assert result.is_valid is True

    def test_queue_passed_valid_in_s2(self) -> None:
        """QUEUE_PASSED는 S2에서 유효."""
        event = SemanticEvent(event_type="QUEUE_PASSED")
        result = self.validator.validate_state_validity(event, State.S2_QUEUE_ENTRY)
        assert result.is_valid is True

    def test_defense_event_valid_in_multiple_states(self) -> None:
        """Defense 이벤트는 여러 상태에서 유효."""
        event = SemanticEvent(event_type="DEF_CHALLENGE_FORCED")
        valid_states = [
            State.S1_PRE_ENTRY,
            State.S2_QUEUE_ENTRY,
            State.S4_SECTION,
            State.S5_SEAT,
            State.S6_TRANSACTION,
        ]
        for state in valid_states:
            result = self.validator.validate_state_validity(event, state)
            assert result.is_valid is True, f"should be valid in {state}"

    def test_unknown_event_type_fails(self) -> None:
        """알 수 없는 event_type은 실패."""
        event = SemanticEvent(event_type="UNKNOWN_EVENT")
        result = self.validator.validate_state_validity(event, State.S0_INIT)
        assert result.is_valid is False
        assert "unknown event_type" in result.errors[0]


# ═══════════════════════════════════════════════════════════════════════════════
# EventValidator.validate (통합) 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateIntegrated:
    """validate 메서드 (통합 검증) 테스트."""

    def setup_method(self) -> None:
        """테스트 설정."""
        self.validator = EventValidator()

    def test_valid_event_passes(self) -> None:
        """유효한 이벤트 통과."""
        event = SemanticEvent(event_type="FLOW_START")
        result = self.validator.validate(event, State.S0_INIT)
        assert result.is_valid is True

    def test_invalid_schema_fails(self) -> None:
        """잘못된 스키마 실패."""
        event = SemanticEvent(
            event_type="FLOW_START",
            context={"source": "invalid"},
        )
        result = self.validator.validate(event, State.S0_INIT)
        assert result.is_valid is False

    def test_invalid_state_validity_fails(self) -> None:
        """잘못된 상태 유효성 실패."""
        event = SemanticEvent(event_type="FLOW_START")
        result = self.validator.validate(event, State.S1_PRE_ENTRY)
        assert result.is_valid is False

    def test_default_policy_no_exception(self) -> None:
        """기본 정책: 실패 시 예외 없음 (log + ignore)."""
        event = SemanticEvent(event_type="UNKNOWN_EVENT")
        # 예외 발생하지 않음
        result = self.validator.validate(event, State.S0_INIT)
        assert result.is_valid is False

    def test_strict_mode_raises_exception(self) -> None:
        """strict 모드: 실패 시 ValidationError 발생."""
        event = SemanticEvent(event_type="UNKNOWN_EVENT")
        with pytest.raises(ValidationError) as exc_info:
            self.validator.validate(event, State.S0_INIT, strict=True)
        assert len(exc_info.value.errors) > 0

    def test_strict_mode_valid_event_no_exception(self) -> None:
        """strict 모드: 유효한 이벤트는 예외 없음."""
        event = SemanticEvent(event_type="FLOW_START")
        result = self.validator.validate(event, State.S0_INIT, strict=True)
        assert result.is_valid is True


# ═══════════════════════════════════════════════════════════════════════════════
# ValidationError 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidationError:
    """ValidationError 예외 테스트."""

    def test_error_contains_messages(self) -> None:
        """에러 메시지 포함 확인."""
        errors = ["error1", "error2"]
        exc = ValidationError(errors)
        assert exc.errors == errors
        assert "error1" in str(exc)
        assert "error2" in str(exc)

    def test_error_is_exception(self) -> None:
        """Exception 상속 확인."""
        exc = ValidationError(["test"])
        assert isinstance(exc, Exception)
