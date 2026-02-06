#!/usr/bin/env python3
"""Run all Defense PoC-0 acceptance scenarios.

Usage:
    PYTHONPATH=./src python3 src/traffic_master_ai/defense/d0_poc/scenarios/run_all_scenarios.py
"""

from traffic_master_ai.defense.d0_poc.scenarios import ScenarioRunner, ScenarioVerifier
from traffic_master_ai.defense.d0_poc.scenarios.data_advanced import get_all_advanced_scenarios
from traffic_master_ai.defense.d0_poc.scenarios.data_basic import get_all_basic_scenarios


def main() -> int:
    """Run all scenarios and print results.

    Returns:
        0 if all pass, 1 if any fail.
    """
    runner = ScenarioRunner()
    verifier = ScenarioVerifier()

    basic_scenarios = get_all_basic_scenarios()
    advanced_scenarios = get_all_advanced_scenarios()
    all_scenarios = basic_scenarios + advanced_scenarios

    print(f"\n{'='*70}")
    print(f"Defense PoC-0 Acceptance Test Suite")
    print(f"{'='*70}")
    print(f"Basic scenarios: {len(basic_scenarios)}")
    print(f"Advanced scenarios: {len(advanced_scenarios)}")
    print(f"Total scenarios: {len(all_scenarios)}")
    print(f"{'='*70}\n")

    all_passed = True
    failed_scenarios = []

    for scenario in all_scenarios:
        results = runner.run_scenario(scenario)
        report = verifier.verify_scenario(results, scenario.id, scenario.title)

        if report.passed:
            print(f"✅ {scenario.id}: {scenario.title}")
            print(f"   {report.total_steps} steps PASSED")
        else:
            all_passed = False
            failed_scenarios.append(scenario.id)
            print(f"❌ {scenario.id}: {scenario.title}")
            print(f"   {report.passed_steps}/{report.total_steps} passed")
            for r in report.results:
                if not r.passed:
                    print(f"   Step {r.step_seq}: {r.mismatches}")

    print(f"\n{'='*70}")
    if all_passed:
        print(f"🎉 All {len(all_scenarios)} scenarios PASSED!")
        return 0
    else:
        print(f"⚠️  {len(failed_scenarios)}/{len(all_scenarios)} scenarios FAILED:")
        for scn_id in failed_scenarios:
            print(f"   - {scn_id}")
        return 1


if __name__ == "__main__":
    exit(main())
