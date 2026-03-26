# Defense Consistency Lock v1 (One Pager)

목적: FE/BE/Cloud/AI 문서 간 충돌을 막기 위해, 런타임 계약의 고정값을 한 페이지로 잠근다.

적용 범위:
- Istio `ext_authz` + Authz Adapter + AI Defense API 구조
- 티켓팅 보호 경로(S1~S6, queue gate challenge 포함)

---

## 1) 최종 아키텍처 경계 (LOCK)

- 실시간 판정 경로(고정):
  - `Envoy -> Authz Adapter -> AI Defense /evaluate`
- 비즈니스 처리 경로(고정):
  - `allow=true`일 때만 `Envoy -> Backend` 전달
- FE Challenge 수행 경로(고정):
  - FE는 앱 서버의 `POST /challenge/issue`, `POST /challenge/verify` 또는 동등 경로 사용
- BE와 AI는 직접 동기 호출을 기본 경로로 사용하지 않음(고정)

---

## 2) 정책 잠금값 (LOCK)

| 항목 | 최종 고정값 | 비고 |
|---|---|---|
| AI 판정 API 경로 | `POST /evaluate` | Adapter가 호출하는 단일 경로 |
| Challenge 상태코드 (edge deny) | `403` + `x-defense-action=challenge` | queue gate 1회 VQA 발급 시에만 사용 |
| Challenge 상태코드 (app gating) | `428 CHALLENGE_REQUIRED` | challenge active 중 high-value 재요청 차단 |
| Block 상태코드 | `403` + `x-defense-action=block` | 공통 |
| VQA 삽입 정책 | `Queue 통과 직후 1회 고정` | 전원 대상(사람/봇/AI), 세션 중 추가 VQA 금지 |
| Runtime LLM | 없음 | 사후 배치 분석 경로에서만 허용 |
| Honey/Sandbox | MVP 제외 | action enum에서 제외 |
| Flow/Tier enum | `S0,S1,S2,S3,S4,S4R,S5,S5R,S6,SX` / `T0~T3` | 변경 시 버전업 필수 |

---

## 3) 고정 계약 키셋 (LOCK)

### 3.1 Request headers
- `x-session-id` (required)
- `x-trace-id` (required)
- `idempotency-key` (hold/payment 계열 required)

### 3.2 Response headers
- `x-defense-action` = `none|challenge|throttle|gate|block` (primary)
- `x-defense-actions` = comma-separated multi actions (optional)
- `x-defense-tier` = `T0|T1|T2|T3`
- `x-defense-policy-version` = string
- `x-defense-trace-id` = trace id
- `x-challenge-type` (optional)
- `x-block-reason` (block 시 optional)

주의:
- `challenge`는 queue gate 1회 정책에서만 사용
- tier 상승(T1/T2/T3)만으로 세션 중 추가 challenge를 발동하지 않음

### 3.3 Multi-action 우선순위
- primary action 우선순위:
  - `block > challenge > gate > throttle > none`
- 예시:
  - `x-defense-action=gate`
  - `x-defense-actions=throttle,gate`

### 3.4 Evaluate request 최소 필수 필드
- `session_id` (string)
- `path` (string)
- `method` (string)
- `timestamp` (epoch ms)

---

## 4) 책임 분리 (LOCK)

- AI Defense:
  - `/evaluate` 판정과 정책 헤더 반환
  - runtime state(예: Redis) 업데이트
- Backend:
  - `/challenge/issue`, `/challenge/verify` 실행 책임
  - challenge active 중 high-value gating(428) 책임
- Cloud(Adapter/Istio):
  - ext_authz 연동, allow/deny 적용, 헤더 전달 책임
- Frontend:
  - `x-defense-action`/`x-defense-actions` 기반 UI 처리 책임

---

## 5) 변경 가능 항목 (TUNABLE)

- threshold, TTL, budget, throttle delay
- strict path prefix
- challenge type/difficulty/max-attempts
- 포트/호스트/배포 토폴로지

조건:
- `x-defense-policy-version` 증가
- decision audit로 전후 비교 가능해야 함

---

## 6) 변경 불가 항목 (FIXED)

- API 필드명/타입
- enum 이름(Flow/Tier/ReasonCode/Action)
- 헤더 키 이름
- ext_authz 판정 경계(allow만 BE 전달)

변경 절차:
- SSOT + OpenAPI + 연동 가이드를 같은 PR에서 동시 수정
- breaking change는 major version 증가
