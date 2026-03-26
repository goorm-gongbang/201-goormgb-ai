# AI Defense Inner Architecture (Current)

Last updated: 2026-03-25

## 1. Overview
- Runtime entrypoint: `traffic_master_ai.defense.api.main:app`
- Public contract: `/ai/*`
- Runtime decision path: deterministic (D0 runtime + feature soft action), no online LLM.

## 2. Main components

### 2.1 API layer (`main.py`)
- Session 식별:
  - 우선순위 `X-Auth-Sid` -> `X-Session-Id` -> `Authorization Bearer JWT(sid)`
- 상태 키 생성:
  - `_build_state_key(sid, match_id) -> "{sid}:{match_id}"`
- Public handlers:
  - `/ai/precheck`
  - `/ai/telemetry/ingest`
  - `/ai/evaluate`
  - `/ai/challenge/start`
  - `/ai/challenge/verify`

### 2.2 State store (`state.py`)
- Redis configured: Redis state store 사용
- Redis unavailable: in-memory fallback
- snapshot model: `RuntimeStateSnapshot`

### 2.3 Challenge runtime (`challenge_runtime.py`)
- 역할:
  - 챌린지 발급 (`challengeId`, 만료시각, 내부 token 생성)
- verify는 `main.py`에서 현재 계약 로직(`caught`, 좌표 범위, 만료 여부)으로 판정.

### 2.4 Policy runtime bridge
- `ai_evaluate` 흐름:
  1. precheck 유효성 검사 (`QUEUE_ENTER`)
  2. seat entry에서 `vqa_passed` 미충족 시 `REQUIRE_S3`
  3. raw telemetry summary 기반 soft action (`REQUIRE_S3/THROTTLE`)
  4. 나머지는 D0 runtime evaluate로 위임

## 3. Telemetry summary pipeline
- ingest payload는 raw events.
- 서버 측에서 summary 계산:
  - `mousePointCount`
  - `totalDist`
  - `linearDist`
  - `linearityRatio`
  - `avgVelocity`
  - `tremorStdDev`
  - `dwellTime`
  - `pathRatio`
  - `botRisk`
- stage별 최신 summary를 state에 저장.

## 4. Challenge state transitions
- start:
  - `active_challenge_id` 세팅
  - `active_challenge_expires_at_ms` 세팅
- verify success:
  - `vqa_passed = True`, `vqa_required = False`, `vqa_last_result = PASSED`
  - active challenge clear
- verify failure:
  - `vqa_attempt_count += 1`
  - remaining > 0: `vqa_last_result = FAILED`
  - remaining == 0: `vqa_last_result = BLOCKED`, active challenge clear

## 5. Current boundaries
- Public FE contract는 `/ai/challenge/start`, `/ai/challenge/verify`만 사용.
- `/challenge/event` 기반 raw challenge ingest는 현재 범위에서 제거.
- `challengeToken`은 현재 계약/런타임에서 사용하지 않는다.
