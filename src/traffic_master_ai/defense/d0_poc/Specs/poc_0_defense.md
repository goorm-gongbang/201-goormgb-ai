# PoC-0 v1.0 – Defense Orchestration Spec (Implementation-Ready)

> 목적: LLM·실브라우저 없이 **이벤트 주입 기반**으로  
> 방어 오케스트레이션의 상태 전이, 위험 등급, 개입 로직이  
> **일관되게 동작하는지** 검증한다.
> **poc-0-defense.md는 PoC-0 baseline이며, STORY의 SPEC_SNAPSHOT과 충돌하면 SPEC_SNAPSHOT을 우선한다.**

---

## 0) 목적

- 입력: Event 스트림
- 출력:
  - FlowState 변화 로그
  - DefenseTier 변화 로그
  - Actuator Action(DEF_*) 로그
- PoC-0은 **순수 로직 검증용**이며, 실제 UI/API/LLM 연동은 포함하지 않는다.

---

## 1) State Machine Spec

### 1.1 상태 모델 (2축)

#### FlowState
S0, S1, S2, S3, S4, S5, S6, SX

#### DefenseTier
T0, T1, T2, T3

---

### 1.2 정상 전이 (Flow Progression)

- S0 --FLOW_START--> S1
- S1 --STAGE_1_ENTRY_CLICKED--> S2
- S2 --STAGE_2_QUEUE_PASSED--> S3
- S3 --STAGE_3_CHALLENGE_PASSED--> S4
- S4 --STAGE_4_SECTION_SELECTED--> S5
- S5 --STAGE_5_CONFIRM_CLICKED--> S6
- S6 --STAGE_6_PAYMENT_COMPLETED--> DONE  
  *(PoC-0에서는 DONE을 로그로만 기록하고 종료)*

---

### 1.3 Interrupt 전이 (방어 개입)

- Any(S1~S5) --DEF_CHALLENGE_FORCED--> S3

> PoC-0에서는 S3가 항상 존재하므로  
> 강제 개입은 `current_flow_state = S3`로 단순 덮어쓴다.
-	“PoC-0 v1.1+: S3는 return_to(마지막 비보안 상태)로 복귀 가능”
-	“last_non_security_state가 없으면 S4로 fallback”

---

### 1.4 실패 전이

- Any --FLOW_ABORT--> SX
- Any --SESSION_EXPIRED--> SX
- Any --DEF_BLOCKED--> SX

---

### 1.5 Timebox / Retry Budget (고정)

- TIMEOUT 발생 시: **1회 BACKOFF 후 재시도**
- 고정 파라미터:
  - MAX_RETRY_PER_STATE = 3
  - BACKOFF_MS = 200
- 실제 sleep은 사용하지 않고 `TIME_COOLDOWN_EXPIRED` 이벤트로 대체 가능

---

### 1.6 PoC-0 비목적

- 실제 DOM/네트워크 파싱 ❌
- 실제 좌석/결제 API ❌
- GAN / LLM / VQA 생성 ❌  
  → Challenge는 pass/fail 이벤트로만 시뮬레이션

---

## 2) Event Dictionary Spec

### 2.1 Event 공통 구조

```json
{
  "event_id": "string",
  "ts_ms": 123456789,
  "type": "EVENT_TYPE",
  "source": "page | backend | timer | defense",
  "session_id": "string",
  "payload": {}
}
```


## 2.2 Event Types (PoC-0 최소 세트)

“PoC-0에서는 최소 세트만 mandatory. 확장 이벤트는 story 스냅샷에서 추가 정의될 수 있으며, 추가 시 registry/validator도 함께 업데이트한다.”

### Flow
- FLOW_START
- FLOW_ABORT
- FLOW_RESET

### Stage Progress
- STAGE_1_ENTRY_ENABLED
- STAGE_1_ENTRY_CLICKED
- STAGE_2_QUEUE_SHOWN
- STAGE_2_QUEUE_PASSED
- STAGE_3_CHALLENGE_APPEARED
- STAGE_3_CHALLENGE_PASSED
- STAGE_3_CHALLENGE_FAILED
- STAGE_4_SECTION_LIST_READY
- STAGE_4_SECTION_SELECTED
- STAGE_4_SECTION_EMPTY
- STAGE_5_SEATMAP_READY
- STAGE_5_SEAT_SELECTED
- STAGE_5_SEAT_TAKEN
- STAGE_5_HOLD_FAILED
- STAGE_5_CONFIRM_CLICKED
- STAGE_6_PAYMENT_PAGE_ENTERED
- STAGE_6_PAYMENT_COMPLETED
- STAGE_6_PAYMENT_ABORTED

### Signal
- SIGNAL_TOKEN_MISMATCH
- SIGNAL_REPETITIVE_PATTERN

### Risk
- RISK_TIER_UPDATED

### Defense (Actuator 결과)
- DEF_THROTTLED
- DEF_SANDBOXED
- DEF_SANDBOX_RELEASED
- DEF_CHALLENGE_FORCED
- DEF_BLOCKED

### Time
- TIME_TIMEOUT
- TIME_COOLDOWN_EXPIRED
- SANDBOX_MAX_AGE_EXPIRED

---

## 2.3 이벤트 생성 주체

- Page / Backend / Timer / Defense 모두 사용
- PoC-0에서는 전부 Mock Producer로 대체

---

## 3) Failure Handling Matrix Spec

### 3.1 전역 파라미터 (고정)

- CHALLENGE_FAIL_THRESHOLD = 3
- N_SEAT_TAKEN_STREAK = 7
- BACKOFF_POLICY = one-shot backoff then retry
- STAGE6_NO_INTERVENTION = true

---

### 3.2 전역 실패 규칙

#### Rule F-1: Challenge 실패 누적
- STAGE_3_CHALLENGE_FAILED 누적 +1
- 3회 이상:
  - tier = T3
  - emit DEF_BLOCKED
  - flow_state = SX

---

#### Rule F-2: TIMEOUT 처리
- retry_count < MAX_RETRY_PER_STATE:
  - emit TIME_COOLDOWN_EXPIRED
  - 동일 상태 재시도
- 초과 시:
  - FLOW_ABORT → SX
- PoC-0에서는 TIME_COOLDOWN_EXPIRED는 엔진이 예약만 하고 실제 주입은 테스트/하니스가 수행해도 된다(슬립 없음).

---

#### Rule F-3: S5 이선좌/홀드 실패 반복
- STAGE_5_SEAT_TAKEN / STAGE_5_HOLD_FAILED 연속 카운트
- 7회 이상:
  - tier 유지
  - emit DEF_THROTTLED

---

#### Rule F-4: 정책 위반
- SIGNAL_TOKEN_MISMATCH 수신 시:
  - tier = T3
  - emit DEF_BLOCKED
  - flow_state = SX
- PoC-0에서는 Orchestrator(또는 transition 엔진)가 F-4를 집행하며, RiskEngine은 tier 변경 이벤트를 만들 수 있으나 최종 Block 집행은 Orchestrator→Actuator 경로로 수행한다.

---

#### Rule F-5: Stage 6 개입 금지
- S6에서는 신규 개입/승격 금지
- 단, 이미 T3인 경우 DEF_BLOCKED 허용

---

### 3.3 Sandbox 복귀 규칙
- DEF_SANDBOXED 상태에서:
  - SANDBOX_MAX_AGE_EXPIRED 전: 복귀 불가
  - 이후 STAGE_3_CHALLENGE_PASSED 수신 시:
    - emit DEF_SANDBOX_RELEASED

---

## 4) Responsibility Boundary Spec

### 4.1 컴포넌트 구성 (PoC-0)
- EventBus
- Orchestrator
- Guard
- RiskEngine
- Actuator
- Timer
- Logger

---

### 4.2 책임 규칙
- Guard → SIGNAL_*만 생성
- RiskEngine → RISK_TIER_UPDATED만 생성
- Actuator → DEF_*만 생성
- Orchestrator → FlowState 변경, 개입 결정, 차단 결정
- Page/Backend → Mock Producer로 대체 (event type 동일)

---

### 4.3 PoC-0 RiskEngine (Rule-based)
- 기본: T0
- SIGNAL_REPETITIVE_PATTERN 1회 → T1
- 반복(>=3) 또는 Sandbox 대상 → T2
- SIGNAL_TOKEN_MISMATCH → T3 즉시

---

## 5) Definition of Done (PoC-0)

- 이벤트 시나리오 3~4개 실행 시:
  - 상태 전이가 스펙과 일치
  - Challenge 실패 3회 → T3 + Block
  - Token mismatch → 즉시 T3 + Block
  - S5 반복 실패 → tier 유지 + throttle만 적용
  - Sandbox는 만료 + challenge pass 시에만 복귀
  - S6에서 신규 개입 없음
