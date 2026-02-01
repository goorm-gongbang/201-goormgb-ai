"""전이 결과 및 순수 전이 함수 정의.

A0-1-T4: State Machine Spec v1.0 기반 순수 전이 함수 구현.
"""

from dataclasses import dataclass, field
from typing import Any

from traffic_master_ai.attack.a0_poc.events import SemanticEvent
from traffic_master_ai.attack.a0_poc.snapshots import PolicySnapshot, StateSnapshot
from traffic_master_ai.attack.a0_poc.states import State, TERMINAL_REASONS


@dataclass(frozen=True, slots=True)
class TransitionResult:
    """
    순수 전이 함수의 결과.

    불변(immutable)하여 사이드 이펙트가 없음을 보장합니다.
    commands 필드는 의도 수준의 명령만 포함 (실제 실행은 다른 곳에서 처리).

    Attributes:
        next_state: 전이할 다음 상태
        terminal_reason: SX로 전이 시 이유 (done|abort|cooldown|reset)
        failure_code: 오류 추적용 실패 코드 (선택)
        notes: 전이 결정에 대한 사람이 읽을 수 있는 메모
        commands: 의도 수준 명령 (실행되지 않고 기록만 됨)
    """

    next_state: State
    terminal_reason: str | None = None
    failure_code: str | None = None
    notes: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """next_state가 SX인 경우에만 terminal_reason이 필수."""
        if self.next_state.is_terminal() and self.terminal_reason is None:
            raise ValueError("SX_TERMINAL일 때 terminal_reason 필수")
        if not self.next_state.is_terminal() and self.terminal_reason is not None:
            raise ValueError("터미널 상태가 아닐 때 terminal_reason은 None이어야 함")

    def is_terminal(self) -> bool:
        """이 결과가 터미널 상태로 이어지는지 확인."""
        return self.next_state.is_terminal()


@dataclass(frozen=True, slots=True)
class DecisionLog:
    """
    감사/재생 목적의 결정 로그 항목 스키마.

    스키마 정의만 제공 - 실제 파일 저장/JSONL 작성은
    별도 계층에서 처리 (A0-1 범위 외).
    """

    decision_id: str
    timestamp_ms: int
    current_state: State
    event: SemanticEvent
    next_state: State
    policy_profile: str
    budgets: dict[str, int]
    counters: dict[str, int]
    elapsed_ms: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """직렬화를 위한 딕셔너리 변환 (스키마만, I/O 없음)."""
        return {
            "decision_id": self.decision_id,
            "timestamp_ms": self.timestamp_ms,
            "current_state": self.current_state.value,
            "event": {
                "event_type": self.event.event_type,
                "stage": self.event.stage.value if self.event.stage else None,
                "failure_code": self.event.failure_code,
                "context": self.event.context,
            },
            "next_state": self.next_state.value,
            "policy_profile": self.policy_profile,
            "budgets": self.budgets,
            "counters": self.counters,
            "elapsed_ms": self.elapsed_ms,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """
    상태 머신 실행 런의 최종 결과.

    시작부터 터미널 상태까지의 전체 실행 경로를 캡처합니다.
    """

    state_path: list[State]
    terminal_state: State
    terminal_reason: str
    handled_events: int
    total_elapsed_ms: int
    final_budgets: dict[str, int] = field(default_factory=dict)
    final_counters: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """터미널 상태가 SX인지 검증."""
        if not self.terminal_state.is_terminal():
            raise ValueError("terminal_state는 SX_TERMINAL이어야 함")
        if self.terminal_reason not in TERMINAL_REASONS:
            raise ValueError(f"유효하지 않은 terminal_reason: {self.terminal_reason}")

    def is_success(self) -> bool:
        """실행이 성공적으로 완료되었는지 확인."""
        return self.terminal_reason == "done"


# ═══════════════════════════════════════════════════════════════════════════════
# 순수 전이 함수 (Pure Transition Function)
# State Machine Spec v1.0 구현
# ═══════════════════════════════════════════════════════════════════════════════


def transition(
    state: State,
    event: SemanticEvent,
    policy_snapshot: PolicySnapshot,
    state_snapshot: StateSnapshot,
) -> TransitionResult:
    """
    상태 머신의 순수 전이 함수.

    State Machine Spec v1.0에 정의된 모든 전이 규칙을 1:1로 반영합니다.
    사이드 이펙트 없음: 파일 I/O, 전역 상태 변경, sleep/time 호출 금지.

    Args:
        state: 현재 상태
        event: 발생한 시맨틱 이벤트
        policy_snapshot: 정책 스냅샷 (불변)
        state_snapshot: 상태 스냅샷 (예산, 카운터 등)

    Returns:
        TransitionResult: 다음 상태 및 메타데이터
    """
    event_type = event.event_type

    # ───────────────────────────────────────────────────────────────────────────
    # 글로벌 터미널 이벤트 (어떤 상태에서든 즉시 SX로)
    # ───────────────────────────────────────────────────────────────────────────
    if event_type == "FATAL_ERROR":
        return TransitionResult(
            next_state=State.SX_TERMINAL,
            terminal_reason="abort",
            failure_code=event.failure_code,
            notes=["FATAL_ERROR 발생 - 즉시 abort"],
        )

    if event_type == "POLICY_ABORT":
        return TransitionResult(
            next_state=State.SX_TERMINAL,
            terminal_reason="abort",
            notes=["정책 위반으로 abort"],
        )

    if event_type == "COOLDOWN_TRIGGERED":
        return TransitionResult(
            next_state=State.SX_TERMINAL,
            terminal_reason="cooldown",
            notes=["쿨다운 트리거됨"],
        )

    # ───────────────────────────────────────────────────────────────────────────
    # 보안 인터럽트 (S3 진입) - S1, S2, S4, S5, S6에서 가능
    # ───────────────────────────────────────────────────────────────────────────
    if event_type == "CHALLENGE_DETECTED" and state.can_be_last_non_security():
        return TransitionResult(
            next_state=State.S3_SECURITY,
            notes=[f"{state.value}에서 보안 챌린지 감지 - S3 인터럽트"],
        )

    # ───────────────────────────────────────────────────────────────────────────
    # S3 보안 상태에서의 전이
    # ───────────────────────────────────────────────────────────────────────────
    if state == State.S3_SECURITY:
        return _handle_s3_transition(event, state_snapshot)

    # ───────────────────────────────────────────────────────────────────────────
    # 상태별 정상 전이 규칙
    # ───────────────────────────────────────────────────────────────────────────
    if state == State.S0_INIT:
        return _handle_s0_transition(event)

    if state == State.S1_PRE_ENTRY:
        return _handle_s1_transition(event)

    if state == State.S2_QUEUE_ENTRY:
        return _handle_s2_transition(event)

    if state == State.S4_SECTION:
        return _handle_s4_transition(event)

    if state == State.S5_SEAT:
        return _handle_s5_transition(event, state_snapshot)

    if state == State.S6_TRANSACTION:
        return _handle_s6_transition(event, state_snapshot)

    # SX에서는 더 이상 전이 없음
    if state == State.SX_TERMINAL:
        return TransitionResult(
            next_state=State.SX_TERMINAL,
            terminal_reason="done",  # 이미 터미널
            notes=["이미 터미널 상태 - 상태 유지"],
        )

    # 알 수 없는 상태 (발생하면 안됨)
    return TransitionResult(
        next_state=state,
        notes=[f"알 수 없는 상태 {state.value} - 상태 유지"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 상태별 전이 핸들러
# ═══════════════════════════════════════════════════════════════════════════════


def _handle_s0_transition(event: SemanticEvent) -> TransitionResult:
    """S0 (Init/Bootstrap) 상태에서의 전이 처리."""
    if event.event_type == "BOOTSTRAP_COMPLETE":
        return TransitionResult(
            next_state=State.S1_PRE_ENTRY,
            notes=["부트스트랩 완료 - S1으로 전이"],
        )

    # S0에서 유효하지 않은 이벤트 - 무시하고 상태 유지
    return TransitionResult(
        next_state=State.S0_INIT,
        notes=[f"S0에서 유효하지 않은 이벤트 '{event.event_type}' - 무시"],
    )


def _handle_s1_transition(event: SemanticEvent) -> TransitionResult:
    """S1 (Pre-Entry) 상태에서의 전이 처리."""
    if event.event_type == "ENTRY_ENABLED":
        return TransitionResult(
            next_state=State.S2_QUEUE_ENTRY,
            notes=["입장 가능 - S2로 전이"],
        )

    return TransitionResult(
        next_state=State.S1_PRE_ENTRY,
        notes=[f"S1에서 유효하지 않은 이벤트 '{event.event_type}' - 무시"],
    )


def _handle_s2_transition(event: SemanticEvent) -> TransitionResult:
    """S2 (Queue & Entry) 상태에서의 전이 처리."""
    if event.event_type == "QUEUE_PASSED":
        return TransitionResult(
            next_state=State.S4_SECTION,
            notes=["대기열 통과 - S4로 전이"],
        )

    # 보안 챌린지 없이 S3 패스스루 케이스
    if event.event_type == "CHALLENGE_NOT_PRESENT":
        return TransitionResult(
            next_state=State.S4_SECTION,
            notes=["보안 챌린지 없음 - S4로 직접 전이"],
        )

    return TransitionResult(
        next_state=State.S2_QUEUE_ENTRY,
        notes=[f"S2에서 유효하지 않은 이벤트 '{event.event_type}' - 무시"],
    )


def _handle_s3_transition(
    event: SemanticEvent,
    state_snapshot: StateSnapshot,
) -> TransitionResult:
    """
    S3 (Security Verification) 상태에서의 전이 처리.

    SCN-03/SCN-04: ReturnTo = last_non_security_state
    """
    event_type = event.event_type

    # 챌린지 통과 - last_non_security_state로 복귀
    if event_type == "CHALLENGE_PASSED":
        return_to = state_snapshot.last_non_security_state
        if return_to is not None:
            return TransitionResult(
                next_state=return_to,
                notes=[f"챌린지 통과 - {return_to.value}로 복귀"],
            )
        # last_non_security_state가 없으면 S1으로 (안전한 기본값)
        return TransitionResult(
            next_state=State.S1_PRE_ENTRY,
            notes=["챌린지 통과 - last_non_security_state 없음, S1로 복귀"],
        )

    # 챌린지 없음 확인 - last_non_security_state로 복귀
    if event_type == "CHALLENGE_NOT_PRESENT":
        return_to = state_snapshot.last_non_security_state
        if return_to is not None:
            return TransitionResult(
                next_state=return_to,
                notes=[f"챌린지 없음 확인 - {return_to.value}로 복귀"],
            )
        return TransitionResult(
            next_state=State.S1_PRE_ENTRY,
            notes=["챌린지 없음 - last_non_security_state 없음, S1로 복귀"],
        )

    # 챌린지 실패 - 예산 확인 후 재시도 또는 터미널
    if event_type == "CHALLENGE_FAILED":
        security_budget = state_snapshot.budgets.get("security", 0)
        if security_budget > 0:
            # 예산 남음 - S3에서 대기 (재시도 가능)
            return TransitionResult(
                next_state=State.S3_SECURITY,
                notes=[f"챌린지 실패 - 예산 남음({security_budget}), S3 유지"],
            )
        # 예산 소진 - abort
        return TransitionResult(
            next_state=State.SX_TERMINAL,
            terminal_reason="abort",
            failure_code="SECURITY_BUDGET_EXHAUSTED",
            notes=["챌린지 실패 - 보안 예산 소진, abort"],
        )

    return TransitionResult(
        next_state=State.S3_SECURITY,
        notes=[f"S3에서 유효하지 않은 이벤트 '{event_type}' - 무시"],
    )


def _handle_s4_transition(event: SemanticEvent) -> TransitionResult:
    """S4 (Section Selection) 상태에서의 전이 처리."""
    if event.event_type == "SECTION_SELECTED":
        return TransitionResult(
            next_state=State.S5_SEAT,
            notes=["구역 선택 완료 - S5로 전이"],
        )

    return TransitionResult(
        next_state=State.S4_SECTION,
        notes=[f"S4에서 유효하지 않은 이벤트 '{event.event_type}' - 무시"],
    )


def _handle_s5_transition(
    event: SemanticEvent,
    state_snapshot: StateSnapshot,
) -> TransitionResult:
    """
    S5 (Seat Selection) 상태에서의 전이 처리.

    롤백 케이스 포함: SEAT_TAKEN → S5 유지 또는 S4로 롤백
    """
    event_type = event.event_type

    if event_type == "SEAT_SELECTED":
        return TransitionResult(
            next_state=State.S6_TRANSACTION,
            notes=["좌석 선택 완료 - S6으로 전이"],
        )

    # 롤백 케이스: 좌석 이미 선점됨
    if event_type == "SEAT_TAKEN":
        retry_budget = state_snapshot.budgets.get("retry", 0)
        if retry_budget > 0:
            # 예산 남음 - S5 유지하고 다른 좌석 시도
            return TransitionResult(
                next_state=State.S5_SEAT,
                notes=[f"좌석 선점됨 - 예산 남음({retry_budget}), S5 유지"],
            )
        # 예산 소진 - S4로 롤백하여 다른 구역 선택
        return TransitionResult(
            next_state=State.S4_SECTION,
            notes=["좌석 선점됨 - 예산 소진, S4로 롤백"],
        )

    return TransitionResult(
        next_state=State.S5_SEAT,
        notes=[f"S5에서 유효하지 않은 이벤트 '{event_type}' - 무시"],
    )


def _handle_s6_transition(
    event: SemanticEvent,
    state_snapshot: StateSnapshot,
) -> TransitionResult:
    """
    S6 (Transaction Monitor) 상태에서의 전이 처리.

    롤백 케이스 포함: HOLD_FAILED, TXN_ROLLBACK_REQUIRED
    """
    event_type = event.event_type

    # 정상 완료: 결제 완료
    if event_type == "PAYMENT_COMPLETE":
        return TransitionResult(
            next_state=State.SX_TERMINAL,
            terminal_reason="done",
            notes=["결제 완료 - 티켓팅 성공!"],
        )

    # 홀드 확인
    if event_type == "HOLD_CONFIRMED":
        return TransitionResult(
            next_state=State.S6_TRANSACTION,
            notes=["홀드 확인 - S6 유지, 결제 대기"],
        )

    # 롤백 케이스: 홀드 실패
    if event_type == "HOLD_FAILED":
        retry_budget = state_snapshot.budgets.get("retry", 0)
        if retry_budget > 0:
            return TransitionResult(
                next_state=State.S5_SEAT,
                notes=[f"홀드 실패 - 예산 남음({retry_budget}), S5로 롤백"],
            )
        return TransitionResult(
            next_state=State.S4_SECTION,
            notes=["홀드 실패 - 예산 소진, S4로 롤백"],
        )

    # 롤백 케이스: 트랜잭션 롤백 필요
    if event_type == "TXN_ROLLBACK_REQUIRED":
        return TransitionResult(
            next_state=State.S5_SEAT,
            notes=["트랜잭션 롤백 필요 - S5로 롤백"],
        )

    # 결제 타임아웃
    if event_type == "PAYMENT_TIMEOUT":
        return TransitionResult(
            next_state=State.SX_TERMINAL,
            terminal_reason="abort",
            failure_code="PAYMENT_TIMEOUT",
            notes=["결제 타임아웃 - abort"],
        )

    return TransitionResult(
        next_state=State.S6_TRANSACTION,
        notes=[f"S6에서 유효하지 않은 이벤트 '{event_type}' - 무시"],
    )
