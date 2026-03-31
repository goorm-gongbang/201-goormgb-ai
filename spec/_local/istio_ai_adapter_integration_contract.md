# Istio/Authz <-> AI Runtime Integration Contract (Current)

Last updated: 2026-03-26

## 1. 목적
- `101-goormgb-frontend`와 AI Runtime 간 `/ai/*` 계약을 고정한다.
- ext_authz adapter가 호출하는 `/ai/evaluate` 입력/출력 형태를 고정한다.

## 2. Public endpoints

### 2.1 `POST /ai/precheck`
Request
```json
{
  "matchId": 687,
  "cfToken": "turnstile-token"
}
```

Response
```json
{
  "allowed": true
}
```

Headers
- `X-Session-Id` 또는 `X-Auth-Sid` 또는 `Authorization: Bearer <jwt(sid claim)>` 필요.

### 2.2 `POST /ai/telemetry/ingest`
Request
```json
{
  "matchId": 687,
  "stage": "QUEUE_ENTER_PRECLICK",
  "events": [
    {
      "type": "mousemove",
      "tsMs": 1773817200000,
      "xNorm": 0.42,
      "yNorm": 0.77
    },
    {
      "type": "click",
      "tsMs": 1773817200200,
      "xNorm": 0.47,
      "yNorm": 0.8,
      "button": 0
    }
  ]
}
```

Response
```json
{
  "accepted": true
}
```

Enums
- `stage`: `QUEUE_ENTER_PRECLICK | SEAT_STAGE | VQA_CHALLENGE`
- `events[].type`: `mousemove | mousedown | mouseup | click`

### 2.3 `POST /ai/challenge/start`
Request
```json
{
  "matchId": 687
}
```

Response
```json
{
  "challengeId": "CH_1a2b3c4d5e6f",
  "remainingAttempts": 2,
  "expiresAtMs": 1773817229123
}
```

### 2.4 `POST /ai/challenge/verify`
Request
```json
{
  "matchId": 687,
  "challengeId": "CH_1a2b3c4d5e6f",
  "caught": true,
  "catchTsMs": 1773817228123,
  "catchXNorm": 0.45,
  "catchYNorm": 0.88
}
```

Response
```json
{
  "success": true,
  "remainingAttempts": 1
}
```

주의
- `challengeToken`은 이 경로에서 사용하지 않는다.
- mismatched/expired challenge는 `success=false, remainingAttempts=0`으로 응답한다.

### 2.5 `POST /ai/evaluate`
Request
```json
{
  "event": {
    "eventType": "QUEUE_ENTER",
    "requestPath": "/queue/matches/687/enter",
    "requestMethod": "POST"
  },
  "context": {
    "sid": "sid_local_dev"
  }
}
```

> **`context.sid` 용도 제한 (중요)**  
> `context.sid`는 **AI runtime 상태 조회용 correlation key** (`{sid}:{matchId}`)로만 사용된다.  
> 이 값은 202 authz-adapter가 ingress 시점에 추출하며, JWT 서명 검증 없이 payload decode만 수행하는 fallback 경로를 포함한다.  
> 따라서 **backend sanction(제재) 의 identity로 사용해서는 안 된다.**  
>
> sanction callback(`_send_be_runtime_sanction`)은 현재 **비활성 상태** (`TM_BACKEND_RUNTIME_SANCTIONS_URL` unset)로 운영한다.  
> 추후 sanction 기능을 재추진할 때는 아래 계약 확장 절차를 따른다:
> 1. `context`에 `sidSource`, `sidTrusted` 필드 추가 (202/201 협의)
> 2. 202의 JWT signature verify 여부 및 trusted header 정책 결정
> 3. 201은 `sidTrusted=true`인 경우에만 sanction callback 활성화

```json
// 미래 sanction 재추진 시 context 확장 예시 (현재 미적용)
{
  "context": {
    "sid": "sid_abc123",
    "sidSource": "authorization_jwt_unverified",
    "sidTrusted": false
  }
}
```

Response
```json
{
  "decision": {
    "action": "REQUIRE_S3"
  }
}
```

Enums
- `event.eventType`:
  - `QUEUE_ENTER`
  - `SEAT_ENTRY`
  - `RECOMMENDATION_BLOCKS`
  - `SECTION_BLOCKS`
  - `ASSIGN_HOLD`
  - `SEAT_HOLDS`
- `decision.action`:
  - `NONE | THROTTLE | REQUIRE_S3 | BLOCK`

## 3. Internal-only endpoints
- `GET /readyz`
- `GET /runtime/{state_key}` where `state_key = "{sid}:{matchId}"`
- `POST /runtime/vqa/mark`
- `GET /meta/storage`
- `GET /metrics`

## 4. Session/State key 규칙
- 상태 저장 키: `"{sid}:{matchId}"`.
- `/ai/evaluate`는 `requestPath` 내 `/matches/{matchId}`를 파싱해 동일 키를 조회한다.

## 5. `/ai/evaluate` 결정 규칙 (현재 고정 계약)
- `QUEUE_ENTER`:
  - precheck 미통과면 `BLOCK`.
- VQA 이후 단계 이벤트:
  - `SEAT_ENTRY`
  - `RECOMMENDATION_BLOCKS`
  - `SECTION_BLOCKS`
  - `ASSIGN_HOLD`
  - `SEAT_HOLDS`
  - 위 이벤트에서 `vqa_passed == false`면 항상 `REQUIRE_S3` (Istio는 428 처리).
- 위 고정 가드 외에 tier/heuristic 기반으로 `REQUIRE_S3`를 추가로 내리지 않는다.

## 6. 실패/재시도 규칙 (challenge verify)
- 기본 재시도 제한: `vqa_retry_limit` (default 2).
- 실패 시 `vqa_attempt_count += 1`, `remainingAttempts` 감소.
- 남은 시도가 0이면 `vqa_last_result = BLOCKED` 상태로 전이.

## 7. Public contract에서 제거된 항목
- `/challenge/start`
- `/challenge/event`
- `/challenge/verify`
- verify payload의 `challengeToken`
