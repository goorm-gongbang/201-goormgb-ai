# Defense PoC-0 — D0-1 Spec Snapshot (Baseline)

## 0. 목적과 범위
- Story: **D0-1 (Defense PoC-0 초기 구축)**
- 목적:
  - 이벤트 주입 기반으로 방어 오케스트레이션 로직을 검증
  - 순수 함수 기반 상태 전이 엔진의 정합성 확보
- 비목적:
  - 실브라우저 / 실결제 / 외부 DB 연동
  - GAN / LLM / VQA 생성 로직

---

## 1. 상태 모델

### 1.1 FlowState
- S0: Init
- S1: Pre-Entry
- S2: Queue & Entry
- S3: Security Verification
- S4: Section Selection
- S5: Seat Selection
- S6: Transaction
- SX: Abort / Terminal

### 1.2 DefenseTier
- T0: Normal
- T1: Suspicious
- T2: High Risk
- T3: Confirmed Bot

### 1.3 Context Model
- `last_non_security_state: Optional[FlowState]` — S3 인터럽트 전 상태 저장
- `challenge_fail_count: int` — Challenge 실패 횟수 (초기값: 0)
- `seat_taken_count: int` — 좌석 선점 실패 횟수
- `hold_fail_count: int` — 홀드 실패 횟수
- `session_age: int` — 세션 경과 시간
- `is_sandboxed: bool` — 샌드박스 여부
- `retry_count: int` — 동일 상태 내 TIMEOUT 재시도 횟수 (초기값: 0, 상태 전이 시 0으로 리셋)

---

## 2. 이벤트 모델

### 2.1 기본 원칙
- 모든 이벤트는 canonical string name을 사용
- 이벤트는 현재 FlowState 기준으로 **유효성 검증 후 처리**
- 허용되지 않은 이벤트는 무시(ignore)하며 예외를 발생시키지 않음

### 2.2 Event Source
- PAGE
- BACKEND
- TIMER
- DEFENSE

(Event Dictionary 및 허용 상태 매핑은 `signals/registry.py`가 단일 진실)

---

## 3. Policy Snapshot

### 3.1 PolicySnapshot
Policy는 전이 시점에 immutable하게 전달된다.

고정 파라미터 (PoC-0):
- `max_retry_per_state = 3`
- `challenge_fail_threshold = 3`
- `seat_taken_streak_threshold = 7`

---

## 4. Transition Engine 규칙 (v1.0)

### 4.1 정상 전이
- S0 → S1 → S2 → S3 → S4 → S5 → S6
- 결제 완료 시:
  - S6 → SX
  - terminal_reason = DONE

### 4.2 Security (S3)

#### 4.2.1 S3 Interrupt (DEF_CHALLENGE_FORCED)
- 모든 상태에서 `DEF_CHALLENGE_FORCED` 이벤트 수신 시:
  - `next_state = S3`
  - `current_state != S3`인 경우에만 `last_non_security_state = current_state`
  - 이미 S3인 경우 덮어쓰지 않음

#### 4.2.2 S3 ReturnTo (STAGE_3_CHALLENGE_PASSED)
- S3에서 `STAGE_3_CHALLENGE_PASSED` 수신 시:
  - `last_non_security_state`가 있으면 해당 상태로 복귀
  - 없으면 `S4`로 기본 진행
  - 복귀 후 `last_non_security_state = None`으로 클리어

#### 4.2.3 Challenge Fail (F-1)
- Challenge 실패 횟수 누적
- threshold 도달 시:
  - Tier = T3
  - DEF_BLOCKED 액션 발생
  - Flow 종료 (SX), failure_code = F_CHALLENGE_FAILED

### 4.3 Failure Matrix

#### F-2: Timeout (Retry 기반)
- `TIME_TIMEOUT` 이벤트 수신 시:
  - `retry_count += 1`
  - `retry_count < max_retry_per_state`: 상태 유지
  - `retry_count >= max_retry_per_state`: SX 전이, terminal_reason = ABORT, failure_code = F_TIMEOUT
- 상태 전이 시 `retry_count = 0`으로 리셋
- 엔진은 타이머/이벤트 예약을 수행하지 않음 (외부 Driver가 주입)

#### F-4: Token Mismatch (즉시 차단)
- `SIGNAL_TOKEN_MISMATCH` 이벤트 수신 시 (모든 상태):
  - 즉시 SX 전이
  - terminal_reason = BLOCKED
  - failure_code = F_POLICY_VIOLATION
  - actions = [DEF_BLOCKED]

### 4.4 Seat Selection (S5)
- Seat taken / hold failed 발생 시:
  - streak 카운트 증가
- threshold 도달 시:
  - FlowState는 S5 유지
  - DEF_THROTTLED 액션만 발생
  - S4로 롤백하지 않음

### 4.5 Transaction (S6)
- 신규 방어 개입 없음
- 결제 완료 → DONE
- 결제 중단 → ABORT
- 트랜잭션 롤백 이벤트 수신 시 S5로 복귀

---

## 5. 설계 원칙
- Transition Engine은 **순수 함수**
- Context 변경은 diff(`context_mutations`)로만 반환
- Actuation, logging, persistence는 범위 외