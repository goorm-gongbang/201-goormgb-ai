# Delivery Bundle (2026-03-04)

이 폴더는 타 팀 전달용 패키지입니다.

- `CI/`: Cloud/Infra 연동용 API, Docker, 저장전략, 체크리스트
- `FE/`: FE 연동 계약/가이드
- `BE/`: BE 연동 계약/SSOT/API 가이드

문서 충돌 시 우선순위:
1. `DEFENSE_CONSISTENCY_LOCK_V1.md`
2. `CI/openapi-defense.v2.yaml`
3. `FE/*`, `BE/*` 연동 가이드
4. `CONFIGURABILITY_POLICY.md`

## Canonical 8 Documents (최신 기준)

1. `CI/openapi-defense.v2.yaml`
2. `CI/defense_api_README.md`
3. `CI/storage_strategy.md`
4. `CI/cloud_backend_collaboration_checklist.md`
5. `FE/fe_be_ssot_contract.md`
6. `FE/risk_tier_decision_guide.md`
7. `FE/telemetry_payload_guide.md`
8. `FE/vqa_event_defense_scenarios.md`

## Fixed Policy Snapshot

- Queue 통과 직후 1회 고정 VQA
- 세션 진행 중 tier 상승만으로 추가 challenge 금지
- Runtime LLM 없음(사후 배치 분석만 허용)
- Honey/Sandbox 제외
- Runtime action: `none | challenge | throttle | gate | block`
