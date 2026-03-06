# Risk Tier Decision Guide (사람/봇 판단)

본 문서는 현재 구현 기준으로 "어떤 조건에서 tier/action이 바뀌는지"를 한 번에 설명합니다.

## 0) 고정 계약 vs 운영 가변값

- Fixed:
  - Tier/Action 의미(`T0~T3`, `DEF_*`)
  - 헤더 키(`x-defense-action`, `x-defense-tier`, `x-defense-policy-version`)
  - 이벤트/사유 코드의 의미
- Tunable:
  - telemetry/risk threshold
  - repetitive/challenge fail 임계치
  - strict 경로 prefix (throttle/sandbox 대상)
  - LLM gating 기준

아래 임계값 숫자는 baseline 예시이며 운영 중 변경 가능합니다.

## 1) 판단 경로가 2개인 이유

현재 레포에는 방어 경로가 2개 있습니다.

1. 플랫폼 로컬 게이팅(MVP-0)
   - 위치: `platform/backend/src/main/java/com/trafficmaster/security/DefaultRiskControlService.java`
   - 목적: 텔레메트리 기반 빠른 차단 검증
2. Cloud ext_authz 연동용 AI Defense API(stub)
   - 위치: `src/traffic_master_ai/defense/api/policy.py`
   - 목적: Adapter/Cloud 통합 계약 확정

## 2) 플랫폼 로컬 게이팅 기준(MVP-0)

입력: 최근 텔레메트리 snapshot

차단 조건(baseline):

- telemetry age <= 120000ms
- `totalDist >= 80.0`
- `totalDist - linearDist <= 0.8`
- `tremorStdDev <= 0.08`

위 조건을 동시에 만족하면 `RiskDecision.BLOCKED`.

운영 적용:
- 위 값은 운영 데이터로 재튜닝 가능
- 변경 시 `policy_version`을 증가시키고 A/B 비교 필수

의미:

- "거의 완벽한 직선 + 저노이즈"를 봇 신호로 간주

## 3) AI Defense API(stub) tier/action 기준

파일:

- `src/traffic_master_ai/defense/api/policy.py`
- 전달/운영 기준은 본 문서의 v1 잠금 정책을 우선 적용(코드 baseline과 불일치 시 문서 기준으로 정렬)

기본 규칙(baseline):

- R0 queue gate VQA: Queue 통과 직후 전원 1회 challenge (고정 정책)
- R3 token mismatch -> `T3`, `DEF_BLOCKED`
- R2 challenge fail 누적 `>= 3` -> `T3`, `DEF_BLOCKED`
- F5 `flow_state == S6` -> 신규 개입 금지(allow 유지)
- R1 repetitive pattern
  - `>= 3` -> `T2`, `DEF_SANDBOXED` (+ 필요 시 `DEF_THROTTLED`)
  - `>= 1` -> 최소 `T1`, `DEF_SANDBOXED`
- strict POST 경로(`TM_STRICT_POST_PATH_PREFIXES`)에서 tier가 `T2/T3`이면 throttle/sandbox 강화(추가 challenge 없음)

현재 기본 strict 경로(baseline):

- `/api/queue/`
- `/api/holds`
- `/api/payments`

실운영에서는 서비스 경로 체계에 맞춰 prefix를 재정의할 수 있음.

주요 정책 ENV 키(현재 stub 기준):
- `TM_DEFENSE_POLICY_VERSION`
- `TM_CHALLENGE_FAIL_THRESHOLD`
- `TM_REPETITIVE_PATTERN_T1_THRESHOLD`
- `TM_REPETITIVE_PATTERN_T2_THRESHOLD`
- `TM_BLOCK_ON_TOKEN_MISMATCH`
- `TM_STRICT_POST_PATH_PREFIXES`

VQA 정책 고정값(v1):
- Queue 통과 직후 1회 고정 VQA
- 세션 중 tier 변화(T1/T2/T3)만으로 추가 VQA를 발동하지 않음
- S6에서는 신규 개입 금지(기존과 동일)

## 4) Header 결과(클라이언트/어댑터 소비)

- `x-defense-policy-version`
- `x-defense-action`
  - `none`
  - `throttle`
  - `challenge`
  - `honey`
  - `sandbox`
  - `block`
- `x-defense-actions` (복수 액션, optional)
- `x-defense-tier`
- `x-block-reason` (block 시)
- `x-challenge-type` (challenge 시, queue gate 1회에서 사용)

## 5) LLM 호출 위치(현재/목표)

- 현재 운영 코드 경로에는 LLM 호출이 없습니다.
- 목표 정책 문서에서는 `HeavyJudge`를 `tier >= T2` 구간에서 gated로 호출하는 구조를 정의합니다.
- 즉, 현재는 deterministic rule 기반, 추후 LLM을 조건부로 추가하는 단계입니다.

## 6) 사람/봇 해석 가이드

사람 가능성 높은 패턴:

- 굴곡/미세 흔들림 존재
- 속도/정지 시간이 불규칙
- 챌린지 실패 누적이 낮음

봇 가능성 높은 패턴:

- 직선도 과도 + 노이즈 극저
- 반복 패턴 카운트 증가
- 토큰 불일치
- 챌린지 실패 누적

주의:
- 본 문서의 `challenge`는 "queue gate 1회 검증" 의미이며, 세션 중 step-up challenge를 의미하지 않음.

## 7) 운영 권장

1. 정책 버전(`x-defense-policy-version`)을 세션 시작 시 고정
2. threshold 변경 시 A/B 단위로 비교
3. 결정 로그와 사용자 마찰 지표를 같이 보고 튜닝
