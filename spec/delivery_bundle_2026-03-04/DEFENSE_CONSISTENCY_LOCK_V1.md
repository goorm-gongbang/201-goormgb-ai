# Defense Consistency Lock v1 (One Pager)

목적: FE/BE/Cloud/AI 문서 간 충돌을 막기 위해, 런타임 계약의 고정값을 한 페이지로 잠근다.

적용 범위:
- Istio `ext_authz` + Authz Adapter + AI Defense API 구조
- 티켓팅 보호 경로(S1~S6, challenge overlay 포함)

---

## 1) 최종 아키텍처 경계 (LOCK)

- 실시간 판정 경로(고정):
  - `Envoy -> Authz Adapter -> AI Defense /evaluate`
- 비즈니스 처리 경로(고정):
  - `allow=true`일 때만 `Envoy -> Backend` 전달
- FE Challenge 수행 경로(고정):
  - FE는 앱 서버의 `POST /challenge/issue`, `POST /challenge/verify` 사용
- BE와 AI는 직접 호출을 기본 경로로 사용하지 않음(고정)

---

## 2) 충돌 항목 정합화 매트릭스 (LOCK)

| 항목 | 최종 고정값 | 비고 |
|---|---|---|
| AI 판정 API 경로 | `POST /evaluate` | Adapter가 호출하는 단일 경로 |
| Challenge 상태코드 (edge deny) | `403` + `x-defense-action=challenge` | ext_authz deny 응답 |
| Challenge 상태코드 (app gating) | `428 CHALLENGE_REQUIRED` | challenge active 중 high-value 재요청 차단 시 허용 |
| Block 상태코드 | `403` + `x-defense-action=block` | 공통 |
| 헤더 키 표기 | 소문자 canonical (`x-session-id`, `x-trace-id`, `x-defense-*`) | 프레임워크별 대소문자 normalize 허용 |
| Evaluate JSON 키 | `snake_case` | 예: `session_id`, `trace_id`, `flow_state` |
| Redis 필드명 | `snake_case` | 예: `risk_score`, `challenge_fail_count` |
| Flow/Tier enum | `S0,S1,S2,S3,S4,S4R,S5,S5R,S6,SX` / `T0~T3` | 변경 시 버전업 필수 |

---

## 3) 고정 계약 키셋 (LOCK)

### 3.1 Request headers (FE/Adapter 입력)
- `x-session-id` (required)
- `x-trace-id` (required)
- `idempotency-key` (hold/payment 계열 required)

### 3.2 Response headers (Adapter/BE -> FE)
- `x-defense-action` = `none|throttle|challenge|honey|sandbox|block` (primary)
- `x-defense-actions` = comma-separated multi actions (optional)
- `x-defense-tier` = `T0|T1|T2|T3`
- `x-defense-policy-version` = string
- `x-defense-trace-id` = trace id
- `x-challenge-type` (optional)
- `x-block-reason` (block 시 optional)

### 3.3 Multi-action 우선순위
- primary action 결정 우선순위:
  - `block > challenge > throttle > honey > sandbox > none`
- 동시 액션 예시:
  - `x-defense-action=challenge`
  - `x-defense-actions=throttle,challenge`

### 3.4 Evaluate request 최소 필수 필드
- `session_id` (string)
- `path` (string)
- `method` (string)
- `timestamp` (epoch ms)

---

## 4) 판정/실행 책임 분리 (LOCK)

- AI Defense:
  - `/evaluate` 판정과 정책 헤더 반환
  - runtime state(예: Redis) 업데이트
- Backend:
  - `/challenge/issue`, `/challenge/verify` 실행 책임
  - challenge active 중 high-value gating(428) 책임
- Cloud(Adapter/Istio):
  - ext_authz 연동, allow/deny 적용, 헤더 전달 책임
- Frontend:
  - `x-defense-action`/`x-defense-actions` 기반 challenge/throttle/honey/sandbox/block UI 처리 책임

---

## 5) 변경 가능 항목 (TUNABLE, 버전업 없이 가능)

- threshold, TTL, budget, throttle delay
- strict path prefix
- challenge type/difficulty/max-attempts
- 포트/호스트/배포 토폴로지

조건:
- `x-defense-policy-version` 증가
- decision audit로 전후 비교 가능해야 함

---

## 6) 변경 불가 항목 (FIXED, 버전업 필요)

- API 필드명/타입
- enum 이름(Flow/Tier/ReasonCode/Action)
- 헤더 키 이름
- ext_authz 판정 경계(allow만 BE 전달)

변경 절차:
- SSOT + OpenAPI + 연동 가이드를 같은 PR에서 동시 수정
- breaking change는 major version 증가

---

## 7) 본 문서의 우선순위

이 문서는 번들 내 정합성 잠금 문서이며, 충돌 시 아래 기준으로 해석한다.

1. `DEFENSE_CONSISTENCY_LOCK_V1.md` (이 문서)
2. `CI/openapi-defense.v1.yaml`
3. `FE/*`, `BE/*` 가이드 문서
4. 운영 파라미터 문서(`CONFIGURABILITY_POLICY.md`)
