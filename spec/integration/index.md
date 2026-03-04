# AI x FE/BE/Cloud Delivery Index (2026-03-04)

이 문서는 타 팀 전달용 산출물의 단일 인덱스입니다.

## 1) 현재 결론

- 현재 단계에서 FE/BE/Cloud 전달 문서 패키지 완성 가능합니다.
- AI Defense API Swagger/OpenAPI + Docker 제공 가능합니다.
- 텔레메트리 페이로드 가이드, VQA 시나리오, 리스크 티어 판단 가이드, 통합 테스트 가이드를 본 폴더 기준으로 제공 가능합니다.
- 주의: `l0_core.yaml`, `l0_defense_policy.yaml`, `defense_ssot.yaml`은 현재 레포 `spec/` 아래에 정식 반영되어 있지 않습니다. 현재 레포의 정식 SSOT는 `spec/ssot/ssot_addendum.yaml`, `spec/ssot/stage*.ssot.yaml`입니다.

## 2) To Cloud

- AI CICD용 API/Swagger + Docker
  - `spec/defense_api/openapi-defense.v1.yaml`
  - `src/traffic_master_ai/defense/api/main.py`
  - `src/traffic_master_ai/defense/api/Dockerfile`
  - `spec/defense_api/README.md`
- 데이터 저장 전략(로그/DB)
  - `spec/defense_api/storage_strategy.md`
  - `spec/defense_api/postgres_schema.sql`
  - `spec/defense_api/verification_queries.sql`
- 텔레메트리 이벤트 페이로드/가이드
  - `spec/integration/telemetry_payload_guide.md`
- VQA 이벤트/방어 시나리오
  - `spec/integration/vqa_event_defense_scenarios.md`

## 3) To FE/BE

- SSOT(API/Selector/ReasonCode) 계약
  - `spec/integration/fe_be_ssot_contract.md`
  - `spec/ssot/ssot_addendum.yaml`
  - `spec/ssot/stage1.ssot.yaml`
  - `spec/ssot/stage2.ssot.yaml`
  - `spec/ssot/stage3.ssot.yaml`
  - `spec/ssot/stage4_5.ssot.yaml`
  - `spec/ssot/stage6.ssot.yaml`
- 사람/봇 리스크 티어 판단 가이드
  - `spec/integration/risk_tier_decision_guide.md`

## 4) 공통

- VQA 이벤트 및 방어 전략 시나리오
  - `spec/integration/vqa_event_defense_scenarios.md`
- 공격 -> 방어 전체 흐름 + LLM 호출 위치 설명
  - `spec/integration/risk_tier_decision_guide.md`
- 재현 가능한 통합 테스트 가이드
  - `spec/integration/cross_team_test_guide.md`

## 5) 전달 순서(권장)

1. Cloud에 `spec/defense_api/*` 먼저 전달
2. FE/BE에 `spec/integration/fe_be_ssot_contract.md` + `spec/integration/telemetry_payload_guide.md` 전달
3. 공통 회의에서 `spec/integration/vqa_event_defense_scenarios.md`와 `spec/integration/risk_tier_decision_guide.md`로 동작 합의
4. 합의 후 `spec/integration/cross_team_test_guide.md`로 같은 절차로 검증
