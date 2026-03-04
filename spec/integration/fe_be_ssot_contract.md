# FE/BE SSOT Contract (AI 연동 기준)

본 문서는 FE/BE가 AI(공격/방어)와 맞춰야 하는 최소 계약을 고정합니다.

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

## 4) Telemetry 계약(요약)

- FE 송신: `POST /api/telemetry/behavior`
  - 구현: `platform/frontend/src/components/telemetry/TelemetryLayer.tsx`
- FE feature 산출: `platform/frontend/src/lib/sensor.ts`
- BE 수신/alias 처리: `platform/backend/src/main/java/com/trafficmaster/controller/TelemetryController.java`
- BE 계약 상수: `platform/backend/src/main/java/com/trafficmaster/contract/TelemetryContract.java`

상세 payload는 별도 문서:

- `spec/integration/telemetry_payload_guide.md`

## 5) 방어 헤더 계약(Cloud/FE 공용)

- `x-defense-action`: `challenge | blocked | sandbox`
- `x-defense-tier`: `T0 | T1 | T2 | T3`
- `x-defense-policy-version`: 정책 버전
- `x-block-reason`: 차단 사유
- `x-challenge-type`: 현재 mock은 `quiz`

참조:

- `src/traffic_master_ai/defense/api/policy.py`
- `spec/defense_api/openapi-defense.v1.yaml`

## 6) 변경 승인 체크리스트

1. SSOT 파일 업데이트 여부
2. OpenAPI(있다면) 동기화 여부
3. 공격 E2E(MAP/RECOMMEND) 회귀 결과
4. 텔레메트리 로그(`decision_audit.jsonl`, `trajectory_raw.jsonl`) 정합성
