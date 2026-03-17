# AI Defense - Frontend/Backend 연동 가이드

본 문서는 AI Defense 시스템 연동을 위해 **Backend팀이 구현해야 할 API**와 **AI팀이 Frontend에 직접 구현할 내용**을 정리한 가이드입니다.

---

## 1. 개요: 트래픽 처리 흐름

1. **Frontend**는 모든 요청 헤더에 `X-Session-Id`를 달아 Backend로 요청을 보냅니다.
2. **Envoy Proxy (Istio)**가 Backend 앞단에서 요청을 가로채어 AI Defense로 판정을 요청합니다.
   * AI Defense는 `X-Session-Id`를 기반으로 리스크를 누적 판정합니다.
3. AI Defense가 **ALLOW(허용)**한 요청만 기존처럼 Backend로 전달됩니다.
   * **DENY(차단)된 악성 요청은 Backend까지 도달하지 않습니다.**
4. 따라서 **Backend팀은 악성 유저 차단 처리를 위해 기존 비즈니스 로직을 전혀 수정할 필요가 없습니다.**

---

## 2. Backend팀 구현 요건

AI Defense 기능 지원을 위해 아래 1개의 신규 API 엔드포인트 구현이 필요합니다.

### 2.1. 텔레메트리 데이터 저장 API

Frontend에서 수집한 유저의 마우스/키보드 행동 데이터(비식별 메타데이터)를 사후 분석용으로 저장하기 위한 엔드포인트입니다.

* **Method:** `POST`
* **Path:** `/api/telemetry/behavior`
* **동작 요구사항:**
  * 전달받은 Request Body를 DB(PostgreSQL JSONB 등) 또는 S3에 저장
  * 비즈니스 로직에 영향을 주지 않도록 **저장 성공 시 200 OK만 반환** (Frontend는 응답을 활용하지 않는 Best-effort 요청임)
  * AI Defense가 실시간 판정에는 체인이 걸리지 않으므로, 비동기로 저장하거나 느려도 서비스에 지장이 없습니다.

* **Request Body Schema (JSON):**

```json
{
  "sessionId": "string",            // 유저 세션 식별자 (예: sess-a1b2c3)
  "correlationId": "string",        // (Optional) 연관된 요청 추적 ID
  "trigger": "string",              // 이벤트 트리거 타입 (예: "CLICK", "CANCEL")
  "datasetId": "string",            // (Optional) 데이터셋 ID
  "features": {                     // AI 판정에 사용되는 핵심 피처 (필수)
    "totalDist": "number",
    "linearDist": "number",
    "linearityRatio": "number",
    "avgVelocity": "number",
    "tremorStdDev": "number",
    "dwellTime": "number",
    "moveEventCount": "number",
    "segmentDurationMs": "number",
    "keyDownCount": "number",
    "keyHoldAvgMs": "number",
    "keyIntervalCv": "number",
    "backspaceCount": "number",
    "pasteDetected": "boolean",
    "imeCompositionCount": "number",
    "timestamp": "number"
  },
  "points": [                       // (Optional) 마우스 Raw 좌표. 용량이 크면 백엔드에서 드롭(무시)하고 features만 저장해도 무방.
    { "x": "number", "y": "number", "t": "number" }
  ]
}
```

---

## 3. 세션 ID 동기화 논의 (회의 안건)

AI Defense가 동일한 유저를 추적하기 위해서는 **Frontend와 AI Defense, Backend가 모두 동일한 식별자를 사용**해야 합니다.

* **AI팀 제안:** Frontend가 사이트 접속 시 UUID를 생성하여 `X-Session-Id` 헤더로 모든 API 요청에 전송.
* **Backend팀 확인 필요 사항:** 기존에 회원/비회원 세션 추적을 위해 사용 중인 쿠키나 헤더(예: JSESSIONID, JWT 등)가 있다면, AI Defense도 해당 값을 식별자로 사용할 수 있도록 합의가 필요합니다.

---

## 4. AI팀 Frontend 구현 예정 사항 (Backend 참고)

아래 항목은 백엔드팀이 아닌 **AI팀에서 직접 Frontend 레포지토리에 코드를 작성**할 내용입니다.

1. **BehavioralSensor 이식:**
   * 유저의 마우스 이벤트, 키보드 타건 간격, 체류 시간 등을 수집하여 위 `features` JSON 구조로 가공하는 로직(`TelemetryLayer`, `sensor.ts` 등) 삽입.
2. **백그라운드 텔레메트리 전송:**
   * 수집된 데이터를 주기적으로(또는 클리 시점 등에) 백엔드의 `/api/telemetry/behavior` 엔드포인트로 `fetch` 전송.
3. **VQA(캡챠) 챌린지 UI 처리:**
   * 만약 Envoy가 AI Defense의 DENY 판정에 따라 `403 Forbidden`과 `x-defense-action=CHALLENGE` 헤더를 내려주면, 이를 캐치하여 백그라운드를 블러 처리하고 공 잡기(VQA) UI를 팝업으로 띄우도록 Axios/Fetch 인터셉터 구현.
4. **전역 세션 헤더 삽입:**
   * 모든 API 요청 헤더에 합의된 식별자(예: `X-Session-Id`)를 자동으로 주입.
