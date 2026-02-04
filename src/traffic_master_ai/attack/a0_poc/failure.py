"""Failure Handling Matrix - A0-3-T1 구현.

Failure Handling Matrix Spec v1.0에 기반한 실패 코드 정의 및 대응 매트릭스.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from traffic_master_ai.attack.a0_poc.event_registry import EventType
from traffic_master_ai.attack.a0_poc.states import State


# ═══════════════════════════════════════════════════════════════════════════════
# FailureCode - 실패 유형 분류 (Taxonomy)
# ═══════════════════════════════════════════════════════════════════════════════


class FailureCode(str, Enum):
    """Failure Handling Matrix v1.0 §3.1에 정의된 실패 코드."""

    # A. 경쟁/도메인 실패
    F_SEAT_TAKEN = "F_SEAT_TAKEN"            # 이선좌
    F_HOLD_FAILED = "F_HOLD_FAILED"          # 홀드 획득 실패
    F_HOLD_EXPIRED = "F_HOLD_EXPIRED"        # 홀드 TTL 만료
    F_SECTION_EMPTY = "F_SECTION_EMPTY"      # 선택 구역 유효 좌석 없음

    # B. 보안/개입 실패
    F_CHALLENGE_FAILED = "F_CHALLENGE_FAILED"  # 챌린지 실패
    F_THROTTLED_TIMEOUT = "F_THROTTLED_TIMEOUT" # 스로틀링/지연 타임아웃
    F_SANDBOX_STUCK = "F_SANDBOX_STUCK"      # 샌드박스 정체

    # C. 세션/기술 실패
    F_SESSION_EXPIRED = "F_SESSION_EXPIRED"  # 세션/토큰 만료
    F_NETWORK_TIMEOUT = "F_NETWORK_TIMEOUT"  # 네트워크 타임아웃
    F_SERVER_ERROR = "F_SERVER_ERROR"        # 5xx
    F_CLIENT_ERROR = "F_CLIENT_ERROR"        # 4xx
    F_UI_INCONSISTENT = "F_UI_INCONSISTENT"  # 상태 불일치

    # D. 거래/종료 실패
    F_PAYMENT_TIMEOUT = "F_PAYMENT_TIMEOUT"  # 결제 시간 초과
    F_TXN_ROLLBACK = "F_TXN_ROLLBACK"        # 거래 단계 무효로 인한 롤백


# ═══════════════════════════════════════════════════════════════════════════════
# FailurePolicy - 실패 대응 정책 데이터 구조
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class FailurePolicy:
    """실패 발생 시 취해야 할 대응 규칙."""

    failure_code: FailureCode
    primary_action: str
    recover_path: State | str  # 특정 State 또는 "Self"
    retry_budget_key: str | None = None  # 차감할 예산 (N_seat, N_hold 등)
    backoff_strategy: str = "none"
    stop_condition: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# FailureMatrix - 실패 처리 매트릭스
# ═══════════════════════════════════════════════════════════════════════════════


class FailureMatrix:
    """이벤트와 상태 조합을 바탕으로 실패 정책(FailurePolicy)을 결정하는 컴포넌트."""

    def __init__(self) -> None:
        # (Current State, EventType) -> FailurePolicy 매핑
        self._matrix: dict[tuple[State, EventType], FailurePolicy] = {}
        self._load_v1_matrix()

    def _load_v1_matrix(self) -> None:
        """Spec v1.0 §3.3 핵심 실패 Top 12 매핑 규칙 주입."""

        # 1. 이선좌 (S5, SEAT_TAKEN)
        self._add_rule(
            State.S5_SEAT, EventType.SEAT_TAKEN,
            FailurePolicy(
                failure_code=FailureCode.F_SEAT_TAKEN,
                primary_action="다른 좌석 후보 선택",
                recover_path=State.S5_SEAT, # "Self" 관점
                retry_budget_key="N_seat",
                backoff_strategy="jitter + short wait",
                stop_condition="N_seat 소진 시 S4",
            )
        )

        # 2. 홀드 실패 (S5, HOLD_FAILED)
        self._add_rule(
            State.S5_SEAT, EventType.HOLD_FAILED,
            FailurePolicy(
                failure_code=FailureCode.F_HOLD_FAILED,
                primary_action="재시도 또는 후보 변경",
                recover_path=State.S5_SEAT,
                retry_budget_key="N_hold",
                backoff_strategy="exp backoff(짧게)",
                stop_condition="N_hold 소진 시 S4",
            )
        )

        # 3. 홀드 만료/결제 단계 롤백 (S6, TXN_ROLLBACK_REQUIRED)
        self._add_rule(
            State.S6_TRANSACTION, EventType.TXN_ROLLBACK_REQUIRED,
            FailurePolicy(
                failure_code=FailureCode.F_HOLD_EXPIRED,
                primary_action="롤백 후 재선택",
                recover_path=State.S5_SEAT,
                retry_budget_key="N_txn_rb",
                stop_condition="반복 시 SX",
            )
        )

        # 4. 구역 매진 (S4, SECTION_EMPTY)
        self._add_rule(
            State.S4_SECTION, EventType.SECTION_EMPTY,
            FailurePolicy(
                failure_code=FailureCode.F_SECTION_EMPTY,
                primary_action="다른 구역 선택",
                recover_path=State.S4_SECTION,
                retry_budget_key="N_section",
                stop_condition="후보 소진 시 SX",
            )
        )

        # 5. 챌린지 실패 (S3, CHALLENGE_FAILED)
        self._add_rule(
            State.S3_SECURITY, EventType.CHALLENGE_FAILED,
            FailurePolicy(
                failure_code=FailureCode.F_CHALLENGE_FAILED,
                primary_action="재시도(템포 완화)",
                recover_path=State.S3_SECURITY,
                retry_budget_key="N_challenge",
                backoff_strategy="cooldown 증가",
                stop_condition="N_challenge 소진 시 SX",
            )
        )

        # 6. 네트워크 타임아웃 (Any, TIMEOUT)
        # Note: 'Any' 처리를 위해 모든 유효 상태 순회
        for state in [s for s in State if s != State.SX_TERMINAL]:
            self._add_rule(
                state, EventType.TIMEOUT,
                FailurePolicy(
                    failure_code=FailureCode.F_NETWORK_TIMEOUT,
                    primary_action="재시도",
                    recover_path="Self",
                    retry_budget_key="N_net",
                    backoff_strategy="exp backoff",
                    stop_condition="timebox 초과 시 SX",
                )
            )

        # 7. 세션 만료 (Any, SESSION_EXPIRED)
        for state in [s for s in State if s != State.SX_TERMINAL]:
            self._add_rule(
                state, EventType.SESSION_EXPIRED,
                FailurePolicy(
                    failure_code=FailureCode.F_SESSION_EXPIRED,
                    primary_action="세션 리셋",
                    recover_path=State.S0_INIT,
                    retry_budget_key="N_session_reset",
                    stop_condition="reset 반복 시 SX",
                )
            )

        # 8. 결제 시간 초과 (S6, PAYMENT_TIMEOUT)
        self._add_rule(
            State.S6_TRANSACTION, EventType.PAYMENT_TIMEOUT,
            FailurePolicy(
                failure_code=FailureCode.F_PAYMENT_TIMEOUT,
                primary_action="종료(실패 결과)",
                recover_path=State.SX_TERMINAL,
                stop_condition="즉시 SX",
            )
        )

        # 9. 샌드박스 정체 (S2, QUEUE_STUCK)
        self._add_rule(
            State.S2_QUEUE_ENTRY, EventType.QUEUE_STUCK,
            FailurePolicy(
                failure_code=FailureCode.F_SANDBOX_STUCK,
                primary_action="리셋/세션 재시작",
                recover_path=State.S1_PRE_ENTRY, # Spec: S1 or SX
                retry_budget_key="N_reset",
                stop_condition="reset 반복 시 SX",
            )
        )

    def _add_rule(self, state: State, event: EventType, policy: FailurePolicy) -> None:
        self._matrix[(state, event)] = policy

    def get_policy(self, state: State, event_type: EventType) -> FailurePolicy | None:
        """현재 상태와 발생한 이벤트에 해당하는 실패 정책 반환."""
        policy = self._matrix.get((state, event_type))
        
        # Recover Path가 "Self"인 경우 현재 상태로 치환
        if policy and policy.recover_path == "Self":
            return FailurePolicy(
                failure_code=policy.failure_code,
                primary_action=policy.primary_action,
                recover_path=state,
                retry_budget_key=policy.retry_budget_key,
                backoff_strategy=policy.backoff_strategy,
                stop_condition=policy.stop_condition,
            )
            
        return policy
