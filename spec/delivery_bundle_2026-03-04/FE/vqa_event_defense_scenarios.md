# VQA Event and Defense Scenario Guide

본 문서는 VQA(보안 챌린지) 삽입 규칙과 이벤트를 URL/액션 기준으로 정리합니다.

## 0) Contract vs Tunable

- Fixed:
  - 이벤트명(`VQA_CHALLENGE_*`, `VQA_ESCALATION_TRIGGERED`)
  - 필수 식별자 필드(`session_id`, `challenge_id`, `ts_ms`)
  - S6 신규 개입 금지 원칙
- Tunable:
  - 챌린지 삽입 타이밍
  - 최대 시도 횟수/TTL
  - escalation 비율
  - 챌린지 타입/난이도

문서 내 값은 baseline이며 운영 데이터로 조정 가능합니다.

## 1) 상태/화면 기준

- S1 Entry: `/games/{gameId}`
- S2 Queue: `/queue/*`
- S3 Security(VQA overlay): 현재 화면 위 보안 모달 오버레이
- S4 Seat MAP: `/seats?mode=MAP`
- S4R/S5R Recommend: `/seats?mode=RECOMMEND`
- S6 Payment: `/payment?orderId=*`

참조:

- `src/traffic_master_ai/attack/a1_mvp/contracts/api.py`
- `spec/ssot/stage3.ssot.yaml`

## 2) 현재 구현(MVP-0)

현재 실제 동작:

1. Queue 통과 후 챌린지 노출
2. 챌린지 통과 시 좌석 단계 진입
3. 필요 시 테스트 훅으로 챌린지 강제 가능

관련 API:

- `GET /api/security/challenge`
- `POST /api/security/verify`

관련 코드:

- `platform/backend/src/main/java/com/trafficmaster/config/TestModeConfig.java`
- `platform/backend/src/main/java/com/trafficmaster/controller/TelemetryController.java`

## 3) 목표 구현(MVP-1)

### Baseline VQA (baseline policy)

- 삽입 시점: S2 -> S3 (Queue 통과 직후)
- 목적: 기본 인간 검증

### Escalation VQA (baseline policy)

- 삽입 시점: S1/S2/S4/S4R/S5/S5R 중 결제(S6) 이전
- 트리거: Tier 상승 또는 규칙 적중
- 목적: 의심 세션에 추가 검증

S6 규칙:

- 결제 단계에서는 신규 VQA 삽입 금지
- 허용 액션: BLOCK만

## 4) 이벤트 계약(권장)

아래 이벤트를 decision audit 또는 방어 이벤트 스트림에 기록합니다.

- `VQA_CHALLENGE_ISSUED`
  - `session_id`, `trace_id`, `challenge_id`, `challenge_level`, `inserted_at_stage`, `url`, `ts_ms`
- `VQA_CHALLENGE_SUBMITTED`
  - `session_id`, `challenge_id`, `answer_latency_ms`, `attempt`, `ts_ms`
- `VQA_CHALLENGE_PASSED`
  - `session_id`, `challenge_id`, `attempt`, `ts_ms`
- `VQA_CHALLENGE_FAILED`
  - `session_id`, `challenge_id`, `attempt`, `reason_code`, `ts_ms`
- `VQA_ESCALATION_TRIGGERED`
  - `session_id`, `tier_from`, `tier_to`, `trigger_rules`, `ts_ms`

## 5) 방어 액션 매핑

- `DEF_CHALLENGE_FORCED` -> 403 + `x-defense-action: challenge`
- Challenge active 중 high-value 재요청 -> 428 + `CHALLENGE_REQUIRED` (app gating)
- `DEF_BLOCKED` -> 403 + `x-defense-action: blocked`
- `DEF_THROTTLED` -> 200 + `x-defense-action: throttled`
- `DEF_SANDBOXED` -> 200 + `x-defense-action: sandbox`

참조:

- `src/traffic_master_ai/defense/api/policy.py`
- `spec/delivery_bundle_2026-03-04/CI/openapi-defense.v1.yaml`

## 6) 예시 시나리오

### Scenario A: Baseline only

1. 유저가 Queue 통과
2. `VQA_CHALLENGE_ISSUED(inserted_at_stage=S3)`
3. 통과 후 S4로 복귀

### Scenario B: Escalation before hold

1. S4/S5에서 반복 패턴 누적
2. Tier가 T1 -> T2
3. `DEF_CHALLENGE_FORCED`
4. VQA 통과 시 기존 단계로 복귀, 실패 누적 시 차단

### Scenario C: Hard block

1. token mismatch 또는 챌린지 실패 누적 임계 초과
2. `DEF_BLOCKED`, flow -> SX

## 7) 구현/운영 체크

1. `inserted_at_stage`와 `challenge_level` 필드 표준 확정
2. 챌린지 TTL/최대 시도 횟수 확정
3. Baseline/Escalation 비율과 UX 영향 지표 동시 추적
4. TTL/max-attempts/난이도는 ENV 또는 정책 스냅샷으로 외부화
