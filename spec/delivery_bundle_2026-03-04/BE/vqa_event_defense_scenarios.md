# VQA Event and Defense Scenario Guide

본 문서는 VQA(보안 챌린지) 삽입 규칙과 이벤트를 URL/액션 기준으로 정리합니다.

## 0) Contract vs Tunable

- Fixed:
  - 이벤트명(`VQA_CHALLENGE_*`)
  - 필수 식별자 필드(`session_id`, `challenge_id`, `ts_ms`)
  - Queue 통과 직후 1회 고정 VQA
  - 세션 중 추가 VQA 금지
  - S6 신규 개입 금지 원칙
- Tunable:
  - 최대 시도 횟수/TTL
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

### Queue Gate VQA (fixed policy)

- 삽입 시점: S2 -> S3 (Queue 통과 직후)
- 대상: 사람/봇/AI 포함 전원
- 횟수: 세션당 1회 고정
- 목적: 입장 관문 검증(기본 인간 검증)

### Mid-session rule (fixed policy)

- S4/S4R/S5/S5R 진행 중 tier 상승(T1/T2/T3)만으로 추가 VQA를 삽입하지 않음
- 의심 세션 대응은 `throttle/sandbox/honey/block`로 처리

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

## 5) 방어 액션 매핑

- `DEF_CHALLENGE_FORCED` -> 403 + `x-defense-action: challenge` (queue gate 1회에서만 사용)
- Queue gate challenge active 중 high-value 재요청 -> 428 + `CHALLENGE_REQUIRED` (app gating)
- `DEF_THROTTLED` -> 200 + `x-defense-action: throttle`
- `DEF_HONEY_SEAT_INJECTED` -> 200 + `x-defense-action: honey`
- `DEF_SANDBOXED` -> 200 + `x-defense-action: sandbox`
- `DEF_BLOCKED` -> 403 + `x-defense-action: block`
- `DEF_HONEY_TRIGGERED` -> 403 + `x-defense-action: block`, `x-block-reason: honey_triggered`

참조:

- `src/traffic_master_ai/defense/api/policy.py`
- `spec/delivery_bundle_2026-03-04/CI/openapi-defense.v1.yaml`

## 6) 예시 시나리오

### Scenario A: Baseline only

1. 유저가 Queue 통과
2. `VQA_CHALLENGE_ISSUED(inserted_at_stage=S3)`
3. 통과 후 S4로 복귀

### Scenario B: Suspicious but no mid-session VQA

1. S4/S5에서 반복 패턴 누적
2. Tier가 T1 -> T2
3. `DEF_SANDBOXED` 또는 `DEF_THROTTLED`
4. 추가 VQA 없이 기존 흐름 유지(필요 시 차단만 수행)

### Scenario C: Hard block

1. token mismatch 또는 챌린지 실패 누적 임계 초과
2. `DEF_BLOCKED`, flow -> SX

## 7) 구현/운영 체크

1. `inserted_at_stage`와 `challenge_level` 필드 표준 확정
2. 챌린지 TTL/최대 시도 횟수 확정
3. "Queue Gate 1회 정책 준수율"과 UX 영향 지표 동시 추적
4. TTL/max-attempts/난이도는 ENV 또는 정책 스냅샷으로 외부화
