"""Unit tests for ROI & Evidence Logger - A0-3-T2.

ROILogger 지표 누적 및 JSONL 파일 기록 검증.
"""

import json
from pathlib import Path

import pytest

from traffic_master_ai.attack.a0_poc import (
    FailureCode,
    ROILogger,
    State,
)


class TestROILogger:
    """ROILogger 기능 검증 테스트."""

    @pytest.fixture
    def log_file(self, tmp_path: Path) -> Path:
        return tmp_path / "evidence.jsonl"

    def test_log_failure_updates_summary(self, log_file: Path) -> None:
        """실패 기록 시 요약 데이터(ROI)가 정확히 업데이트되는지 확인."""
        logger = ROILogger(log_file)
        
        # 1. 챌린지 실패 기록
        logger.log_failure(
            state=State.S3,
            event="CHALLENGE_FAILED",
            failure_code=FailureCode.F_CHALLENGE_FAILED,
            remaining_budgets={"N_challenge": 1},
            stage_elapsed_ms=500,
            total_elapsed_ms=1000,
            recover_path="S3",
        )

        # 2. 이선좌 기록
        logger.log_failure(
            state=State.S5,
            event="SEAT_TAKEN",
            failure_code=FailureCode.F_SEAT_TAKEN,
            remaining_budgets={"N_seat": 5},
            stage_elapsed_ms=200,
            total_elapsed_ms=2000,
            recover_path="S5",
        )

        summary = logger.get_roi_summary()
        assert summary["total_attempts"] == 2
        assert summary["total_time_ms"] == 2000
        assert summary["challenge_count"] == 1
        assert summary["detailed_counters"]["seatTakenCount"] == 1
        assert summary["detailed_counters"]["challengeFailCount"] == 1

    def test_jsonl_output_format(self, log_file: Path) -> None:
        """로그 파일이 유효한 JSONL 형식으로 작성되는지 확인."""
        logger = ROILogger(log_file)
        
        logger.log_failure(
            state=State.S4,
            event="SECTION_EMPTY",
            failure_code=FailureCode.F_SECTION_EMPTY,
            remaining_budgets={"N_section": 3},
            stage_elapsed_ms=100,
            total_elapsed_ms=500,
            recover_path="S4",
        )

        assert log_file.exists()
        lines = log_file.read_text().splitlines()
        assert len(lines) == 1
        
        log_entry = json.loads(lines[0])
        assert log_entry["failure_code"] == "F_SECTION_EMPTY"
        assert log_entry["state"] == "S4"
        assert "timestamp" in log_entry

    def test_rollback_detection(self, log_file: Path) -> None:
        """복구 경로에 따른 롤백 카운트 증가 확인."""
        logger = ROILogger(log_file)
        
        # S4로 롤백되는 상황 시뮬레이션
        logger.log_failure(
            state=State.S5,
            event="SEAT_TAKEN",
            failure_code=FailureCode.F_SEAT_TAKEN,
            remaining_budgets={"N_seat": 0},
            stage_elapsed_ms=1000,
            total_elapsed_ms=10000,
            recover_path="rollback_to_S4",
        )

        summary = logger.get_roi_summary()
        assert summary["rollback_count"] == 1
        assert summary["detailed_counters"]["rollbackCount"] == 1

    def test_file_writing_exception_safety(self) -> None:
        """파일 경로가 잘못되어도 예외가 발생하지 않고 조용히 넘어가야 함."""
        invalid_logger = ROILogger("/non_existent_path_that_should_fail/evidence.jsonl")
        
        # 예외 없이 실행되어야 함
        invalid_logger.log_failure(
            state=State.S0,
            event="TEST",
            failure_code=FailureCode.F_CLIENT_ERROR,
            remaining_budgets={},
            stage_elapsed_ms=0,
            total_elapsed_ms=0,
            recover_path="SX",
        )
        assert True
