# Cloud / FE / BE Collaboration Checklist (2026-03)

기준: AI팀 전달물 관리용 체크리스트

## 1) To Cloud

### A. AI CICD 준비용 Swagger/API + Docker

- 마감: 2026-03-04 16:00
- 상태: DONE
- 전달물:
  - `spec/defense_api/openapi-defense.v1.yaml`
  - `src/traffic_master_ai/defense/api/main.py`
  - `src/traffic_master_ai/defense/api/Dockerfile`
  - `spec/defense_api/README.md`

### B. 데이터 저장 전략(로그/DB, 백업/운영)

- 마감: 2026-03-06
- 상태: DONE
- 전달물:
  - `spec/defense_api/storage_strategy.md`
  - `spec/defense_api/postgres_schema.sql`
  - `spec/defense_api/verification_queries.sql`

핵심 결정:

- Runtime state: Redis
- Audit origin: JSONL append-only + object storage
- Analytics: PostgreSQL(JSONB)

### C. 유저 행동 텔레메트리 이벤트 페이로드 + 가이드

- 마감: 2026-03-05 오후
- 상태: DONE
- 전달물:
  - `spec/integration/telemetry_payload_guide.md`

### D. VQA 이벤트 및 방어 시나리오

- 마감: 2026-03-05 오전
- 상태: DONE
- 전달물:
  - `spec/integration/vqa_event_defense_scenarios.md`

## 2) To BE/FE

### A. SSOT(API Contract) 제공

- 마감: 2026-03-05 오후
- 상태: DONE
- 전달물:
  - `spec/integration/fe_be_ssot_contract.md`
  - `spec/ssot/ssot_addendum.yaml`
  - `spec/ssot/stage1.ssot.yaml`
  - `spec/ssot/stage2.ssot.yaml`
  - `spec/ssot/stage3.ssot.yaml`
  - `spec/ssot/stage4_5.ssot.yaml`
  - `spec/ssot/stage6.ssot.yaml`

### B. Risk Tier 기반 사람/봇 판단 가이드

- 마감: 2026-03-05 오후
- 상태: DONE
- 전달물:
  - `spec/integration/risk_tier_decision_guide.md`

## 3) 공통

### A. 공격 -> 방어 전체 아키텍처/판단/LLM 호출 흐름 가이드

- 상태: DONE
- 전달물:
  - `spec/integration/risk_tier_decision_guide.md`

### B. 타 팀 재현 테스트 가이드

- 상태: DONE
- 전달물:
  - `spec/integration/cross_team_test_guide.md`

## 4) Backend Swagger 제공 원칙

결론: 백엔드도 Swagger/OpenAPI 제공이 맞음.

- 최소:
  - `GET /v3/api-docs`
  - `openapi-backend.v1.json` 또는 `openapi-backend.v1.yaml` 아티팩트
- 가이드:
  - `spec/integration/backend_swagger_enablement.md`
