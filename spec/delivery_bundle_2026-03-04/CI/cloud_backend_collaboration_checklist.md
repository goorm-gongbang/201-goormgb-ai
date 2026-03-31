# Cloud / FE / BE Collaboration Checklist (Latest)

본 문서는 최신 정합화 기준의 전달 체크리스트입니다.

## 0) 고정 정책
- Queue 통과 직후 1회 VQA 필수
- Mid-session tier 상승만으로 추가 challenge 금지
- Runtime LLM/Honey/Sandbox 없음
- Runtime action: `none|challenge|throttle|gate|block`

## 1) Cloud 전달물

### A. AI API + Docker (CICD)
- `CI/openapi-defense.v2.yaml`
- `CI/defense_api_README.md`
- `CI/ai_defense_api_main.py`
- `CI/Dockerfile.ai-defense`

### B. 저장 전략
- `CI/storage_strategy.md`
- `CI/postgres_schema.sql`
- `CI/verification_queries.sql`

## 2) FE/BE 전달물

### A. SSOT/API 계약
- `FE/fe_be_ssot_contract.md` (BE 동일본 반영)
- `FE/vqa_event_defense_scenarios.md` (BE 동일본 반영)

### B. 판단 가이드
- `FE/risk_tier_decision_guide.md` (BE 동일본 반영)
- `FE/telemetry_payload_guide.md` (BE 동일본 반영)

## 3) 실행 전 공통 확인
- Adapter가 `/evaluate` 호출 가능
- Envoy deny 시 `x-defense-action` 헤더 전달됨
- FE가 `challenge/block` UI 처리함
- BE가 challenge issue/verify 및 active gate(428) 처리함

## 4) OpenAPI/Swagger 원칙
- 방어 API의 단일 기준은 `openapi-defense.v2.yaml`
- FE/BE 변경으로 깨지는 경우 같은 PR에서 OpenAPI + 계약 문서 동시 수정
