# Cloud / FE / BE Collaboration Checklist (2026-03)

기준: AI팀 전달물 관리용 체크리스트

## 운영 가변값 안내
- 본 체크리스트에서 참조하는 포트/threshold/TTL은 baseline 예시입니다.
- 실제 적용값은 환경변수/정책 스냅샷으로 확정합니다.
- 고정 계약은 OpenAPI/SSOT의 필드명·enum·헤더 키입니다.

## 1) To Cloud

### A. AI CICD 준비용 Swagger/API + Docker

- 마감: 2026-03-04 16:00
- 상태: DONE
- 전달물:
  - `spec/delivery_bundle_2026-03-04/CI/openapi-defense.v1.yaml`
  - `spec/delivery_bundle_2026-03-04/CI/ai_defense_api_main.py`
  - `spec/delivery_bundle_2026-03-04/CI/Dockerfile.ai-defense`
  - `spec/delivery_bundle_2026-03-04/CI/defense_api_README.md`

### B. 데이터 저장 전략(로그/DB, 백업/운영)

- 마감: 2026-03-06
- 상태: DONE
- 전달물:
  - `spec/delivery_bundle_2026-03-04/CI/storage_strategy.md`
  - `spec/delivery_bundle_2026-03-04/CI/postgres_schema.sql`
  - `spec/delivery_bundle_2026-03-04/CI/verification_queries.sql`

핵심 결정:

- Runtime state: Redis
- Audit origin: JSONL append-only + object storage
- Analytics: PostgreSQL(JSONB)

### C. 유저 행동 텔레메트리 이벤트 페이로드 + 가이드

- 마감: 2026-03-05 오후
- 상태: DONE
- 전달물:
  - `spec/delivery_bundle_2026-03-04/FE/telemetry_payload_guide.md`

### D. VQA 이벤트 및 방어 시나리오

- 마감: 2026-03-05 오전
- 상태: DONE
- 전달물:
  - `spec/delivery_bundle_2026-03-04/FE/vqa_event_defense_scenarios.md`

## 2) To BE/FE

### A. SSOT(API Contract) 제공

- 마감: 2026-03-05 오후
- 상태: DONE
- 전달물:
  - `spec/delivery_bundle_2026-03-04/BE/fe_be_ssot_contract.md`
  - `spec/delivery_bundle_2026-03-04/BE/ssot_addendum.yaml`
  - `spec/delivery_bundle_2026-03-04/BE/stage1.ssot.yaml`
  - `spec/delivery_bundle_2026-03-04/BE/stage2.ssot.yaml`
  - `spec/delivery_bundle_2026-03-04/BE/stage3.ssot.yaml`
  - `spec/delivery_bundle_2026-03-04/BE/stage4_5.ssot.yaml`
  - `spec/delivery_bundle_2026-03-04/BE/stage6.ssot.yaml`

### B. Risk Tier 기반 사람/봇 판단 가이드

- 마감: 2026-03-05 오후
- 상태: DONE
- 전달물:
  - `spec/delivery_bundle_2026-03-04/BE/risk_tier_decision_guide.md`

## 3) 공통

### A. 공격 -> 방어 전체 아키텍처/판단/LLM 호출 흐름 가이드

- 상태: DONE
- 전달물:
  - `spec/delivery_bundle_2026-03-04/BE/risk_tier_decision_guide.md`

### B. 타 팀 재현 테스트 가이드

- 상태: DONE
- 전달물:
  - `spec/delivery_bundle_2026-03-04/FE/cross_team_test_guide.md`

## 4) Backend Swagger 제공 원칙

결론: 백엔드도 Swagger/OpenAPI 제공이 맞음.

- 최소:
  - `GET /v3/api-docs`
  - `openapi-backend.v1.json` 또는 `openapi-backend.v1.yaml` 아티팩트
- 가이드:
  - `spec/delivery_bundle_2026-03-04/BE/backend_swagger_enablement.md`
