# Backend SSOT: AI Sanctions 연동 & DB 스키마 명세서 (3/19 Dev용)

본 문서는 AI 팀(2인)의 개발 리소스 한계를 고려하여, 백엔드 팀이 AI의 실시간 방어 및 사후 제재(Sanctions)와 연동하기 위해 **반드시 구현해야 할 최종 인터페이스 및 데이터베이스(DB/Redis) 구조**를 단일 진실 공급원(SSOT)으로 정의합니다.

---

## 1. 🚨 이중 차단(Dual-Blocking) 구현 가이드

AI 서버는 악성 트래픽을 L7(Istio)에서 1차 차단하고, 백엔드로 비동기 제재(Sanctions) API를 호출하여 **해당 유저의 JWT 만료 및 예매 세션 파기**를 강제합니다.

### 1.1. Backend 구현 과제: `Sanctions API` 엔드포인트
백엔드는 AI가 찌를 수 있는 내부용 제재 웹훅을 열어두고 로직을 구현해야 합니다.

*   **Endpoint:** `POST /api/v1/internal/sanctions`
*   **Request Payload (AI ➡️ BE):**
```json
{
  "idempotencyKey": "uuid-v4-abc1234",   // 네트워크 재시도(Retry) 대비 멱등키 (필수)
  "sessionId": "tm:sess:abc1234",        // 적발된 세션의 ID
  "target": {
    "type": "USER_TOKEN",                // "USER_TOKEN" | "ACCOUNT_ID" (식별 범위)
    "value": "idx_user_9912"             // 토큰 식별자 또는 유저 ID (백엔드 DB 식별용)
  },
  "action": "SUSPEND",                   // "SUSPEND" (강제 로그아웃) | "REVOKE" (단순 토큰만료)
  "reasonCode": "R2_OFFLINE_BOT_DETECTED",
  "auditTraceId": "trace-991823"         // 추후 증적 조회를 위한 추적 ID
}
```

*   **Backend 팀 요구 Action Items (구현 범위):**
    1.  멱등키 무시/중복 혀용 방지 (예: Redis에 `idempotencyKey` 존재 여부 체크 후 1회만 실행)
    2.  `target.value`에 해당하는 유저의 **Refresh Token 만료 처리 (Redis/DB 블랙리스트 등재)**
    3.  해당 유저가 기존에 생성한 좌석 Hold(선점) 내역이 있다면 **강제 릴리즈(Release)** 처리
    4.  *(Optional)* 보안 로깅 (Audit) 테이블에 해당 내역 적재

---

## 2. 🔑 JWT 토큰 Payload 확장 가이드

현재 백엔드가 발급하는 JWT 토큰(혹은 헤더)에 AI가 유저를 식별할 수 있는 정보를 노출해야, Istio가 검사 시 이 값을 AI 런타임에 넘겨줄 수 있습니다.

### 2.1. Backend 구현 과제: JWT Claim 또는 응답 헤더 변경
*   **변경 전:** 클라이언트에 단순히 JWT 토큰만 던져주거나, 토큰 내 식별자가 난독화되어 Istio proxy 레벨에서 추출 불가.
*   **변경 후:** JWT Token Payload 내부에 `userId` 또는 `accountId` 식별자를 1 depth로 평문(Plain) 명시. 
    *   (Istio의 RequestAuthentication 필터가 이 JWT를 검증하고, 파싱된 `userId` 값을 HTTP Header(예: `x-user-id`)로 변환하여 AI 파드 쪽에 던져줍니다.)

---

## 3. 🗄️ 백엔드 연동 DB / Redis 스키마 요구사항

AI의 제재(Sanctions)를 실질적으로 집행하기 위해서는 백엔드의 DB/Redis 구조에 제재 상태 관리가 녹아들어야 합니다.

### 3.1. 제재 이력/블랙리스트 (RDBMS Table - 제안)
제재 히스토리를 저장하고 어드민 등급에서 열람하기 위한 테이블 (예: `user_blocks` 또는 `sanctions_log` 테이블 신설)

| Column Name | Type | Key | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGINT | PK | Auto-increment ID |
| `user_id` | VARCHAR | FK | 제재 대상 회원 ID (`target.value`) |
| `reason_code` | VARCHAR | | 제재 사유 (예: `T3_Bot_Cheat`) |
| `trace_id` | VARCHAR | | AI 증적 로그 연결 ID (`auditTraceId`) |
| `block_expires_at` | DATETIME | | 제재 해제 시각 (영구정지면 MAX_DATE) |
| `created_at` | DATETIME | | 제재 접수 시각 |

### 3.2. JWT 무효화 Redis (Token Blacklist)
Sanctions API가 호출된 즉시 기존에 살아있던 AuthGuard 세션을 끊어내기 위해, 백엔드 Auth 필터가 통과 전 확인하는 토큰 블랙리스트 레디스 키 공간.

*   **Key:** `blacklist:token:{user_id}` 또는 `blacklist:token:{jti}`
*   **Value:** `1` (또는 만료기한 timestamp)
*   **TTL:** 해당 유저의 기존 Refresh Token 만료 기한과 동일하게 세팅하여 자연 소멸 유도
*   **AuthGuard 로직:** 모든 API 인가 전 `blacklist:token:*` 에 등록된 식별자인지 검사하여 401(Unauthorized) 리턴.
