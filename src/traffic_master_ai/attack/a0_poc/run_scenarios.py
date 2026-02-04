"""CLI Runner for PoC-0 Acceptance Scenarios.

모든 시나리오(SCN-01~SCN-15)를 로드하여 실행하고 최종 요약 리포트를 출력합니다.
"""

from pathlib import Path
import argparse
import sys

from traffic_master_ai.attack.a0_poc import (
    ScenarioLoader,
    ScenarioRunner,
    ScenarioReport,
    StateStore,
    PolicyProfileLoader,
    PolicySnapshot,
    FailureMatrix,
)

def run_scenarios(scenario_dir: str, policy_file: str) -> bool:
    """모든 시나리오를 실행합니다."""
    loader = ScenarioLoader(scenario_dir)
    scenarios = loader.load_all()
    
    if not scenarios:
        print(f"No scenarios found in {scenario_dir}")
        return False

    # 정책 로더 준비
    policy_loader = PolicyProfileLoader()
    policy_loader.load_from_json(policy_file)
    
    # PoC-0용 Matrix (A0-3 로직 필요시 확장)
    matrix = FailureMatrix() 
    
    runner = ScenarioRunner()
    report = ScenarioReport()

    print(f"\n🔍 Starting Acceptance Tests for {len(scenarios)} scenarios...\n")

    for scn in scenarios:
        try:
            # 시나리오에 정의된 정책 프로파일 로드
            policy_profile = policy_loader.get_profile(scn.policy_profile)
            policy = PolicySnapshot(profile_name=policy_profile.profile_name, rules=policy_profile.to_rules_dict())
            
            store = StateStore() # default S0
            
            # 정책 스냅샷의 N_ 계열 룰을 Store 예산으로 동기화 (SCN-05, 07, 13 등 복구 유도)
            # FailureMatrix가 N_challenge 등의 키를 직접 사용하므로 접두사 유지
            for key, val in policy.rules.items():
                if key.startswith("N_") and isinstance(val, int):
                    store.set_budget(key, val)
            
            result = runner.run(scn, store, policy, failure_matrix=matrix)
            report.add_result(result)
        except Exception as e:
            print(f"❌ Error running scenario {scn.id}: {e}")

    # 리포트 출력
    report.print_summary()
    
    return all(r.is_success for r in report.results)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PoC-0 Acceptance Scenario Runner")
    parser.add_argument("--scenarios", type=str, default="spec/scenarios", help="Path to scenario JSONs")
    parser.add_argument("--policy", type=str, default="spec/policies.json", help="Path to policy JSON file")
    
    args = parser.parse_args()
    
    root = Path(__file__).parent.parent.parent.parent.parent
    scn_path = str(root / args.scenarios)
    pol_path = str(root / args.policy)

    success = run_scenarios(scn_path, pol_path)
    if not success:
        sys.exit(1)
    sys.exit(0)
