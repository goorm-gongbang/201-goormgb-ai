"""Unit tests for Policy Profile Loader - A0-2-T3.

PolicyProfile, PolicyProfileLoader 검증.
"""

from pathlib import Path
from typing import Any

import pytest

from traffic_master_ai.attack.a0_poc import (
    InvalidProfileSchemaError,
    PolicyProfile,
    PolicyProfileLoader,
    ProfileNotFoundError,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_profiles_dict() -> dict[str, dict[str, Any]]:
    """테스트용 프로파일 딕셔너리."""
    return {
        "default": {
            "N_challenge": 2,
            "N_section": 4,
            "N_seat": 6,
            "N_hold": 3,
            "seat_taken_threshold": 4,
            "S1_timeout_ms": 30000,
            "S6_timeout_ms": 120000,
            "payment_timeout_policy": "abort",
        },
        "strict": {
            "N_challenge": 1,
            "N_section": 2,
            "payment_timeout_policy": "rollback",
        },
    }


@pytest.fixture
def loader() -> PolicyProfileLoader:
    """빈 로더 인스턴스."""
    return PolicyProfileLoader()


@pytest.fixture
def loaded_loader(
    loader: PolicyProfileLoader, 
    sample_profiles_dict: dict[str, dict[str, Any]],
) -> PolicyProfileLoader:
    """프로파일이 로드된 로더."""
    loader.load_from_dict(sample_profiles_dict)
    return loader


@pytest.fixture
def policies_json_path() -> Path:
    """spec/policies.json 경로."""
    return Path(__file__).parent.parent.parent / "spec" / "policies.json"


# ═══════════════════════════════════════════════════════════════════════════════
# PolicyProfile 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestPolicyProfile:
    """PolicyProfile 테스트."""

    def test_create_profile(self) -> None:
        """프로파일 생성 테스트."""
        profile = PolicyProfile(
            profile_name="test",
            budgets={"N_challenge": 2},
            timeboxes={"S1_timeout_ms": 30000},
            policies={"payment_timeout_policy": "abort"},
        )
        assert profile.profile_name == "test"
        assert profile.budgets == {"N_challenge": 2}
        assert profile.timeboxes == {"S1_timeout_ms": 30000}
        assert profile.policies == {"payment_timeout_policy": "abort"}

    def test_get_budget(self) -> None:
        """예산 조회 테스트."""
        profile = PolicyProfile(
            profile_name="test",
            budgets={"N_challenge": 2, "N_section": 4},
        )
        assert profile.get_budget("N_challenge") == 2
        assert profile.get_budget("N_section") == 4
        assert profile.get_budget("N_seat", 0) == 0  # default

    def test_get_timebox(self) -> None:
        """타임박스 조회 테스트."""
        profile = PolicyProfile(
            profile_name="test",
            timeboxes={"S1_timeout_ms": 30000},
        )
        assert profile.get_timebox("S1_timeout_ms") == 30000
        assert profile.get_timebox("S2_timeout_ms", 60000) == 60000

    def test_get_policy(self) -> None:
        """정책 조회 테스트."""
        profile = PolicyProfile(
            profile_name="test",
            policies={"payment_timeout_policy": "abort"},
        )
        assert profile.get_policy("payment_timeout_policy") == "abort"
        assert profile.get_policy("unknown", "default") == "default"

    def test_to_rules_dict(self) -> None:
        """rules dict 변환 테스트."""
        profile = PolicyProfile(
            profile_name="test",
            budgets={"N_challenge": 2},
            timeboxes={"S1_timeout_ms": 30000},
            policies={"payment_timeout_policy": "abort"},
        )
        rules = profile.to_rules_dict()
        assert rules["N_challenge"] == 2
        assert rules["S1_timeout_ms"] == 30000
        assert rules["payment_timeout_policy"] == "abort"

    def test_profile_is_frozen(self) -> None:
        """프로파일이 immutable인지 확인."""
        profile = PolicyProfile(profile_name="test")
        with pytest.raises(AttributeError):
            profile.profile_name = "other"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════════
# PolicyProfileLoader 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestPolicyProfileLoader:
    """PolicyProfileLoader 테스트."""

    def test_initial_state(self, loader: PolicyProfileLoader) -> None:
        """초기 상태 테스트."""
        assert loader.is_loaded is False
        assert loader.list_profiles() == []

    def test_load_from_dict(
        self,
        loader: PolicyProfileLoader,
        sample_profiles_dict: dict[str, dict[str, Any]],
    ) -> None:
        """딕셔너리에서 로딩 테스트."""
        profiles = loader.load_from_dict(sample_profiles_dict)
        assert loader.is_loaded is True
        assert "default" in profiles
        assert "strict" in profiles
        assert len(profiles) == 2

    def test_get_profile(self, loaded_loader: PolicyProfileLoader) -> None:
        """프로파일 조회 테스트."""
        profile = loaded_loader.get_profile("default")
        assert profile.profile_name == "default"
        assert profile.get_budget("N_challenge") == 2

    def test_get_default_profile(self, loaded_loader: PolicyProfileLoader) -> None:
        """기본 프로파일 조회 테스트."""
        profile = loaded_loader.get_default_profile()
        assert profile.profile_name == "default"

    def test_get_profile_not_found(self, loaded_loader: PolicyProfileLoader) -> None:
        """존재하지 않는 프로파일 조회 시 에러."""
        with pytest.raises(ProfileNotFoundError) as exc_info:
            loaded_loader.get_profile("nonexistent")
        assert exc_info.value.profile_name == "nonexistent"

    def test_list_profiles(self, loaded_loader: PolicyProfileLoader) -> None:
        """프로파일 목록 조회 테스트."""
        profiles = loaded_loader.list_profiles()
        assert "default" in profiles
        assert "strict" in profiles

    def test_has_profile(self, loaded_loader: PolicyProfileLoader) -> None:
        """프로파일 존재 여부 확인 테스트."""
        assert loaded_loader.has_profile("default") is True
        assert loaded_loader.has_profile("strict") is True
        assert loaded_loader.has_profile("nonexistent") is False

    def test_default_profile_required(self, loader: PolicyProfileLoader) -> None:
        """default 프로파일 필수 검증."""
        with pytest.raises(InvalidProfileSchemaError):
            loader.load_from_dict({"other": {"N_challenge": 1}})


class TestPolicyProfileLoaderFromJson:
    """JSON 파일 로딩 테스트."""

    def test_load_from_json(
        self, 
        loader: PolicyProfileLoader, 
        policies_json_path: Path,
    ) -> None:
        """JSON 파일 로딩 테스트."""
        if not policies_json_path.exists():
            pytest.skip(f"spec/policies.json not found at {policies_json_path}")
        
        profiles = loader.load_from_json(policies_json_path)
        assert "default" in profiles
        assert loader.is_loaded is True

    def test_load_six_default_profiles(
        self,
        loader: PolicyProfileLoader,
        policies_json_path: Path,
    ) -> None:
        """6개 기본 프로파일 로딩 테스트."""
        if not policies_json_path.exists():
            pytest.skip(f"spec/policies.json not found at {policies_json_path}")

        loader.load_from_json(policies_json_path)
        expected_profiles = [
            "default",
            "challenge_strict",
            "txn_timeout_rollback",
            "section_strict",
            "seat_threshold_rollback",
            "hold_strict_rollback",
        ]
        for name in expected_profiles:
            assert loader.has_profile(name), f"Missing profile: {name}"

    def test_file_not_found(self, loader: PolicyProfileLoader) -> None:
        """존재하지 않는 파일 로딩 시 에러."""
        with pytest.raises(FileNotFoundError):
            loader.load_from_json(Path("/nonexistent/path/policies.json"))


# ═══════════════════════════════════════════════════════════════════════════════
# Error 클래스 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestErrors:
    """에러 클래스 테스트."""

    def test_profile_not_found_error(self) -> None:
        """ProfileNotFoundError 테스트."""
        error = ProfileNotFoundError("test_profile")
        assert error.profile_name == "test_profile"
        assert "test_profile" in str(error)

    def test_invalid_profile_schema_error(self) -> None:
        """InvalidProfileSchemaError 테스트."""
        error = InvalidProfileSchemaError("Invalid format", profile_name="test")
        assert error.profile_name == "test"
        assert "Invalid format" in str(error)
