"""Event Validator - A0-2-T2 구현.

Event 유효성 검증 계층: A0-1 엔진에 입력되기 전 pre-check.
기본 정책: log + ignore (예외 없이 is_valid=False 반환).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from traffic_master_ai.attack.a0_poc.event_registry import (
    EVENT_VALID_STATES,
    EventSource,
    EventType,
    is_valid_in_state,
)
from traffic_master_ai.attack.a0_poc.events import SemanticEvent
from traffic_master_ai.attack.a0_poc.states import State

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ValidationError - strict 모드 예외
# ═══════════════════════════════════════════════════════════════════════════════


class ValidationError(Exception):
    """strict 모드에서 validation 실패 시 발생하는 예외."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {errors}")


# ═══════════════════════════════════════════════════════════════════════════════
# ValidationResult - 검증 결과 데이터 클래스
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """이벤트 검증 결과.
    
    Attributes:
        is_valid: 검증 통과 여부
        errors: 검증 실패 시 오류 메시지 목록
        event_type: 검증된 이벤트 타입 (참조용)
    """

    is_valid: bool
    errors: list[str]
    event_type: str | None = None

    @classmethod
    def success(cls, event_type: str | None = None) -> ValidationResult:
        """성공 결과 생성."""
        return cls(is_valid=True, errors=[], event_type=event_type)

    @classmethod
    def failure(cls, errors: list[str], event_type: str | None = None) -> ValidationResult:
        """실패 결과 생성."""
        return cls(is_valid=False, errors=errors, event_type=event_type)


# ═══════════════════════════════════════════════════════════════════════════════
# EventValidator - 이벤트 검증기 클래스
# ═══════════════════════════════════════════════════════════════════════════════


# 유효한 source 값 집합
_VALID_SOURCES = frozenset(source.value for source in EventSource)


class EventValidator:
    """Event 유효성 검증기.
    
    검증 계층:
        1. Schema Validation: 필수 필드, 값 형식 검증
        2. State-Validity Validation: 현재 상태에서 허용되는 이벤트인지 검증
    
    정책:
        - 기본: log + ignore (is_valid=False 반환, 예외 없음)
        - strict=True: ValidationError 발생
    
    Example:
        >>> validator = EventValidator()
        >>> from traffic_master_ai.common.models.events import EventType
        >>> event = SemanticEvent(type=EventType.FLOW_START)
        >>> result = validator.validate(event, State.S0)
        >>> result.is_valid
        True
    """

    def _is_valid_event_type(self, event_type: str) -> bool:
        """event_type이 EventType enum에 정의되어 있는지 확인."""
        try:
            EventType(event_type)
            return True
        except ValueError:
            return False

    def _is_valid_source(self, source: str) -> bool:
        """source 값이 유효한지 확인."""
        return source in _VALID_SOURCES

    def validate_schema(self, event: SemanticEvent) -> ValidationResult:
        """Schema 검증: 필수 필드 및 값 형식 검사.
        
        검증 항목:
            - event_type 필수
            - event_type이 EventType enum에 정의됨
            - source가 있으면 유효한 값인지
            - stage가 있으면 State enum 인스턴스인지
        
        Args:
            event: 검증할 SemanticEvent
            
        Returns:
            ValidationResult
        """
        errors: list[str] = []

        # event_type 검증
        if not event.type.value if hasattr(event.type, 'value') else event.type:
            errors.append("event_type is required")
        elif not self._is_valid_event_type(event.type.value if hasattr(event.type, 'value') else event.type):
            errors.append(f"unknown event_type: {event.type.value if hasattr(event.type, 'value') else event.type}")

        # source 검증 (context에 source 필드가 있다면)
        source = event.payload.get("source")
        if source is not None and not self._is_valid_source(source):
            errors.append(f"invalid source: {source}")

        # stage 검증
        if event.stage is not None and not isinstance(event.stage, State):
            errors.append(f"invalid stage: {event.stage}")

        if errors:
            return ValidationResult.failure(errors, event.type.value if hasattr(event.type, 'value') else event.type)
        return ValidationResult.success(event.type.value if hasattr(event.type, 'value') else event.type)

    def validate_state_validity(
        self,
        event: SemanticEvent,
        current_state: State,
    ) -> ValidationResult:
        """State-Validity 검증: 현재 상태에서 이벤트가 허용되는지 검사.
        
        EVENT_VALID_STATES 매핑을 기준으로 검증.
        
        Args:
            event: 검증할 SemanticEvent
            current_state: 현재 상태
            
        Returns:
            ValidationResult
        """
        errors: list[str] = []

        # EventType enum으로 변환 시도
        try:
            event_type_enum = EventType(event.type.value if hasattr(event.type, 'value') else event.type)
        except ValueError:
            # 알 수 없는 event_type - schema validation에서 처리
            errors.append(f"unknown event_type for state-validity: {event.type.value if hasattr(event.type, 'value') else event.type}")
            return ValidationResult.failure(errors, event.type.value if hasattr(event.type, 'value') else event.type)

        # State-validity 검증
        if not is_valid_in_state(event_type_enum, current_state):
            valid_states = EVENT_VALID_STATES.get(event_type_enum, frozenset())
            valid_state_names = [s.value for s in valid_states]
            errors.append(
                f"event '{event.type.value if hasattr(event.type, 'value') else event.type}' is not valid in state {current_state.value}. "
                f"Valid states: {valid_state_names}"
            )
            return ValidationResult.failure(errors, event.type.value if hasattr(event.type, 'value') else event.type)

        return ValidationResult.success(event.type.value if hasattr(event.type, 'value') else event.type)

    def validate(
        self,
        event: SemanticEvent,
        current_state: State,
        *,
        strict: bool = False,
    ) -> ValidationResult:
        """통합 검증: Schema + State-Validity 검증 수행.
        
        Args:
            event: 검증할 SemanticEvent
            current_state: 현재 상태
            strict: True면 실패 시 ValidationError 발생
            
        Returns:
            ValidationResult
            
        Raises:
            ValidationError: strict=True이고 검증 실패 시
        """
        all_errors: list[str] = []

        # Schema 검증
        schema_result = self.validate_schema(event)
        if not schema_result.is_valid:
            all_errors.extend(schema_result.errors)

        # State-validity 검증 (schema가 유효한 경우에만)
        if schema_result.is_valid:
            state_result = self.validate_state_validity(event, current_state)
            if not state_result.is_valid:
                all_errors.extend(state_result.errors)

        # 결과 처리
        if all_errors:
            # 로깅 (log + ignore 정책)
            logger.warning(
                "Event validation failed: event_type=%s, state=%s, errors=%s",
                event.type.value if hasattr(event.type, 'value') else event.type,
                current_state.value,
                all_errors,
            )

            # strict 모드면 예외 발생
            if strict:
                raise ValidationError(all_errors)

            return ValidationResult.failure(all_errors, event.type.value if hasattr(event.type, 'value') else event.type)

        return ValidationResult.success(event.type.value if hasattr(event.type, 'value') else event.type)
