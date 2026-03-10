# FE/BE SSOT Contract (AI 연동 최신)

## 0) Contract boundary
- Fixed:
  - 상태/이벤트/ReasonCode 명칭
  - 헤더 키, API 필드명, selector 의미
- Tunable:
  - 경로 prefix, 포트/호스트, threshold/TTL/timeout

## 1) 핵심 정책 잠금
- Queue 통과 직후 1회 VQA 필수
- Mid-session tier 상승으로 추가 challenge 금지
- Runtime LLM/Honey/Sandbox 없음
- S6 신규 개입 금지(BLOCK만 허용)

## 2) FE Selector 계약
기준 파일:
- `src/traffic_master_ai/attack/a1_mvp/contracts/selectors.py`

주의:
- selector 문자열은 변경 전 공지 + 동시 반영 필수

## 3) BE API/ReasonCode 계약
- reason code 기준: `platform/backend/src/main/java/com/trafficmaster/contract/ReasonCodes.java`
- 경로 기준: `src/traffic_master_ai/attack/a1_mvp/contracts/api.py`

## 4) Defense Header Contract
- `x-defense-action`: `none | challenge | throttle | gate | block`
- `x-defense-actions`: `comma-separated multi actions` (optional)
- `x-defense-tier`: `T0 | T1 | T2 | T3`
- `x-defense-policy-version`: 정책 버전
- `x-challenge-type`: challenge 시
- `x-block-reason`: block 시

상태코드 규칙:
- edge deny challenge: `403` + `x-defense-action=challenge`
- app gating: `428 CHALLENGE_REQUIRED`
- block: `403` + `x-defense-action=block`

multi-action 우선순위:
- `block > challenge > gate > throttle > none`

## 5) Challenge Contract
- Issue/Verify 실행 주체: Backend
- FE는 응답 헤더/코드 기반으로 챌린지 UI 진입
- high-value 요청 중 challenge active면 Backend가 428 반환

## 6) 변경 승인 체크리스트
1. SSOT/계약 문서 업데이트
2. OpenAPI(v2) 동기화
3. FE/BE 통합 테스트 통과
4. decision_audit 로그 정합성 확인
