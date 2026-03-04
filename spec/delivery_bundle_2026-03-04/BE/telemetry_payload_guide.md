# Telemetry Payload Guide (FE -> BE -> AI)

## 0) Contract stability

- Fixed:
  - endpoint 목적(`POST /api/telemetry/behavior`)
  - 공통 식별자 의미(`sessionId`, `correlationId`, `requestId`)
  - `features`/`points` payload 컨테이너 구조
- Tunable:
  - 어떤 feature를 Core로 바로 판정에 쓰는지
  - trigger 종류
  - raw points 전송 on/off
  - feature별 임계값

아래 숫자/키 셋은 baseline이며 운영 데이터로 조정 가능합니다.

## 1) Endpoint

- Method: `POST`
- Path: `/api/telemetry/behavior`
- FE sender: `platform/frontend/src/components/telemetry/TelemetryLayer.tsx`
- BE receiver: `platform/backend/src/main/java/com/trafficmaster/controller/TelemetryController.java`

## 2) Request Body (현재 구현)

```json
{
  "sessionId": "sess-123",
  "correlationId": "corr-1",
  "trigger": "click",
  "datasetId": "human-01",
  "features": {
    "totalDist": 512.3,
    "linearDist": 500.1,
    "linearityRatio": 0.976,
    "avgVelocity": 0.84,
    "tremorStdDev": 1.92,
    "dwellTime": 43.2,
    "moveEventCount": 85,
    "segmentDurationMs": 702.4,
    "keyDownCount": 3,
    "keyHoldAvgMs": 92.7,
    "keyIntervalCv": 0.41,
    "backspaceCount": 1,
    "pasteDetected": false,
    "imeCompositionCount": 1,
    "timestamp": 1772500000000
  },
  "points": [
    {"x": 100, "y": 200, "t": 0},
    {"x": 102, "y": 204, "t": 8}
  ],
  "requestId": "req-1"
}
```

### snake_case alias도 허용

BE는 아래 alias를 허용합니다.

- `session_id`
- `dataset_id`
- `request_id`
- `correlation_id`

## 3) Trigger enum (현재)

- `click`
- `cancel`

확장 정책:
- 신규 trigger 추가는 가능
- 기존 trigger 의미 변경/삭제는 금지(하위호환 이슈)

정의 위치:

- `platform/frontend/src/contracts/telemetry.ts`

## 4) Feature 계약: Core / Shadow

### Core (실시간 판정 후보)

- `totalDist`
- `linearDist`
- `linearityRatio`
- `avgVelocity`
- `tremorStdDev`
- `dwellTime`
- `moveEventCount`
- `segmentDurationMs`
- (추가 예정) `keyHoldAvgMs`는 검증 완료 시 Core 승격 가능

### Shadow (로그 우선, 검증 후 승격)

- `keyDownCount`
- `keyHoldAvgMs`
- `keyIntervalCv`
- `backspaceCount`
- `pasteDetected`
- `imeCompositionCount`

원칙:

- Core는 low-latency runtime 판정 경로에 넣을 수 있는 값
- Shadow는 우선 로그/분석에 쌓고, 오프라인 검증 후 Core로 승격
- 신규 feature key는 Shadow로 먼저 추가 후 승격 여부 결정

## 5) Feature 필드 의미

정의 위치:

- `platform/frontend/src/lib/sensor.ts`

필드(요약):

- `totalDist`: 시작~종료까지 누적 이동거리(px)
- `linearDist`: 시작점~종료점 직선거리(px)
- `linearityRatio`: `linearDist / totalDist` (0~1)
- `avgVelocity`: 평균 속도(px/ms), 이동 구간 기준
- `tremorStdDev`: 직선 대비 흔들림 표준편차
- `dwellTime`: 마지막 이동 이후 클릭까지 정지 시간(ms)
- `moveEventCount`: 세그먼트 내 포인터 move 이벤트 수
- `segmentDurationMs`: 세그먼트 시작부터 클릭(또는 cancel)까지 길이(ms)
- `keyDownCount`: 세그먼트 내 keydown 횟수
- `keyHoldAvgMs`: keydown -> keyup 평균 유지 시간(ms)
- `keyIntervalCv`: 연속 keydown 간격의 변동계수(CV)
- `backspaceCount`: Backspace 입력 횟수
- `pasteDetected`: paste/beforeinput(paste) 감지 여부
- `imeCompositionCount`: IME 조합 시작 이벤트 횟수
- `timestamp`: 클라이언트 생성 시각(ms)

## 6) Raw points 목적

- `points`는 옵션입니다.
- `TM_CAPTURE_RAW_TRAJ=1`일 때만 전송됩니다.
- 목적:
  - 인간 궤적 데이터셋 축적
  - 합성기(attack trajectory synthesizer) 검증
- 저장:
  - `platform/backend/logs/trajectory_raw.jsonl`

## 7) BE 처리 요약

- 최신 feature snapshot은 인메모리 store에 기록
  - `platform/backend/src/main/java/com/trafficmaster/security/BehaviorTelemetryStore.java`
- audit에는 `stage=TELEMETRY`, `eventType=BEHAVIOR`로 기록
  - `platform/backend/logs/decision_audit.jsonl`

## 8) 운영 주의사항

- Telemetry 전송 실패는 UX를 막지 않도록 best-effort 처리됨
- `timestamp`는 참고용, 서버 처리 시각이 기준
- payload 키 추가 시:
  - 기존 키 삭제/의미 변경 금지
  - 신규 키는 optional로 추가
- 키보드 데이터는 \"문자 내용\"이 아니라 요약 통계만 전송(개인정보 최소화)

## 9) 추천 운영값 관리 방식

- threshold/가중치는 문서 하드코딩 대신 정책 파일/ENV로 관리
- release마다 `policy_version`을 올리고, 승격/강등 히스토리를 decision audit에 남김

관련 ENV 예시:
- `TM_CAPTURE_RAW_TRAJ` (`0|1`)
- `TM_TELEMETRY_FEATURE_SCHEMA_VERSION` (예: `v1`, `v1.1`)
