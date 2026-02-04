# Defense PoC-0 — D0-2 Spec Snapshot (Brain Layer)

## 0. D0-1 상속 계약 (Baseline)

### 상태 모델
- FlowState: S0 → S1 → S2 → S3 → S4 → S5 → S6 → SX
- DefenseTier: T0 (Normal) → T1 (Suspicious) → T2 (High Risk) → T3 (Confirmed Bot)

### 이벤트 모델
- 모든 이벤트는 canonical string name 사용
- Event 구조: event_id, ts_ms, type, source, session_id, payload

### PolicySnapshot (PoC-0 고정)
- `max_retry_per_state = 3`
- `challenge_fail_threshold = 3`
- `seat_taken_streak_threshold = 7`

### 설계 원칙
- Transition Engine은 **순수 함수**
- Context 변경은 diff (`context_mutations`) 로만 반환
- Actuation, logging, persistence는 범위 외

---

## 1. D0-2 목적

- Brain 계층 컴포넌트 (Signal Aggregator, Risk Engine) 구현
- 이벤트 스트림에서 누적 증거(Evidence) 수집 및 위험도 판단

---

## 2. EvidenceState 모델

- `last_signal_ts: int` — 마지막 시그널 수신 시간
- `challenge_fail_count: int` — 누적 Challenge 실패 횟수
- `seat_taken_streak: int` — S5 연속 이선좌/홀드 실패 횟수
- `signal_history: deque(maxlen=10)` — 최근 10개 시그널 Ring Buffer
- `token_mismatch_detected: bool` — 토큰 불일치 발생 여부
