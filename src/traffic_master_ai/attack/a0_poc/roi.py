"""ROI & Evidence Logging - A0-3-T2 구현.

공격 비용(ROI) 측정 및 실패 증거(Evidence) 기록 담당.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from traffic_master_ai.attack.a0_poc.failure import FailureCode
from traffic_master_ai.attack.a0_poc.states import State

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# EvidenceLog - 개별 실패/의사결정 증거 요약 (v1.0)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class EvidenceLog:
    """실패 발생 시 기록되는 상세 증거 데이터 스키마 v1.0."""

    timestamp: str
    state: str
    event: str
    failure_code: str | None = None
    retry_budget_remaining: dict[str, int] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    elapsed_time_total_ms: int = 0
    elapsed_time_stage_ms: int = 0
    chosen_recover_path: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# ROILogger - ROI 및 Evidence 누적 기록기
# ═══════════════════════════════════════════════════════════════════════════════


class ROILogger:
    """공격 비용을 계산하고 Evidence 로그를 JSONL 파일로 남기는 컴포넌트."""

    def __init__(self, log_path: Path | str | None = None) -> None:
        """
        Args:
            log_path: evidence.jsonl 파일 저장 경로. None이면 파일 기록은 생략.
        """
        self._log_path = Path(log_path) if log_path else None
        
        # 누적 ROI 지표 (v1.0 명세 반영)
        self._total_attempts: int = 0
        self._total_time_ms: int = 0
        self._challenge_count: int = 0
        self._rollback_count: int = 0
        self._api_call_count: int = 0 # Future expansion
        
        # 상세 카운터
        self._counters: dict[str, int] = {
            "seatTakenCount": 0,
            "holdFailCount": 0,
            "sectionEmptyCount": 0,
            "challengeFailCount": 0,
            "timeoutCount": 0,
            "rollbackCount": 0,
        }

    def log_failure(
        self,
        state: State,
        event: str,
        failure_code: FailureCode,
        remaining_budgets: dict[str, int],
        stage_elapsed_ms: int,
        total_elapsed_ms: int,
        recover_path: str,
    ) -> None:
        """실패 이벤트를 기록하고 ROI를 업데이트함."""
        
        # 1. ROI 카운터 업데이트
        self._total_attempts += 1
        self._total_time_ms = total_elapsed_ms
        
        # Failure Code별 카운터 업데이트
        self._update_counters(failure_code, recover_path)

        # 2. Evidence Log 생성
        evidence = EvidenceLog(
            timestamp=datetime.now().isoformat(),
            state=state.value,
            event=event,
            failure_code=failure_code.value,
            retry_budget_remaining=remaining_budgets,
            counters=dict(self._counters),
            elapsed_time_total_ms=total_elapsed_ms,
            elapsed_time_stage_ms=stage_elapsed_ms,
            chosen_recover_path=recover_path,
        )

        # 3. JSONL 기록 (Exception Handling 포함)
        self._write_to_jsonl(evidence)

    def _update_counters(self, failure_code: FailureCode, recover_path: str) -> None:
        """성격에 따른 내부 카운터 및 ROI 지표 증가."""
        if failure_code == FailureCode.F_SEAT_TAKEN:
            self._counters["seatTakenCount"] += 1
        elif failure_code == FailureCode.F_HOLD_FAILED:
            self._counters["holdFailCount"] += 1
        elif failure_code == FailureCode.F_SECTION_EMPTY:
            self._counters["sectionEmptyCount"] += 1
        elif failure_code == FailureCode.F_CHALLENGE_FAILED:
            self._counters["challengeFailCount"] += 1
            self._challenge_count += 1
        elif failure_code in (FailureCode.F_NETWORK_TIMEOUT, FailureCode.F_THROTTLED_TIMEOUT):
            self._counters["timeoutCount"] += 1
            
        # 롤백 처리 감지 (문자열 매칭 또는 특정 로직)
        if "rollback" in recover_path.lower() or ("S4" in recover_path and failure_code in (FailureCode.F_SEAT_TAKEN, FailureCode.F_HOLD_FAILED)):
            self._counters["rollbackCount"] += 1
            self._rollback_count += 1

    def _write_to_jsonl(self, evidence: EvidenceLog) -> None:
        """JSONL 형식으로 파일에 추가."""
        if not self._log_path:
            return

        try:
            if not self._log_path.parent.exists():
                self._log_path.parent.mkdir(parents=True, exist_ok=True)
            
            log_data = json.dumps(asdict(evidence))
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(log_data + "\n")
        except Exception as e:
            # Hard Rule: 파일 쓰기 실패가 전체 엔진 중단으로 이어지지 않도록 함
            logger.error("ROILogger: Failed to write evidence log: %s", e)

    def get_roi_summary(self) -> dict[str, Any]:
        """현재까지의 ROI 요약 데이터 반환."""
        return {
            "total_attempts": self._total_attempts,
            "total_time_ms": self._total_time_ms,
            "challenge_count": self._challenge_count,
            "rollback_count": self._rollback_count,
            "detailed_counters": dict(self._counters),
        }
