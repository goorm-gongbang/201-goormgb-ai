# FE/BE SSOT Contract (AI 연동 기준)

본 문서는 FE/BE가 AI(공격/방어)와 맞춰야 하는 최소 계약을 고정합니다.

## 0) Contract boundary

- Fixed:
  - 상태/이벤트/ReasonCode 명칭
  - 헤더 키, API 필드명, selector 의미
  - SSOT 문서 위계
- Tunable:
  - 경로 prefix(`/api` vs `/v1/api`)
  - 포트/호스트
  - threshold/TTL/timeout
  - 챌린지 타입/난이도

운영 가변값은 정책/ENV로 관리하고, 고정 계약 변경 시에는 SSOT + OpenAPI 동시 버전업이 필요합니다.

## 1) SSOT 우선순위

1. `spec/ssot/ssot_addendum.yaml`
2. `spec/ssot/stage1.ssot.yaml`
3. `spec/ssot/stage2.ssot.yaml`
4. `spec/ssot/stage3.ssot.yaml`
5. `spec/ssot/stage4_5.ssot.yaml`
6. `spec/ssot/stage6.ssot.yaml`

변경 규칙:

- selector/API/reasonCode 변경은 PR 전에 공지
- SSOT와 구현을 같은 PR에서 같이 변경
- E2E 회귀 확인 없이 머지 금지

## 2) FE Selector 계약

공격 에이전트의 기준 selector는 아래 파일이 단일 기준입니다.

- `src/traffic_master_ai/attack/a1_mvp/contracts/selectors.py`

필수 selector:

- Pre-entry: `#booking-button:not([disabled])`
- Security: `[data-testid="security-overlay"]`, `[data-testid="security-input"]`, `[data-testid="security-submit"]`, `[data-testid="security-error"]`
- MAP: `button[data-testid^="zone-"][data-remaining]:not([disabled])`, `[data-testid="seat-grid"]`, `button[data-seat-status="AVAILABLE"]`, `#booking-button-map:not([disabled])`, `[data-testid="hold-fail-close"]`, `[data-testid="party-size-select"]`
- Recommend: `[data-testid="rec-auto-select"]:not([disabled])`, `[data-testid="seat-mode-toggle"]`, `[data-testid="party-size-select"]`
- Payment: `[data-testid="agree-terms"]`, `[data-testid="agree-cancel-fee"]`, `#pay-button:not([disabled])`

주의:
- selector 문자열 자체는 고정 계약으로 취급
- UI 구조 변경 시 selector 계약 PR을 먼저 머지한 뒤 FE/공격 에이전트를 같이 반영

## 3) BE API/ReasonCode 계약

공격/방어 공통 reason code:

- `platform/backend/src/main/java/com/trafficmaster/contract/ReasonCodes.java`
  - `BLOCKED`
  - `CHALLENGE_REQUIRED`
  - `MISSING_IDEMPOTENCY_KEY`
  - 그 외 표준 코드들

공통 헤더 상수:

- `platform/backend/src/main/java/com/trafficmaster/contract/TmHeaders.java`

공격 에이전트의 API 경로 기대치:

- `src/traffic_master_ai/attack/a1_mvp/contracts/api.py`
  - `/api/recommendations`
  - `/api/holds`
  - `/api/zones/{zoneId}/seats`
  - URL glob: `/queue`, `/seats?mode=MAP|RECOMMEND`, `/payment`, `/payment/done`

주의:
- 경로 prefix 변경은 허용하되(예: `/v1/api/*`), OpenAPI/SSOT/공격 계약 파일을 같은 PR에서 동기화

## 4) Telemetry 계약(요약)

- FE 송신: `POST /api/telemetry/behavior`
  - 구현: `platform/frontend/src/components/telemetry/TelemetryLayer.tsx`
- FE feature 산출: `platform/frontend/src/lib/sensor.ts`
- BE 수신/alias 처리: `platform/backend/src/main/java/com/trafficmaster/controller/TelemetryController.java`
- BE 계약 상수: `platform/backend/src/main/java/com/trafficmaster/contract/TelemetryContract.java`

상세 payload는 별도 문서:

- `spec/delivery_bundle_2026-03-04/BE/telemetry_payload_guide.md`

## 5) 방어 헤더 계약(Cloud/FE 공용)

- `x-defense-action`: `none | throttle | challenge | honey | sandbox | block`
- `x-defense-actions`: `comma-separated multi actions` (optional)
- `x-defense-tier`: `T0 | T1 | T2 | T3`
- `x-defense-policy-version`: 정책 버전
- `x-block-reason`: 차단 사유
- `x-challenge-type`: 현재 mock은 `quiz`
- 상태코드 해석: edge deny는 `403`, challenge active 중 app gating은 `428 CHALLENGE_REQUIRED`
- multi-action 우선순위: `block > challenge > throttle > honey > sandbox > none`

주의:
- 헤더 "키 이름"은 고정
- 헤더 "값의 정책 기준(언제 challenge/block)"은 운영 가변
- v1 고정 정책: challenge는 Queue 통과 직후 1회에서만 사용하며, 세션 중 tier 상승만으로 추가 challenge를 발동하지 않음

참조:

- `src/traffic_master_ai/defense/api/policy.py`
- `spec/delivery_bundle_2026-03-04/CI/openapi-defense.v1.yaml`

## 6) 변경 승인 체크리스트

1. SSOT 파일 업데이트 여부
2. OpenAPI(있다면) 동기화 여부
3. 공격 E2E(MAP/RECOMMEND) 회귀 결과
4. 텔레메트리 로그(`decision_audit.jsonl`, `trajectory_raw.jsonl`) 정합성
