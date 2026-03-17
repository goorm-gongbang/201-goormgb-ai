# Traffic Master: Backend API & AI Defense Integration Guide

## 1. 문서 개요
본 문서는 백엔드 팀이 Traffic Master(예매 시스템)의 Core API를 구현함에 있어, 앞단의 **AI Defense Proxy (Istio/Envoy)**와 원활하게 연동되기 위해 준수해야 할 **API 엔드포인트, Request 스키마, 그리고 특수 HTTP Header 규약**을 정의합니다.

또한, 오프라인 AI 분석 결과 발견된 매크로 어뷰저들을 백엔드에서 사후 제재하기 위한 **Sanctions API** 연동 스펙도 함께 포함하고 있습니다.

---

## 2. 실시간 방어망 개입 지점 (Real-time Intervention)

> **핵심 동작 원리**
> 아래 명시된 Core API가 호출될 때마다, 백엔드 서버에 도달하기 직전 앞단의 Envoy(프록시)가 트래픽을 가로채어 실시간 방어 판정(`ALLOW` / `BLOCK` / `THROTTLE`)을 수행합니다. 
> 백엔드 서버에는 이미 검증을 무사히 통과한 안전한 트래픽과, 제어된 속도(`THROTTLE`)의 인입만 도달하게 됩니다.

### 티켓 예매 흐름 상태(Flow State) 및 개입 정책
각 API 호출은 유저의 특정 여정(State)에 대응하며, 상태별로 방어망의 제어 강도가 다르게 적용됩니다.

| 상태 | 유저 여정 단계 | 연관 API | 설명 및 방어망 개입 정책 |
|:---|:---|:---|:---|
| **S1** | **예매 진입** | `POST /api/booking/entry` | 특정 콘서트/경기의 '예매하기' 버튼을 누른 직후 단계 |
| **S2** | **대기열 통과** | (대기열 소켓) | 트래픽 대기열을 통과해 실제 예매망으로 들어오는 단계 |
| **S3** | **VQA 캡챠 관문** | - | **(가장 강력한 방어 구간)** 예매창 진입 전 1회성 공 잡기 캡챠(VQA)를 수행해야만 통과 가능한 단계 |
| **S4/S5** | **좌석 선점 (Hold)** | `POST /api/holds`<br/>`POST /api/orders` | 캡챠 통과 후 특정 좌석을 찜(Hold)하고 주문서를 생성 중인 고위험 타겟 단계 |
| **S6** | **최종 결제 완료** | `POST /api/payments` | 결제를 시도하는 크리티컬 단계. **정상 결제 방해를 막기 위해 추가 캡챠 개입은 절대 금지**하며, 명백한 봇만 `BLOCK` 처리합니다. (Fail-Open) |

> 🚫 **백엔드 구현 제외 대상 (AI 팀 전담 처리)**
> 1. **VQA 캡챠 발급/검증 API:** フロント엔드가 AI Defense 전용 엔드포인트(`POST /defense/challenge/...`)로 직결 통신하므로 백엔드는 캡챠 상태를 모른 채 안전해진 트래픽만 받게 됩니다.
> 2. **텔레메트리 비동기 수집 API:** 프론트엔드가 전송하는 대용량 궤적 데이터 역시 Envoy가 백엔드를 거치지 않고 AI 수집 API로 직행 라우팅(Bypass)합니다.

---
---

## 3. 티켓 예매/결제 Core API 인터페이스 스펙

백엔드 팀은 아래의 4가지 엔드포인트와 스키마를 기준으로 구현해 주시기 바랍니다.

### 3.1. [S1 ➡️ S2] 예매/대기열 진입
유저가 예매하기 버튼을 누르는 순간 호출되며, 백엔드는 대기열 티켓 발급 및 세션 상태를 DB/Redis에 기록합니다.

*   **Endpoint:** `POST /api/booking/entry`
*   **Request Schema:**
```json
{
  "sessionId": "tm:sess:abc1234",  // (필수) 프론트엔드에서 발급받은 세션 식별키
  "gameId": "game-2026-001",       // (필수) 예매 대상 경기
  "preferences": {                 // (선택) 자동 추천 옵션 등
    "recommendEnabled": true,
    "partySize": 2
  }
}
```

### 3.2. [S4 ➡️ S5] 좌석 선점 (Hold)
*주의: 매크로의 광클 1순위 타겟이 되는 핵심 구간이므로 Envoy 단에서 가장 빡빡한 채점 및 응답 지연(THROTTLE) 컨트롤이 개입합니다.*

*   **Endpoint:** `POST /api/holds`
*   **Headers 필수:** `Idempotency-Key` (봇의 무차별 중복 요청 서버 부하를 막기 위해 **백엔드 단의 멱등성 보장이 필수적**입니다.)
*   **Request Schema:**
```json
{
  "sessionId": "tm:sess:abc1234",
  "gameId": "game-2026-001", 
  "mode": "RECOMMEND",                // "RECOMMEND" (자동 배정) 또는 "MANUAL" (수동 선택)
  "seatBundleId": "bundle-01",        // 구역/블록 식별자
  "seatIds": ["seat-A12", "seat-A13"] // (필수) 단일 또는 복수의 좌석 식별자 배열
}
```

### 3.3. [S5] 주문서 생성 (Order)
좌석 찜하기(Hold)가 완료된 유저가 해당 좌석들로 최종 주문 내역(Order)을 생성합니다.

*   **Endpoint:** `POST /api/orders`
*   **Request Schema:**
```json
{
  "holdId": "hold-abc1234" // 좌석 선점(Hold) API 응답으로 받은 결과 ID (필수)
}
```

### 3.4. [S6 ➡️ SX] 최종 결제 처리 (Payment)
최종 PG 결제를 처리합니다. S6 단계에 진입한 정상 유저가 캡챠 등으로 방해받는 일(Fail-Closed)이 없도록 AI 방어망은 철저하게 보수적으로 작동합니다. (명백한 악성만 차단)

*   **Endpoint:** `POST /api/payments`
*   **Headers 필수:** `Idempotency-Key` (결제 중복 처리 방지용)
*   **Request Schema:**
```json
{
  "orderId": "order-xyz987", // 생성된 주문 번호 (필수)
  "method": "TOSS"           // 결제 수단 구분 값 (TOSS, KAKAO, CARD 등)
}
```

---

## 4. 사후 제재 API (Sanctions API) - 비동기 협업망

### 4.1. 동작 개요 및 관심사의 분리 (SoD)
오프라인 AI 단에서 대량의 행동 데이터를 분석해 매크로 유저(T3_Bot)를 확정했을 때, 이를 백엔드 비즈니스 로직에 반영하기 위한 규약입니다.

*   **AI 팀의 권한:** "의심 유저 판정 및 제재 대상 전달 통보 (API 호출)"
*   **Backend 팀의 권한:** "실제 토큰 만료, 강제 로그아웃, 선점 좌석(Hold) 롤백 여부 결정 (제재 집행)"

### 4.2. Sanctions API 스펙
*   **Endpoint 제안:** `POST /api/v1/internal/sanctions` (경로 조율 가능)
*   **보안:** 방화벽 내부망 전용 처리 또는 `Authorization: Bearer {Admin_Token}` 필수 구성
*   **Request Payload (AI ➡️ BE):**
```json
{
  "idempotencyKey": "uuid-v4-abc1234",   // 네트워크 재시도(Retry) 대비 멱등키 (필수)
  "sessionId": "tm:sess:abc1234",        // 적발된 세션의 ID
  "target": {
    "type": "USER_TOKEN",              // "USER_TOKEN" | "ACCOUNT_ID" | "SESSION"
    "value": "idx_user_9912"
  },
  "action": "SUSPEND",                 // "SUSPEND", "RATE_LIMIT", "FORCE_LOGOUT" 등 (BE가 참조할 힌트)
  "reasonCode": "R2_OFFLINE_BOT_DETECTED", // 차단 사유
  "auditTraceId": "trace-991823"       // 추후 증적 조회를 위한 추적 ID
}
```
*   **Response:**
    *   `200 OK`: 신규 제재 정상 접수 및 집행 완료
    *   `202 Accepted` (또는 200 OK): 이미 처리된 멱등키 (중복 요청 방어됨)
