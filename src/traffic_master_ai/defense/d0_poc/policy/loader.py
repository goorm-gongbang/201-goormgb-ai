"""Policy loader for Defense PoC-0 Brain layer.

Loads and manages policy configurations from JSON files.
Provides dataclasses for type-safe policy access.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(slots=True)
class EscalationPolicy:
    """Policy parameters for tier escalation decisions.

    Attributes:
        pattern_threshold: Number of repetitive patterns to trigger escalation.
        challenge_fail_limit: Max challenge failures before T3.
    """

    pattern_threshold: int
    challenge_fail_limit: int


@dataclass(slots=True)
class ThrottlePolicy:
    """Policy parameters for throttle durations.

    Attributes:
        t1_ms: Throttle duration (ms) for T1 tier.
        t2_ms: Throttle duration (ms) for T2 tier.
        streak_penalty_ms: Additional throttle (ms) for S5 streak penalty.
    """

    t1_ms: int
    t2_ms: int
    streak_penalty_ms: int


@dataclass(slots=True)
class SandboxPolicy:
    """Policy parameters for sandbox behavior.

    Attributes:
        max_age_sec: Maximum sandbox duration in seconds before expiry.
    """

    max_age_sec: int


@dataclass(slots=True)
class PolicyProfile:
    """Complete policy profile containing all policy categories.

    Attributes:
        name: Profile identifier (e.g., "default", "strict").
        escalation: Escalation policy parameters.
        throttle: Throttle policy parameters.
        sandbox: Sandbox policy parameters.
    """

    name: str
    escalation: EscalationPolicy
    throttle: ThrottlePolicy
    sandbox: SandboxPolicy


# Default path for policies.json relative to this module
_DEFAULT_POLICIES_PATH = (
    Path(__file__).parent.parent / "spec" / "policies.json"
)


class PolicyLoader:
    """Loads policy profiles from JSON configuration files.

    Provides type-safe access to policy parameters defined in JSON files.
    """

    def __init__(self, json_path: str | None = None) -> None:
        """Initialize the PolicyLoader.

        Args:
            json_path: Path to policies.json file.
                If None, uses the default path:
                src/traffic_master_ai/defense/d0_poc/spec/policies.json
        """
        if json_path is None:
            self._path = _DEFAULT_POLICIES_PATH
        else:
            self._path = Path(json_path)

    def load_profile(self, profile_name: str) -> PolicyProfile:
        """Load a policy profile by name.

        Args:
            profile_name: Name of the profile to load (e.g., "default", "strict").

        Returns:
            PolicyProfile dataclass with all policy parameters.

        Raises:
            ValueError: If the profile doesn't exist, JSON is malformed,
                or required keys are missing.
        """
        try:
            data = self._read_json()
        except FileNotFoundError as e:
            raise ValueError(f"Policy file not found: {self._path}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in policy file: {e}") from e

        profiles = data.get("profiles")
        if profiles is None:
            raise ValueError("Missing 'profiles' key in policy JSON")

        profile_data = profiles.get(profile_name)
        if profile_data is None:
            available = list(profiles.keys())
            raise ValueError(
                f"Profile '{profile_name}' not found. Available: {available}"
            )

        return self._parse_profile(profile_name, profile_data)

    def _read_json(self) -> Dict[str, Any]:
        """Read and parse the JSON file.

        Returns:
            Parsed JSON data as dictionary.

        Raises:
            FileNotFoundError: If file doesn't exist.
            json.JSONDecodeError: If JSON is malformed.
        """
        with open(self._path, encoding="utf-8") as f:
            return json.load(f)

    def _parse_profile(
        self, name: str, data: Dict[str, Any]
    ) -> PolicyProfile:
        """Parse profile data into PolicyProfile dataclass.

        Args:
            name: Profile name.
            data: Raw profile data from JSON.

        Returns:
            PolicyProfile instance.

        Raises:
            ValueError: If required keys are missing.
        """
        try:
            escalation_data = data["escalation"]
            throttle_data = data["throttle"]
            sandbox_data = data["sandbox"]

            escalation = EscalationPolicy(
                pattern_threshold=escalation_data["pattern_threshold"],
                challenge_fail_limit=escalation_data["challenge_fail_limit"],
            )

            throttle = ThrottlePolicy(
                t1_ms=throttle_data["t1_ms"],
                t2_ms=throttle_data["t2_ms"],
                streak_penalty_ms=throttle_data["streak_penalty_ms"],
            )

            sandbox = SandboxPolicy(
                max_age_sec=sandbox_data["max_age_sec"],
            )

            return PolicyProfile(
                name=name,
                escalation=escalation,
                throttle=throttle,
                sandbox=sandbox,
            )

        except KeyError as e:
            raise ValueError(
                f"Missing required key in profile '{name}': {e}"
            ) from e


__all__ = [
    "EscalationPolicy",
    "PolicyLoader",
    "PolicyProfile",
    "SandboxPolicy",
    "ThrottlePolicy",
]
