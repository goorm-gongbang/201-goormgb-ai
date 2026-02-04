# Defense PoC-0 — D0-1 Living Log

> Append-only.
> Records only merged, verified implementation facts.
> No speculation, no TODOs.

---

## 2026-02-XX

### [GRGB-72] D0-1-T1 Core domain skeleton
- Defense PoC-0 기본 디렉토리 구조 생성
  - core / signals / orchestrator / policy
- Core enums 정의:
  - FlowState (S0–S6, SX)
  - DefenseTier (T0–T3)
  - EventSource
  - TerminalReason
  - FailureCode
- Core dataclass 모델 추가:
  - DefenseAction
  - Context
  - TransitionResult
- 순수 데이터 구조만 포함 (로직 없음)

Paths:
- src/traffic_master_ai/defense/d0_poc/core/states.py
- src/traffic_master_ai/defense/d0_poc/core/models.py

---

### [GRGB-73] D0-1-T2 Event registry & validation layer
- Canonical Event dataclass 구현
- 전체 Event Dictionary 상수화
- EVENT_ALLOWED_STATES 매핑 추가
  - Stage 이벤트는 대응 FlowState에서만 허용
  - FLOW_ABORT / SIGNAL_* / DEFENSE_* / TIME_* 는 ALL_STATES 허용
- Event validator 구현:
  - 허용되지 않은 이벤트는 ignore 처리 (예외 없음)
- 전이/정책 로직은 포함하지 않음

Paths:
- src/traffic_master_ai/defense/d0_poc/signals/events.py
- src/traffic_master_ai/defense/d0_poc/signals/registry.py
- src/traffic_master_ai/defense/d0_poc/signals/validator.py

---

### [GRGB-74] D0-1-T3 Policy snapshot & transition engine
- PolicySnapshot dataclass 추가 (threshold 고정)
- 순수 상태 전이 엔진 구현:
  - (FlowState, Event, Context, PolicySnapshot) → TransitionResult
- Spec v1.0 규칙 반영:
  - Challenge 실패 threshold → Block
  - S5 반복 실패 → Throttle only (state 유지)
  - S6 신규 방어 개입 없음
- Context 변경은 diff 형태로만 반환

Paths:
- src/traffic_master_ai/defense/d0_poc/policy/snapshot.py
- src/traffic_master_ai/defense/d0_poc/orchestrator/engine.py

---

### [GRGB-75] D0-1-T4 S3 Challenge Lifecycle (Interrupt & Failure)
- Context 모델 확장:
  - `retry_count: int` 필드 추가 (TIMEOUT 재시도 추적)
- S3 Interrupt 로직:
  - `DEF_CHALLENGE_FORCED` 이벤트 처리
  - `last_non_security_state` 저장 (S3가 아닌 상태에서만)
- S3 ReturnTo 로직:
  - `STAGE_3_CHALLENGE_PASSED` 시 원래 상태로 복귀
  - 복귀 후 `last_non_security_state` 클리어
- Failure Matrix 구현:
  - F-1: Challenge Fail → threshold 도달 시 BLOCKED
  - F-2: TIME_TIMEOUT → retry_count 기반, threshold 도달 시 ABORT
  - F-4: SIGNAL_TOKEN_MISMATCH → 즉시 BLOCKED
- Spec 변경: SPEC_SNAPSHOT.md에 Context Model, Failure Matrix 섹션 추가

Paths:
- src/traffic_master_ai/defense/d0_poc/core/models.py
- src/traffic_master_ai/defense/d0_poc/orchestrator/engine.py
- src/traffic_master_ai/defense/d0_poc/Specs/D0-1/SPEC_SNAPSHOT.md