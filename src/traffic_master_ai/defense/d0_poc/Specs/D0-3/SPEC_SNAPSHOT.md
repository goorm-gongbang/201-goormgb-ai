# Defense PoC-0 — D0-3 Spec Snapshot (Acceptance Scenarios)

## 0. D0-2 상속 계약 (Baseline)

### 상태 모델
- FlowState: S0 → S1 → S2 → S3 → S4 → S5 → S6 → SX
- DefenseTier: T0 (Normal) → T1 (Suspicious) → T2 (High Risk) → T3 (Confirmed Bot)

### 이벤트 모델
- Event 구조: event_id, ts_ms, type, source, session_id, payload
- DEF_* 이벤트: DEF_THROTTLED, DEF_BLOCKED, DEF_CHALLENGE_FORCED, DEF_SANDBOXED

### PolicySnapshot (PoC-0 고정)
- `max_retry_per_state = 3`, `challenge_fail_threshold = 3`, `seat_taken_streak_threshold = 7`

### 설계 원칙
- Transition Engine, RiskController, ActionPlanner, Actuator 모두 **순수 함수**
- Context/Evidence 변경은 diff 또는 새 객체로만 반환
- ScenarioRunner는 "실행"만 담당, 성공/실패 판정은 결과 데이터에만 포함

---

## 1. D0-3 목적

- Acceptance 시나리오 실행 엔진 구축
- D0-1(Core) + D0-2(Brain) 통합 검증
- 시나리오 정의 Schema 및 Runner 구현
