# Telemetry Payload Guide (FE -> BE -> AI)

## 0) Contract stability
- Fixed:
  - endpoint 목적(`POST /api/telemetry/behavior`)
  - 식별자 의미(`sessionId`, `correlationId`, `requestId`)
  - `features`/`points` 컨테이너 구조
- Tunable:
  - threshold/가중치
  - raw points 전송 on/off
  - feature 승격(Core/Shadow)

## 1) Endpoint
- Method: `POST`
- Path: `/api/telemetry/behavior`

## 2) Request Body
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
  "points": [{"x":100,"y":200,"t":0}],
  "requestId": "req-1"
}
```

## 3) Trigger enum
- `click`
- `cancel`

## 4) Feature 분류

### Core (실시간 판정 후보)
- `totalDist`
- `linearDist`
- `linearityRatio`
- `avgVelocity`
- `tremorStdDev`
- `dwellTime`
- `moveEventCount`
- `segmentDurationMs`
- `keyDownCount`
- `keyHoldAvgMs`
- `keyIntervalCv`

### Shadow (로그 우선)
- `backspaceCount`
- `pasteDetected`
- `imeCompositionCount`

원칙:
- 키보드 요약(`keyDownCount`, `keyHoldAvgMs`, `keyIntervalCv`)은 필수 포함
- feature를 무한정 늘리는 대신, 판정 기여도가 검증된 항목만 Core 유지

## 5) Raw points
- `TM_CAPTURE_RAW_TRAJ=1`일 때만 전송
- 목적: 오프라인 분석/재현

## 6) 저장
- runtime snapshot: in-memory/Redis
- decision audit: `decision_audit.jsonl`
- raw trajectory: `trajectory_raw.jsonl` + object storage

## 7) 운영 주의
- 문자 원문은 수집하지 않고 요약 통계만 전송
- payload key 삭제/의미 변경 금지(추가만 허용)
