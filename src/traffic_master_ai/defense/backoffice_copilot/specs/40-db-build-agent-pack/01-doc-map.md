# DB Build 문서 맵

## 0. 최상위 컨텍스트 파일

- [agent.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/agent.md)
  - DB 구축 작업용 최상위 작업 지침서
- [task-execution-log.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md)
  - DB 구축 task별 결과와 다음 task 입력을 누적하는 전용 로그
- [11-final-drift-review-and-handoff.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md)
  - Task 8~17 결과를 축별로 정리한 최종 drift / handoff 문서

## 1. 목표 구조 문서

- [32-storage-architecture.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md)
  - 이번 DB 구축 작업의 최상위 목표 문서
- [33-docs-vs-current-code-gap-analysis.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/33-docs-vs-current-code-gap-analysis.md)
  - 현재 코드와 목표 구조 차이 설명
- [31-observability-merge-strategy.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/31-observability-merge-strategy.md)
  - Grafana / Discord / 외부 소비 전략

## 2. Backoffice 결과 저장 문서

- [00-core-rules.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/00-core-rules.md)
- [01-service-overview.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/01-service-overview/01-service-overview.md)
- [10-post-review-rules.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/10-post-review-rules.md)
- [11-review-output-rules.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/11-review-output-rules.md)
- [21-data-contract.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md)
- [30-ops-and-checks.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/30-ops-and-checks.md)

핵심 포인트:

- 최종 결과 authoritative store는 PostgreSQL 2테이블
- export는 DB 저장 이후 파생 산출물
- Discord / Grafana 실제 연동은 범위 밖

## 3. Runtime observability / policy SSOT

- [defense_observability_ssot.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_observability_ssot.yaml)
- [policy_v1.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/policy_v1.yaml)
- [defense_policy_optimization_ssot.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_policy_optimization_ssot.yaml)
- [l0_defense_policy.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L0/l0_defense_policy.yaml)

핵심 포인트:

- canonical audit는 `decision_audit`
- production warehouse는 `defense_audit_events`
- policy change는 `PostgreSQL control plane -> Redis runtime projection -> ClickHouse effect measurement`

## 4. 현재 코드에서 꼭 봐야 할 파일

### runtime state / audit

- [audit.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/audit.py)
- [main.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/main.py)
- [state.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/state.py)
- [models.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/models.py)
- [etl_worker.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/etl_worker.py)

### decision state / redis / policy

- [runtime.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/api/runtime.py)
- [loader.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/policy/loader.py)
- [keyspace.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/state/keyspace.py)
- [session_state.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/state/session_state.py)
- [block_state.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/state/block_state.py)
- [dedup.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/state/dedup.py)
- [warehouse.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py)
- [rollout.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/optimizer/rollout.py)

### backoffice 결과 저장

- [001_post_review_tables.sql](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/sql/001_post_review_tables.sql)

## 5. 인프라 handover 문서

- [cloud_team_handover_cicd_deployment.md](/Users/shadowmoon/201-goormgb-ai-1/spec/cloud_team_handover_cicd_deployment.md)
- [cloud_team_handover_backend_ssot.md](/Users/shadowmoon/201-goormgb-ai-1/spec/cloud_team_handover_backend_ssot.md)
- [cloud_team_handover_backend_frontend.md](/Users/shadowmoon/201-goormgb-ai-1/spec/cloud_team_handover_backend_frontend.md)

읽는 목적:

- AI팀이 어떤 env / schema / 저장소를 요구해야 하는지 정리
- 클라우드팀이 해야 할 provisioning 범위를 확인

## 6. Agent 작업 기준 문서

- [02-prompt_guardrail_agents.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md)
- [02-implementation-task-breakdown-v2.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md)
- [task-prompts.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-prompts.md)

읽는 목적:

- 최근에 agent에게 어떤 형식으로 일을 맡겼는지 확인
- DB 작업도 같은 방식으로 쪼개서 맡기기 위한 기준 확보

## 7. DB 구축 시작 시 최소 읽기 세트

DB 구축을 바로 시작할 agent는 최소 아래 순서로 읽으면 된다.

1. [agent.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/agent.md)
2. [32-storage-architecture.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md)
3. [33-docs-vs-current-code-gap-analysis.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/33-docs-vs-current-code-gap-analysis.md)
4. [defense_observability_ssot.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_observability_ssot.yaml)
5. [policy_v1.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/policy_v1.yaml)
6. [defense_policy_optimization_ssot.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_policy_optimization_ssot.yaml)
7. [21-data-contract.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md)
8. [audit.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/audit.py)
9. [main.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/main.py)
10. [runtime.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/api/runtime.py)
11. [loader.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/policy/loader.py)
