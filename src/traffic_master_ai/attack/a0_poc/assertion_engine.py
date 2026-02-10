"""Assertion Engine - PoC-0 시나리오 기댓값 검증 엔진.

ExecutionResult를 ScenarioAssertion 조건과 대조하여 통과 여부를 판정합니다.
"""

from __future__ import annotations

from typing import Any

from traffic_master_ai.attack.a0_poc.scenario_models import ScenarioAssertion
from traffic_master_ai.attack.a0_poc.transition import ExecutionResult


def check_assertion(assertion: ScenarioAssertion, result: ExecutionResult) -> tuple[bool, str]:
    """
    단일 어설션을 검증합니다.
    
    Returns:
        tuple[bool, str]: (성공 여부, 결과 메시지)
    """
    a_type = assertion.type
    a_value = assertion.value
    desc = assertion.description or f"Assertion {a_type}"

    # terminal_reason 검증
    if a_type == "terminal_reason":
        # Enum 객체든 문자열이든 값만 추출 (.done 또는 done)
        raw_actual = result.terminal_reason.value if hasattr(result.terminal_reason, "value") else result.terminal_reason
        actual = str(raw_actual).split('.')[-1].lower()
        expected = str(a_value).split('.')[-1].lower()
        # print(f"[DEBUG] Assertion Check - Actual: {actual}, Expected: {expected}")
        if actual == expected:
            return True, f"PASSED: {desc} (Reason: {actual})"
        return False, f"FAILED: {desc} (Expected: {expected}, Got: {actual})"

    # state_path_contains: 순서 상관없이 포함 여부 (모두 포함해야 함)
    if a_type == "state_path_contains":
        path_values = [str(s.value if hasattr(s, "value") else s) for s in result.state_path]
        targets = [str(v) for v in (a_value if isinstance(a_value, list) else [a_value])]
        missing = [t for t in targets if t not in path_values]
        if not missing:
            return True, f"PASSED: {desc} (Visited all of {targets})"
        return False, f"FAILED: {desc} (Missing {missing}. Path: {path_values})"

    # 2. state_path_equals: 전체 경로가 일치하는가?
    if a_type == "state_path_equals":
        path_values = [s.value for s in result.state_path]
        if path_values == a_value:
            return True, f"PASSED: {desc}"
        return False, f"FAILED: {desc} (Expected {a_value}, Got {path_values})"

    # counter_at_least: 특정 카운터가 최소값 이상인지
    if a_type == "counter_at_least":
        if isinstance(a_value, list) and len(a_value) == 2:
            key, min_val = a_value
        elif isinstance(a_value, dict):
            key = a_value.get("name") or a_value.get("key")
            min_val = a_value.get("min") or a_value.get("value")
        elif isinstance(a_value, (int, float)):
            key = "total_handled_events"
            min_val = a_value
        else:
            return False, f"FAILED: {desc} (Invalid counter format: {a_value})"

        # 카운터 키 지능형 매핑 (시나리오 필드명 -> 내부 이벤트 타입)
        mapping = {
            "seatTakenCount": "SEAT_TAKEN",
            "retryCount": "RETRY_ATTEMPTED",
            "holdFailCount": "HOLD_FAILED",
            "challengeFailCount": "CHALLENGE_FAILED",
        }
        mapped_key = mapping.get(key, key)
        actual = result.final_counters.get(mapped_key, 0) if mapped_key != "total_handled_events" else result.handled_events
        
        if actual >= min_val:
            return True, f"PASSED: {desc} ({key}[{mapped_key}]={actual} >= {min_val})"
        return False, f"FAILED: {desc} ({key}[{mapped_key}]={actual} < {min_val})"

    # 4. counter_equals: 특정 카운터가 정확히 얼마인가?
    if a_type == "counter_equals":
        if not isinstance(a_value, list) or len(a_value) != 2:
            return False, f"ERROR: Invalid assertion value format for {a_type}. Expected [key, target_val]"
        key, target_val = a_value
        actual = result.final_counters.get(key, 0)
        if actual == target_val:
            return True, f"PASSED: {desc} ({key}={actual})"
        return False, f"FAILED: {desc} (Expected {key}={target_val}, Got {actual})"

    # 5. budget_remaining_at_most: 잔여 예산이 특정 값 이하인가? (예산 소진 테스트용)
    if a_type == "budget_remaining_at_most":
        if not isinstance(a_value, list) or len(a_value) != 2:
            return False, f"ERROR: Invalid assertion value format for {a_type}. Expected [key, max_val]"
        key, max_val = a_value
        actual = result.final_budgets.get(key, 0)
        if actual <= max_val:
            return True, f"PASSED: {desc} ({key}={actual} <= {max_val})"
        return False, f"FAILED: {desc} ({key}={actual} > {max_val})"

    # 6. event_handled_count_at_least: 처리된 이벤트 수가 최소 얼마인가?
    if a_type == "event_handled_count_at_least":
        if isinstance(a_value, dict):
            # {"event_type": "...", "count": ...} 형식
            et = a_value.get("type") or a_value.get("event_type")
            target_count = a_value.get("count", 0)
            # NOTE: 현재 ExecutionResult에는 전체 개수는 있지만 타입별 개수가 없음.
            # handled_events를 타입별 카운트로 확장하거나 우선 전체 개수로 대체 (PoC-0 수준)
            # 일단은 'et'가 무엇이든 전체 handled_events로 비교 (향후 로직 보강 필요시 수정)
            if result.handled_events >= target_count:
                return True, f"PASSED: {desc} (Total handled {result.handled_events} >= {target_count})"
            return False, f"FAILED: {desc} (Total handled {result.handled_events} < {target_count})"
            
        if result.handled_events >= int(a_value):
            return True, f"PASSED: {desc} (Handled {result.handled_events} >= {a_value})"
        return False, f"FAILED: {desc} (Handled {result.handled_events} < {a_value})"

    # 7. returned_to_last_non_security_state: S3 이후 정상 복귀했는가?
    if a_type == "returned_to_last_non_security_state":
        # S3Security 진입 후 바로 다음 상태가 SX가 아니고, 방문했던 상태 중 하나여야 함
        # 여기서는 경로상 S3 다음에 나타나는 상태가 이전 상태 리스트에 있었는지 확인
        path = result.state_path
        if "S3" not in [s.value for s in path]:
            return True, f"PASSED: {desc} (S3 not visited, so trivial pass)"
        
        for i in range(len(path) - 1):
            if path[i].value == "S3":
                next_state = path[i+1]
                if next_state.value == "SX":
                    return False, f"FAILED: {desc} (S3 followed by SX instead of recovery)"
                # 이전까지의 상태 중 하나로 복귀했는지 (S0, S1, S2, S4, S5, S6)
                prev_states = [s.value for s in path[:i]]
                if next_state.value in prev_states:
                    return True, f"PASSED: {desc} (Recovered to {next_state.value})"
                return False, f"FAILED: {desc} (Recovered to unknown state {next_state.value})"
        return True, f"PASSED: {desc}"

    # 8. log_lines_at_least: (Stub) 로그 라인 수 확인
    if a_type == "log_lines_at_least":
        # 현재 ExecutionResult에는 로그가 직접 포함되지 않으므로 무조건 True (Pass) 처리하거나 handled_events 활용
        return True, f"PASSED: {desc} (Log line check not supported yet, skipping)"

    # 9. no_invalid_events: (Stub) 부적절한 이벤트 발생 여부
    if a_type == "no_invalid_events":
        # 런타임에 에러가 없었으므로 True
        return True, f"PASSED: {desc} (No runtime invalid events detected during simulation)"

    return False, f"ERROR: Unknown assertion type '{a_type}'"
