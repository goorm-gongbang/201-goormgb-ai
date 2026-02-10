"""Scenario Runner - Acceptance Scenario Execution Engine.

로드된 Scenario 객체를 실행하고 결과를 반환합니다.
가상 시간(delay_ms) 시뮬레이션 및 Orchestrator 전이 로직을 포함합니다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from traffic_master_ai.attack.a0_poc.event_registry import EventType
from traffic_master_ai.attack.a0_poc.events import SemanticEvent
from traffic_master_ai.attack.a0_poc.failure import FailureMatrix
from traffic_master_ai.attack.a0_poc.roi import ROILogger
from traffic_master_ai.attack.a0_poc.scenario_models import Scenario, ScenarioAssertion
from traffic_master_ai.attack.a0_poc.scenario_models import Scenario
from traffic_master_ai.attack.a0_poc.snapshots import PolicySnapshot
from traffic_master_ai.attack.a0_poc.states import State, TerminalReason
from traffic_master_ai.attack.a0_poc.store import StateStore
from traffic_master_ai.attack.a0_poc.transition import (
    ExecutionResult,
    TransitionResult,
    transition,
)
from traffic_master_ai.attack.a0_poc.assertion_engine import check_assertion
from traffic_master_ai.attack.a0_poc.scenario_report import ScenarioResult


class ScenarioRunner:
    """수락 테스트 시뮬레이션 전용 실행 엔진."""

    def __init__(self) -> None:
        self.start_time = datetime.now()

    def run(
        self,
        scenario: Scenario,
        store: StateStore,
        policy: PolicySnapshot,
        failure_matrix: FailureMatrix | None = None,
        roi_logger: ROILogger | None = None,
    ) -> ScenarioResult:
    ) -> ExecutionResult:
        """
        시나리오를 실행하여 가상 시간이 반영된 ExecutionResult를 반환합니다.
        
        Orchestrator의 run_events와 로직은 동일하나,
        각 이벤트 처리 직전에 scenario.events[i].delay_ms 만큼 시간을 흐르게 합니다.
        """
        # 1. 초기 상태 설정
        store.set_state(scenario.initial_state)
        state_path: list[State] = [scenario.initial_state]
        handled_events = 0
        last_result: TransitionResult | None = None
        current_virtual_time = self.start_time
        final_terminal_reason: TerminalReason | None = None

        # 2. 시나리오 이벤트 루프
        for s_evt in scenario.events:
            snapshot = store.get_snapshot()
            current_state = snapshot.current_state

            if current_state.is_terminal():
                break

            # A. 가상 시간 시뮬레이션 (Virtual Time Advance)
            store.add_elapsed_ms(s_evt.delay_ms)
            current_virtual_time += timedelta(milliseconds=s_evt.delay_ms)

            # B. 이벤트 변환 (ScenarioEvent -> SemanticEvent)
            event = SemanticEvent(
                event_type=s_evt.event_type,
                stage=State(s_evt.stage) if s_evt.stage and s_evt.stage != "unknown" else None,
                context=s_evt.context,
            )

            # C. 전이 실행 (transition.py 로직 사용)
            result = transition(
                state=current_state,
                event=event,
                policy_snapshot=policy,
                state_snapshot=snapshot,
            )

            # D. 실패 처리 매트릭스 적용 (A0-3 로직 재사용)
            if failure_matrix and not result.is_terminal():
            # D. 실패 처리 매트릭스 적용 (A0-3 로직 재사용 - private이므로 여기서 직접 처리 또는 orchestrator 호출)
            if failure_matrix:
                try:
                    et = EventType(event.event_type)
                    failure_policy = failure_matrix.get_policy(current_state, et)
                    if failure_policy:
                        # NOTE: 원래는 orchestrator._apply_failure_policy를 호출해야 함.
                        # 중복 방지를 위해 여기서는 간단히 로직을 모방하거나 리팩토링이 필요할 수 있음.
                        # 일단은 orchestrator와 동일한 효과를 내도록 작성.
                        result = self._apply_failure_policy_sim(store, failure_policy, result, event, roi_logger)
                except ValueError:
                    pass

            last_result = result

            # E. 상태 업데이트
            next_state = result.next_state
            store.set_state(next_state)

            if next_state.is_security() and current_state.can_be_last_non_security():
                store.set_last_non_security_state(current_state)

            if state_path[-1] != next_state:
                state_path.append(next_state)

            # F. 카운터 누적 (시뮬레이션용)
            store.increment_counter(event.event_type)
            handled_events += 1

            if result.terminal_reason:
                final_terminal_reason = result.terminal_reason

            if next_state.is_terminal() or next_state.value == scenario.accept.final_state:
                # BREAK CONDITION
                final_terminal_reason = result.terminal_reason or final_terminal_reason or TerminalReason.DONE
                last_result = result
            handled_events += 1

            if next_state.is_terminal():
                break

        # 3. 결과 조립
        final_snapshot = store.get_snapshot()
        final_state = final_snapshot.current_state
        
        # 명시적인 이유가 없는 경우 기본값 결정
        if not final_terminal_reason:
            if final_state.is_terminal() or final_state.value == scenario.accept.final_state:
                final_terminal_reason = TerminalReason.DONE
            else:
                final_terminal_reason = TerminalReason.ABORT

        exec_result = ExecutionResult(
            state_path=state_path,
            terminal_state=final_state,
            terminal_reason=final_terminal_reason,
        
        # 터미널 미도달 검증
        if not final_snapshot.current_state.is_terminal():
            raise ValueError(f"Scenario {scenario.id} ended without reaching terminal state.")

        terminal_reason = TerminalReason.DONE
        if last_result and last_result.terminal_reason:
            terminal_reason = last_result.terminal_reason

        return ExecutionResult(
            state_path=state_path,
            terminal_state=final_snapshot.current_state,
            terminal_reason=terminal_reason,
            handled_events=handled_events,
            total_elapsed_ms=final_snapshot.elapsed_ms,
            final_budgets=dict(final_snapshot.budgets),
            final_counters=dict(final_snapshot.counters),
        )

        # 4. 검증 판정 (Assertion Engine 호출)
        assertion_results = []
        is_success = True

        # terminal_reason 검증
        if scenario.accept.terminal_reason:
            passed, msg = check_assertion(
                ScenarioAssertion(type="terminal_reason", value=scenario.accept.terminal_reason), 
                exec_result
            )
            assertion_results.append((passed, msg))
            if not passed:
                is_success = False
            else:
                assertion_results.append((True, f"PASSED: Terminal Reason is '{final_terminal_reason.value}'"))

        # 상세 어설션 검증
        for assertion in scenario.accept.asserts:
            passed, msg = check_assertion(assertion, exec_result)
            assertion_results.append((passed, msg))
            if not passed:
                is_success = False

        return ScenarioResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            is_success=is_success,
            execution_result=exec_result,
            assertion_results=assertion_results,
            total_elapsed_ms=exec_result.total_elapsed_ms,
        )

    def _apply_failure_policy_sim(
        self,
        store: StateStore,
        policy: Any,  # FailurePolicy
        original_result: TransitionResult,
        event: SemanticEvent,
        roi_logger: ROILogger | None,
    ) -> TransitionResult:
        """orchestrator._apply_failure_policy의 시뮬레이션 버전 (로직 복제)."""
        snapshot = store.get_snapshot()
        next_state = original_result.next_state
        terminal_reason = original_result.terminal_reason
        failure_code = policy.failure_code
        
        if policy.retry_budget_key:
            current_budget = store.get_budget(policy.retry_budget_key)
            if current_budget > 0:
                store.decrement_budget(policy.retry_budget_key)
                if isinstance(policy.recover_path, State):
                    next_state = policy.recover_path
            else:
                if policy.stop_condition:
                    if "S4" in policy.stop_condition:
                        next_state = State.S4_SECTION
                    elif "SX" in policy.stop_condition:
                        next_state = State.SX_TERMINAL
                        terminal_reason = TerminalReason.ABORT
        
        if roi_logger:
            roi_logger.log_failure(
                state=snapshot.current_state,
                event=event.event_type,
                failure_code=failure_code,
                remaining_budgets=store.get_snapshot().budgets,
                stage_elapsed_ms=0,
                total_elapsed_ms=snapshot.elapsed_ms,
                recover_path=next_state.value,
            )

        return TransitionResult(
            next_state=next_state,
            terminal_reason=terminal_reason,
            failure_code=failure_code.value,
            notes=original_result.notes + [f"Simulated Failure Policy: {failure_code.value}"],
        )
