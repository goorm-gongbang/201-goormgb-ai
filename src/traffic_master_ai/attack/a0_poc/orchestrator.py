"""Orchestrator Loop - A0-1-T5.

Semantic Event 배열을 순차 처리하며 State Machine 엔진을 동작시키는 코어 루프.

Hard Rules:
1. Orchestrator는 판단하지 않는다.
2. transition 함수만 호출해 결과를 누적한다.
3. 이벤트는 입력 리스트를 그대로 소비만 한다.
"""

from traffic_master_ai.attack.a0_poc.events import SemanticEvent
from traffic_master_ai.attack.a0_poc.snapshots import PolicySnapshot, StateSnapshot
from traffic_master_ai.attack.a0_poc.event_registry import EventType
from traffic_master_ai.attack.a0_poc.states import State, TerminalReason
from traffic_master_ai.attack.a0_poc.store import StateStore
from traffic_master_ai.attack.a0_poc.transition import (
    ExecutionResult,
    TransitionResult,
    transition,
)
from traffic_master_ai.attack.a0_poc.failure import FailureMatrix, FailurePolicy
from traffic_master_ai.attack.a0_poc.roi import ROILogger


def run_events(
    events: list[SemanticEvent],
    store: StateStore,
    policy: PolicySnapshot,
    failure_matrix: FailureMatrix | None = None,
    roi_logger: ROILogger | None = None,
) -> ExecutionResult:
    """
    이벤트 리스트를 순차적으로 처리하여 ExecutionResult를 반환한다.

    Orchestrator는 판단하지 않고, transition 함수 결과만 누적한다.
    터미널 상태 도달 시 즉시 루프를 종료한다.

    Args:
        events: 처리할 SemanticEvent 리스트
        store: 상태 저장소 (StateStore)
        policy: 정책 스냅샷

    Returns:
        ExecutionResult: 실행 완료 후 결과
            - state_path: 방문한 상태 경로
            - terminal_state: 최종 터미널 상태
            - terminal_reason: 종료 이유
            - handled_events: 처리된 이벤트 수
            - total_elapsed_ms: 총 경과 시간
            - final_budgets: 최종 예산 스냅샷
            - final_counters: 최종 카운터 스냅샷

    Raises:
        ValueError: 터미널에 도달하지 않고 이벤트가 소진된 경우
    """
    # 초기 상태 기록
    state_path: list[State] = [store.get_snapshot().current_state]
    handled_events = 0
    last_result: TransitionResult | None = None

    for event in events:
        snapshot = store.get_snapshot()
        current_state = snapshot.current_state

        # 이미 터미널이면 더 이상 처리하지 않음
        if current_state.is_terminal():
            break

        # 전이 함수 호출 (판단은 transition에서만)
        result = transition(
            state=current_state,
            event=event,
            policy_snapshot=policy,
            state_snapshot=snapshot,
        )

        # 실패 처리 매트릭스 적용 (A0-3-T3)
        if failure_matrix:
            # EventType enum으로 캐스팅하여 매트릭스 조회
            try:
                et = EventType(event.type.value)
                failure_policy = failure_matrix.get_policy(current_state, et)
            except ValueError:
                failure_policy = None

            if failure_policy:
                # 1. 예산 차감 및 전이 결정
                result = _apply_failure_policy(store, failure_policy, result, event, roi_logger)
        
        last_result = result

        # 새 상태로 전이
        next_state = result.next_state
        store.set_state(next_state)

        # last_non_security_state 업데이트
        # S3 진입 시 이전 상태를 기록, S3에서 나갈 때는 업데이트하지 않음
        if next_state.is_security() and current_state.can_be_last_non_security():
            store.set_last_non_security_state(current_state)

        # state_path에 기록 (중복 방지)
        if state_path[-1] != next_state:
            state_path.append(next_state)

        handled_events += 1

        # 터미널 도달 시 종료
        if next_state.is_terminal():
            break

    # 최종 상태 확인
    final_snapshot = store.get_snapshot()
    final_state = final_snapshot.current_state

    # 터미널에 도달하지 않은 경우
    if not final_state.is_terminal():
        raise ValueError(
            f"이벤트 리스트 소진 후에도 터미널 미도달: current_state={final_state.value}"
        )

    # terminal_reason 결정
    terminal_reason: TerminalReason
    if last_result is not None and last_result.terminal_reason is not None:
        terminal_reason = last_result.terminal_reason
    else:
        # 이벤트 없이 시작부터 터미널인 경우 (예외적)
        terminal_reason = TerminalReason.DONE

    return ExecutionResult(
        state_path=state_path,
        terminal_state=final_state,
        terminal_reason=terminal_reason,
        handled_events=handled_events,
        total_elapsed_ms=final_snapshot.elapsed_ms,
        final_budgets=dict(final_snapshot.budgets),
        final_counters=dict(final_snapshot.counters),
    )


def _apply_failure_policy(
    store: StateStore,
    policy: FailurePolicy,
    original_result: TransitionResult,
    event: SemanticEvent,
    roi_logger: ROILogger | None,
) -> TransitionResult:
    """실패 정책을 적용하여 예산을 차감하고 다음 상태를 결정한다."""
    snapshot = store.get_snapshot()
    next_state = original_result.next_state
    terminal_reason = original_result.terminal_reason
    failure_code = policy.failure_code
    
    # 1. 예산 차감 로직
    if policy.retry_budget_key:
        current_budget = store.get_budget(policy.retry_budget_key)
        
        if current_budget > 0:
            # 예산 남음 -> 차감 후 복구 경로로 이동
            store.decrement_budget(policy.retry_budget_key)
            if isinstance(policy.recover_path, State):
                next_state = policy.recover_path
        else:
            # 예산 소진 -> 중단 조건(Stop Condition) 적용
            if policy.stop_condition:
                if "S4" in policy.stop_condition:
                    next_state = State.S4
                elif "SX" in policy.stop_condition:
                    next_state = State.SX
                    terminal_reason = TerminalReason.ABORT
    
    # 2. ROI 기록
    if roi_logger:
        roi_logger.log_failure(
            state=snapshot.current_state,
            event=event.type.value,
            failure_code=failure_code,
            remaining_budgets=store.get_snapshot().budgets,
            stage_elapsed_ms=0, # TODO: Stage 타이머 통합 필요
            total_elapsed_ms=snapshot.elapsed_ms,
            recover_path=next_state.value,
        )

    return TransitionResult(
        next_state=next_state,
        terminal_reason=terminal_reason,
        failure_code=failure_code.value,
        notes=original_result.notes + [f"Failure Policy 적용: {failure_code.value}"],
    )
