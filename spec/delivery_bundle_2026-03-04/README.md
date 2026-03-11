# Delivery Bundle (2026-03-04)

이 폴더는 타 팀 전달용 패키지입니다.

- `CI/`: Cloud/Infra 연동용 API, Docker, 저장전략, 체크리스트
- `BE/`: FE/BE 공통 연동 계약/가이드 (FE 문서 통합 완료)

문서 충돌 시 우선순위:
1. `DEFENSE_CONSISTENCY_LOCK_V1.md`
2. `CI/openapi-defense.v2.yaml`
3. `BE/*` 연동 가이드
4. `CONFIGURABILITY_POLICY.md`

## Canonical Documents (최신 기준)

### CI (Cloud/Infra)
1. `CI/openapi-defense.v2.yaml` — OpenAPI 단일 기준 스펙
2. `CI/defense_api_README.md` — Defense API 실행 가이드
3. `CI/Dockerfile.ai-defense` — AI Defense 컨테이너 이미지
4. `CI/storage_strategy.md` — 저장소 전략 (Redis/JSONL/PostgreSQL)
5. `CI/cloud_backend_collaboration_checklist.md` — 타 팀 협업 체크리스트
6. `CI/postgres_schema.sql` — PostgreSQL 스키마
7. `CI/verification_queries.sql` — 검증 쿼리

### BE (FE/BE 공통)
1. `BE/fe_be_ssot_contract.md` — FE/BE SSOT 계약
2. `BE/risk_tier_decision_guide.md` — 위험등급 판단 가이드
3. `BE/telemetry_payload_guide.md` — 텔레메트리 페이로드 가이드
4. `BE/vqa_event_defense_scenarios.md` — VQA/이벤트/방어 시나리오
5. `BE/cross_team_test_guide.md` — 교차 팀 테스트 가이드
6. `BE/backend_swagger_enablement.md` — Backend Swagger 설정
7. `BE/attack_selector_contract.py` — 공격 선택자 계약 (Python)
8. `BE/ssot_addendum.yaml` — SSOT 부록
9. `BE/stage1~6.ssot.yaml` — 단계별 SSOT 정의

### Bundle Root
1. `DEFENSE_CONSISTENCY_LOCK_V1.md` — 런타임 계약 잠금 (최우선 참조)
2. `CONFIGURABILITY_POLICY.md` — 고정/가변 정책 정의

## Fixed Policy Snapshot

- Queue 통과 직후 1회 고정 VQA
- 세션 진행 중 tier 상승만으로 추가 challenge 금지
- Runtime LLM 없음(사후 배치 분석만 허용)
- Honey/Sandbox 제외
- Runtime action: `none | challenge | throttle | gate | block`
