"""Scenario Loader - Acceptance Scenario Spec v1.0.

디렉토리 내의 모든 시나리오 JSON 파일을 로드하고 유효성을 검증합니다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from traffic_master_ai.attack.a0_poc.scenario_models import Scenario

logger = logging.getLogger(__name__)


class ScenarioLoader:
    """시나리오 로딩 및 유효성 검증을 담당하는 클래스."""

    def __init__(self, directory_path: Path | str) -> None:
        """
        Args:
            directory_path: 시나리오 JSON 파일들이 위치한 디렉토리 경로.
        """
        self.directory_path = Path(directory_path)
        self._scenarios: dict[str, Scenario] = {}

    def load_all(self) -> list[Scenario]:
        """
        디렉토리 내의 모든 *.json 파일을 로드합니다.
        
        Returns:
            list[Scenario]: 성공적으로 로드된 시나리오 객체 리스트.
        """
        if not self.directory_path.exists():
            logger.error(f"Scenario directory not found: {self.directory_path}")
            return []

        loaded_scenarios: list[Scenario] = []
        for file_path in self.directory_path.glob("SCN-*.json"):
            try:
                scenario = self.load_one(file_path)
                loaded_scenarios.append(scenario)
            except Exception as e:
                logger.error(f"Failed to load scenario from {file_path.name}: {e}")

        # ID 중복 체크
        ids = [s.id for s in loaded_scenarios]
        if len(ids) != len(set(ids)):
            logger.warning("Duplicate scenario IDs detected in the directory.")

        self._scenarios = {s.id: s for s in loaded_scenarios}
        return loaded_scenarios

    def load_one(self, file_path: Path | str) -> Scenario:
        """
        단일 시나리오 파일을 로드하고 유효성을 검증합니다.
        
        Args:
            file_path: 시나리오 JSON 파일 경로.
            
        Returns:
            Scenario: 검증된 시나리오 객체.
            
        Raises:
            ValidationError: 스키마 유효성 검사 실패 시.
            FileNotFoundError: 파일이 존재하지 않을 때.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {path}")

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Pydantic 모델을 통한 자동 검증 및 변환
            scenario = Scenario.model_validate(data)
            return scenario
            
        except ValidationError as e:
            # Hard Rule: 상세한 원인을 로그로 남김
            logger.error(f"Schema validation failed for {path.name}:")
            for error in e.errors():
                loc = " -> ".join(map(str, error["loc"]))
                msg = error["msg"]
                logger.error(f"  [{loc}]: {msg}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format in {path.name}: {e}")
            raise

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        """로드된 시나리오 중 특정 ID의 시나리오를 반환합니다."""
        return self._scenarios.get(scenario_id)

    @property
    def loaded_count(self) -> int:
        """현재 로드된 시나리오의 총 개수."""
        return len(self._scenarios)
