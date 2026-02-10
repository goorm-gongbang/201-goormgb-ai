"""Scenario Data Models - Acceptance Scenario Spec v1.0.

Pydantic v2를 사용하여 시나리오 JSON 스캔 및 유효성 검증을 수행합니다.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from traffic_master_ai.attack.a0_poc.states import State, TerminalReason


class EventSource(str, Enum):
    """이벤트 발생 소스 (v1.0 스키마 준수)."""
    MOCK = "mock"
    TIMER = "timer"
    DEFENSE = "defense"
    UI = "ui"
    API = "api"


class ScenarioEvent(BaseModel):
    """시나리오 내 개별 이벤트 명세."""
    model_config = ConfigDict(frozen=True)

    type: str = Field(..., min_length=3)
    source: EventSource = EventSource.MOCK
    stage: str | None = None  # State value string (e.g., "S1")
    delay_ms: int = Field(0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, v: str | None) -> str | None:
        if v is None or v == "unknown":
            return v
        if v not in [s.value for s in State]:
            raise ValueError(f"Invalid stage in scenario: {v}")
        return v


class AssertionType(str, Enum):
    """지원하는 어썰션 타입 9종."""
    STATE_PATH_CONTAINS = "state_path_contains"
    STATE_PATH_EQUALS = "state_path_equals"
    COUNTER_AT_LEAST = "counter_at_least"
    COUNTER_EQUALS = "counter_equals"
    BUDGET_REMAINING_AT_MOST = "budget_remaining_at_most"
    EVENT_HANDLED_COUNT_AT_LEAST = "event_handled_count_at_least"
    RETURNED_TO_LAST_NON_SECURITY_STATE = "returned_to_last_non_security_state"
    LOG_LINES_AT_LEAST = "log_lines_at_least"
    NO_INVALID_EVENTS = "no_invalid_events"
    TERMINAL_REASON = "terminal_reason"


class ScenarioAssertion(BaseModel):
    """시나리오 검증 조건."""
    model_config = ConfigDict(frozen=True)

    type: AssertionType
    value: Any = None
    description: str | None = None


class ScenarioAcceptance(BaseModel):
    """시나리오 기대 결과 (Acceptance)."""
    model_config = ConfigDict(frozen=True)

    final_state: State
    terminal_reason: TerminalReason | None = None
    asserts: list[ScenarioAssertion] = Field(..., min_length=1)


class ScenarioMeta(BaseModel):
    """시나리오 메타데이터."""
    model_config = ConfigDict(extra="allow")

    tags: list[str] = Field(default_factory=list)
    version: str | None = None


class Scenario(BaseModel):
    """PoC-0 수락 테스트 시나리오 최상위 모델."""
    model_config = ConfigDict(frozen=True)

    id: str = Field(..., pattern=r"^SCN-[0-9]{2}$")
    name: str = Field(..., min_length=3)
    description: str | None = None
    initial_state: State
    policy_profile: str = Field(..., min_length=1)
    events: list[ScenarioEvent] = Field(..., min_length=1)
    accept: ScenarioAcceptance
    meta: ScenarioMeta = Field(default_factory=ScenarioMeta)
