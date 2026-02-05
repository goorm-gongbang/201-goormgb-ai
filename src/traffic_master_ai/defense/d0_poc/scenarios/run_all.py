#!/usr/bin/env python3
"""Comprehensive batch verification script for Defense PoC-0.

CI/CD Entry Point - runs all 15 scenarios and returns appropriate exit code.

Usage:
    PYTHONPATH=./src python3 src/traffic_master_ai/defense/d0_poc/scenarios/run_all.py
"""

import sys
from dataclasses import dataclass
from typing import List, Tuple

from ..observability import DecisionLogger
from .data_advanced import get_all_advanced_scenarios
from .data_basic import get_all_basic_scenarios
from .runner import ScenarioRunner
from .schema import Scenario
from .verifier import ScenarioReport, ScenarioVerifier


@dataclass
class ScenarioResult:
    """Result of a single scenario run."""

    scenario_id: str
    title: str
    passed: bool
    total_steps: int
    failed_steps: int
    failure_details: List[Tuple[int, List[str]]]  # (step_seq, mismatches)


def run_scenario_batch(
    scenarios: List[Scenario],
    runner: ScenarioRunner,
    verifier: ScenarioVerifier,
    verbose: bool = True,
) -> List[ScenarioResult]:
    """Run a batch of scenarios and collect results.

    Args:
        scenarios: List of scenarios to run.
        runner: The scenario runner.
        verifier: The scenario verifier.
        verbose: If True, print progress in real-time.

    Returns:
        List of ScenarioResult for each scenario.
    """
    results: List[ScenarioResult] = []

    for scenario in scenarios:
        if verbose:
            print(f"  Running {scenario.id}... ", end="", flush=True)

        step_results = runner.run_scenario(scenario)
        report = verifier.verify_scenario(step_results, scenario.id, scenario.title)

        # Collect failure details
        failure_details: List[Tuple[int, List[str]]] = []
        for r in report.results:
            if not r.passed:
                failure_details.append((r.step_seq, r.mismatches))

        result = ScenarioResult(
            scenario_id=scenario.id,
            title=scenario.title,
            passed=report.passed,
            total_steps=report.total_steps,
            failed_steps=report.failed_steps,
            failure_details=failure_details,
        )
        results.append(result)

        if verbose:
            status = "PASS" if result.passed else "FAIL"
            print(f"[{status}]")

    return results


def print_summary_table(results: List[ScenarioResult]) -> None:
    """Print a formatted summary table of all results.

    Args:
        results: List of scenario results.
    """
    # Calculate column widths
    id_width = max(len("Scenario ID"), max(len(r.scenario_id) for r in results))
    status_width = len("Status")
    title_width = max(len("Title"), max(len(r.title[:40]) for r in results))

    total_width = id_width + status_width + title_width + 10  # padding

    # Header
    print()
    print("=" * total_width)
    print(
        f"{'Scenario ID':<{id_width}} | {'Status':<{status_width}} | {'Title':<{title_width}}"
    )
    print("-" * total_width)

    # Rows
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        title = result.title[:40]
        print(f"{result.scenario_id:<{id_width}} | {status:<{status_width}} | {title}")

    print("-" * total_width)

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    print(f"TOTAL: {total}, PASS: {passed}, FAIL: {failed}")
    print("=" * total_width)


def print_failure_details(results: List[ScenarioResult]) -> None:
    """Print detailed failure information for failed scenarios.

    Args:
        results: List of scenario results.
    """
    failed_results = [r for r in results if not r.passed]
    if not failed_results:
        return

    print("\n" + "=" * 60)
    print("FAILURE DETAILS")
    print("=" * 60)

    for result in failed_results:
        print(f"\n❌ {result.scenario_id}: {result.title}")
        print(f"   Failed {result.failed_steps}/{result.total_steps} steps")
        for step_seq, mismatches in result.failure_details:
            print(f"   Step {step_seq}:")
            for mismatch in mismatches:
                print(f"     - {mismatch}")


def main() -> int:
    """Main entry point for batch verification.

    Returns:
        0 if all scenarios pass, 1 if any fail.
    """
    # Initialize logger for audit trail
    logger = DecisionLogger()
    logger.setup()

    # Initialize components with logger
    runner = ScenarioRunner(logger=logger)
    verifier = ScenarioVerifier()

    # Load all scenarios
    basic_scenarios = get_all_basic_scenarios()
    advanced_scenarios = get_all_advanced_scenarios()
    all_scenarios = basic_scenarios + advanced_scenarios

    # Print header
    print()
    print("=" * 60)
    print("Defense PoC-0 Acceptance Test Suite")
    print("=" * 60)
    print(f"  Basic scenarios:    {len(basic_scenarios)}")
    print(f"  Advanced scenarios: {len(advanced_scenarios)}")
    print(f"  Total scenarios:    {len(all_scenarios)}")
    print("=" * 60)
    print()

    # Run basic scenarios
    print("Running Basic Scenarios (SCN-01 ~ SCN-06):")
    basic_results = run_scenario_batch(basic_scenarios, runner, verifier)

    # Run advanced scenarios
    print("\nRunning Advanced Scenarios (SCN-07 ~ SCN-15):")
    advanced_results = run_scenario_batch(advanced_scenarios, runner, verifier)

    # Close logger after all scenarios
    logger.close()

    # Combine results
    all_results = basic_results + advanced_results

    # Print summary
    print_summary_table(all_results)

    # Print failure details if any
    failed_count = sum(1 for r in all_results if not r.passed)
    if failed_count > 0:
        print_failure_details(all_results)
        print(f"\n⚠️  {failed_count} scenario(s) FAILED. Exit code: 1")
        return 1
    else:
        print(f"\n📝 Audit log written to: {logger.file_path}")
        print("\n🎉 All scenarios PASSED! Exit code: 0")
        return 0


if __name__ == "__main__":
    sys.exit(main())

