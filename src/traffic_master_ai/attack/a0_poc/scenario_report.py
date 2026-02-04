"""Scenario Report - 시나리오 실행 결과 집계 및 리포팅.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from traffic_master_ai.attack.a0_poc.transition import ExecutionResult


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """단일 시나리오의 전체 실행 결과."""
    scenario_id: str
    scenario_name: str
    is_success: bool
    execution_result: ExecutionResult
    assertion_results: list[tuple[bool, str]]
    total_elapsed_ms: int


class ScenarioReport:
    """여러 시나리오의 결과를 집계하고 리포트를 생성합니다."""

    def __init__(self) -> None:
        self.results: list[ScenarioResult] = []

    def add_result(self, result: ScenarioResult) -> None:
        """결과를 추가합니다."""
        self.results.append(result)

    def print_summary(self) -> None:
        """콘솔에 요약 리포트를 출력합니다."""
        if not self.results:
            print("\n[Scenario Report] No results to report.")
            return

        total = len(self.results)
        passed = sum(1 for r in self.results if r.is_success)
        failed = total - passed

        print("\n" + "="*60)
        print(f"🚀 PoC-0 ACCEPTANCE TEST SUMMARY")
        print("="*60)
        print(f"TOTAL SCENARIOS: {total}")
        print(f"PASSED: {passed}")
        print(f"FAILED: {failed}")
        print(f"PASS RATE: {(passed/total)*100:.1f}%")
        print("-" * 60)

        for r in self.results:
            status = "✅ PASS" if r.is_success else "❌ FAIL"
            print(f"[{r.scenario_id}] {r.scenario_name:<30} | {status} | {r.total_elapsed_ms:>5}ms")
            if not r.is_success:
                for success, msg in r.assertion_results:
                    if not success:
                        print(f"  └─ {msg}")

        print("="*60 + "\n")
