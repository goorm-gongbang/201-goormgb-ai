"""Policy Profile Loader - A0-2-T3 구현.

Policy Profile을 JSON 파일에서 로딩하고 시나리오별 전환을 지원.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 에러 클래스
# ═══════════════════════════════════════════════════════════════════════════════


class ProfileNotFoundError(Exception):
    """요청한 profile_name이 존재하지 않을 때 발생."""

    def __init__(self, profile_name: str) -> None:
        self.profile_name = profile_name
        super().__init__(f"Profile not found: {profile_name}")


class InvalidProfileSchemaError(Exception):
    """Profile JSON 스키마가 유효하지 않을 때 발생."""

    def __init__(self, message: str, profile_name: str | None = None) -> None:
        self.profile_name = profile_name
        super().__init__(f"Invalid profile schema: {message}")


# ═══════════════════════════════════════════════════════════════════════════════
# PolicyProfile dataclass
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class PolicyProfile:
    """Policy Profile 정의.
    
    시나리오별 정책 설정을 담는 immutable 데이터 클래스.
    
    Attributes:
        profile_name: 프로파일 식별자
        budgets: 리소스 예산 (retry, security, section, seat, hold 등)
        timeboxes: 스테이지별 제한시간 (ms)
        policies: 정책 규칙 (payment_timeout_policy 등)
    
    Example:
        >>> profile = PolicyProfile(
        ...     profile_name="default",
        ...     budgets={"N_challenge": 2, "N_section": 4},
        ...     timeboxes={"S1": 30000, "S2": 60000},
        ...     policies={"payment_timeout_policy": "abort"},
        ... )
    """

    profile_name: str
    budgets: dict[str, int] = field(default_factory=dict)
    timeboxes: dict[str, int] = field(default_factory=dict)
    policies: dict[str, str] = field(default_factory=dict)

    def get_budget(self, key: str, default: int = 0) -> int:
        """예산 값 조회."""
        return self.budgets.get(key, default)

    def get_timebox(self, key: str, default: int = 0) -> int:
        """타임박스 값 조회 (ms)."""
        return self.timeboxes.get(key, default)

    def get_policy(self, key: str, default: str = "") -> str:
        """정책 규칙 조회."""
        return self.policies.get(key, default)

    def to_rules_dict(self) -> dict[str, Any]:
        """PolicySnapshot.rules와 호환되는 dict 반환."""
        rules: dict[str, Any] = {}
        rules.update(self.budgets)
        rules.update(self.timeboxes)
        rules.update(self.policies)
        return rules


# ═══════════════════════════════════════════════════════════════════════════════
# PolicyProfileLoader 클래스
# ═══════════════════════════════════════════════════════════════════════════════


# 기본 프로파일 키
DEFAULT_PROFILE_NAME = "default"

# 예산 관련 키 목록 (budgets에 들어갈 항목)
_BUDGET_KEYS = frozenset({
    "N_challenge",
    "N_section", 
    "N_seat",
    "N_hold",
    "N_txn_rb",
    "seat_taken_threshold",
    "max_retries",
})

# 타임박스 관련 키 목록
_TIMEBOX_KEYS = frozenset({
    "S0_timeout_ms",
    "S1_timeout_ms",
    "S2_timeout_ms",
    "S3_timeout_ms",
    "S4_timeout_ms",
    "S5_timeout_ms",
    "S6_timeout_ms",
    "global_timeout_ms",
})


class PolicyProfileLoader:
    """Policy Profile 로더.
    
    JSON 파일에서 Policy Profile들을 로딩하고 관리.
    
    Example:
        >>> loader = PolicyProfileLoader()
        >>> loader.load_from_json(Path("spec/policies.json"))
        >>> profile = loader.get_profile("default")
        >>> profile.get_budget("N_challenge")
        2
    """

    def __init__(self) -> None:
        self._profiles: dict[str, PolicyProfile] = {}
        self._loaded_path: Path | None = None

    @property
    def is_loaded(self) -> bool:
        """프로파일이 로드되었는지 확인."""
        return len(self._profiles) > 0

    def load_from_json(self, path: Path | str) -> dict[str, PolicyProfile]:
        """JSON 파일에서 프로파일들을 로딩.
        
        Args:
            path: JSON 파일 경로
            
        Returns:
            로딩된 프로파일 딕셔너리
            
        Raises:
            FileNotFoundError: 파일이 없을 때
            InvalidProfileSchemaError: JSON 스키마가 유효하지 않을 때
        """
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(f"Policy file not found: {path}")

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise InvalidProfileSchemaError(f"Invalid JSON: {e}") from e

        if not isinstance(data, dict):
            raise InvalidProfileSchemaError("Root must be an object")

        self._profiles = {}
        for name, profile_data in data.items():
            self._profiles[name] = self._parse_profile(name, profile_data)

        # default 프로파일 필수 검증
        if DEFAULT_PROFILE_NAME not in self._profiles:
            raise InvalidProfileSchemaError(
                f"'{DEFAULT_PROFILE_NAME}' profile is required"
            )

        self._loaded_path = path
        logger.info(
            "Loaded %d profiles from %s: %s",
            len(self._profiles),
            path,
            list(self._profiles.keys()),
        )

        return dict(self._profiles)

    def load_from_dict(self, data: dict[str, dict[str, Any]]) -> dict[str, PolicyProfile]:
        """딕셔너리에서 프로파일들을 로딩.
        
        테스트나 프로그래매틱 로딩에 유용.
        
        Args:
            data: 프로파일 딕셔너리
            
        Returns:
            로딩된 프로파일 딕셔너리
        """
        self._profiles = {}
        for name, profile_data in data.items():
            self._profiles[name] = self._parse_profile(name, profile_data)

        if DEFAULT_PROFILE_NAME not in self._profiles:
            raise InvalidProfileSchemaError(
                f"'{DEFAULT_PROFILE_NAME}' profile is required"
            )

        return dict(self._profiles)

    def _parse_profile(self, name: str, data: dict[str, Any]) -> PolicyProfile:
        """개별 프로파일 데이터 파싱.
        
        Args:
            name: 프로파일 이름
            data: 프로파일 데이터 딕셔너리
            
        Returns:
            PolicyProfile 인스턴스
        """
        if not isinstance(data, dict):
            raise InvalidProfileSchemaError(
                f"Profile data must be an object",
                profile_name=name,
            )

        budgets: dict[str, int] = {}
        timeboxes: dict[str, int] = {}
        policies: dict[str, str] = {}

        for key, value in data.items():
            if key in _BUDGET_KEYS:
                if not isinstance(value, int):
                    raise InvalidProfileSchemaError(
                        f"Budget '{key}' must be an integer",
                        profile_name=name,
                    )
                budgets[key] = value
            elif key in _TIMEBOX_KEYS:
                if not isinstance(value, int):
                    raise InvalidProfileSchemaError(
                        f"Timebox '{key}' must be an integer",
                        profile_name=name,
                    )
                timeboxes[key] = value
            else:
                # 나머지는 정책으로 분류
                policies[key] = str(value)

        return PolicyProfile(
            profile_name=name,
            budgets=budgets,
            timeboxes=timeboxes,
            policies=policies,
        )

    def get_profile(self, name: str) -> PolicyProfile:
        """이름으로 프로파일 조회.
        
        Args:
            name: 프로파일 이름
            
        Returns:
            PolicyProfile
            
        Raises:
            ProfileNotFoundError: 프로파일이 없을 때
        """
        if name not in self._profiles:
            raise ProfileNotFoundError(name)
        return self._profiles[name]

    def get_default_profile(self) -> PolicyProfile:
        """기본 프로파일 조회."""
        return self.get_profile(DEFAULT_PROFILE_NAME)

    def list_profiles(self) -> list[str]:
        """로딩된 프로파일 이름 목록."""
        return list(self._profiles.keys())

    def has_profile(self, name: str) -> bool:
        """프로파일 존재 여부 확인."""
        return name in self._profiles
