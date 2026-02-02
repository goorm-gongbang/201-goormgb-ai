"""Decision Logger - A0-1-T6.

모든 이벤트 처리 결과를 DecisionLog 구조로 기록한다.
실제 파일 write는 하지 않음 (구조 정의만).

Hard Rules:
1. Logger는 "구조 정의"만 한다.
2. 실제 출력/저장은 절대 하지 않는다.
"""

import json
import uuid
from typing import Callable

from traffic_master_ai.attack.a0_poc.events import SemanticEvent
from traffic_master_ai.attack.a0_poc.snapshots import PolicySnapshot, StateSnapshot
from traffic_master_ai.attack.a0_poc.states import State
from traffic_master_ai.attack.a0_poc.transition import DecisionLog, TransitionResult


class DecisionLogger:
    """
    DecisionLog 객체를 생성하는 로거.

    실제 파일 write나 I/O는 하지 않음.
    구조 정의 및 객체 생성만 담당.
    """

    def __init__(
        self,
        timestamp_provider: Callable[[], int] | None = None,
        id_generator: Callable[[], str] | None = None,
    ) -> None:
        """
        DecisionLogger 초기화.

        Args:
            timestamp_provider: 타임스탬프 제공 함수 (테스트 주입용)
            id_generator: decision_id 생성 함수 (테스트 주입용)
        """
        self._timestamp_provider = timestamp_provider or self._default_timestamp
        self._id_generator = id_generator or self._default_id
        self._logs: list[DecisionLog] = []

    @staticmethod
    def _default_timestamp() -> int:
        """기본 타임스탬프: 0 반환 (실제 시간 사용 안함)."""
        return 0

    @staticmethod
    def _default_id() -> str:
        """기본 ID 생성: UUID4."""
        return str(uuid.uuid4())

    def record(
        self,
        current_state: State,
        event: SemanticEvent,
        result: TransitionResult,
        policy: PolicySnapshot,
        snapshot: StateSnapshot,
    ) -> DecisionLog:
        """
        전이 결과를 DecisionLog로 기록한다.

        파일 I/O 없음 - 메모리에만 저장.

        Args:
            current_state: 전이 전 상태
            event: 처리된 이벤트
            result: 전이 결과
            policy: 적용된 정책
            snapshot: 전이 시점 상태 스냅샷

        Returns:
            생성된 DecisionLog 객체
        """
        log = DecisionLog(
            decision_id=self._id_generator(),
            timestamp_ms=self._timestamp_provider(),
            current_state=current_state,
            event=event,
            next_state=result.next_state,
            policy_profile=policy.profile_name,
            budgets=dict(snapshot.budgets),
            counters=dict(snapshot.counters),
            elapsed_ms=snapshot.elapsed_ms,
            notes=list(result.notes),
        )
        self._logs.append(log)
        return log

    def get_logs(self) -> list[DecisionLog]:
        """기록된 모든 DecisionLog 반환 (복사본)."""
        return list(self._logs)

    def clear(self) -> None:
        """로그 초기화."""
        self._logs.clear()

    def count(self) -> int:
        """기록된 로그 수."""
        return len(self._logs)

    def to_jsonl(self) -> str:
        """
        JSONL 형식 문자열 반환.

        실제 파일 write 없음 - 문자열만 생성.
        1 line = 1 decision 구조.
        """
        lines = [json.dumps(log.to_dict(), ensure_ascii=False) for log in self._logs]
        return "\n".join(lines)
