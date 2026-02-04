# Defense PoC-0 — D0-2 Living Log

> Append-only.
> Records only merged, verified implementation facts.
> No speculation, no TODOs.

---

## 2026-02-XX

### [D0-2] initialized
- D0-2 문서 초기화 완료
- SPEC_SNAPSHOT.md: D0-1 상속 계약 및 EvidenceState 모델 정의
- ARCHIVE_LOG.md: 헤더만 생성

Paths:
- src/traffic_master_ai/defense/d0_poc/Specs/D0-2/SPEC_SNAPSHOT.md
- src/traffic_master_ai/defense/d0_poc/Specs/D0-2/LIVING_LOG.md
- src/traffic_master_ai/defense/d0_poc/Specs/D0-2/ARCHIVE_LOG.md

---

### [GRGB-80] D0-2-T1 Signal Aggregator Implementation
- EvidenceState dataclass 구현:
  - `last_signal_ts: int` (마지막 시그널 수신 시간)
  - `challenge_fail_count: int` (누적 실패 횟수)
  - `seat_taken_streak: int` (S5 연속 실패 횟수)
  - `signal_history: deque(maxlen=10)` (최근 10개 시그널 Ring Buffer)
  - `token_mismatch_detected: bool` (토큰 불일치 여부)
- SignalAggregator.process_event() 구현:
  - F-1: STAGE_3_CHALLENGE_FAILED → challenge_fail_count 증가
  - F-1: STAGE_3_CHALLENGE_PASSED → challenge_fail_count 초기화
  - F-3: STAGE_5_SEAT_TAKEN/HOLD_FAILED → seat_taken_streak 증가
  - F-3: STAGE_5_SEAT_SELECTED → seat_taken_streak 초기화
  - SIGNAL_TOKEN_MISMATCH → token_mismatch_detected = True
  - SIGNAL_* → signal_history에 추가

Paths:
- src/traffic_master_ai/defense/d0_poc/brain/__init__.py
- src/traffic_master_ai/defense/d0_poc/brain/evidence.py

---

### [GRGB-81] D0-2-T2 Risk Controller Implementation
- RiskController.decide_tier() 구현:
  - R-1: SIGNAL_REPETITIVE_PATTERN 1개 → T1, 3개 이상 → T2
  - R-2: challenge_fail_count >= 3 → T3 (Spec F-1)
  - R-3: token_mismatch_detected → T3 즉시 (Spec F-4)
  - R-4: T2+ 상태에서 S3 + STAGE_3_CHALLENGE_PASSED → T1 완화
- Tier rank mapping 사용 (T0 < T1 < T2 < T3)
- 하락은 R-4 조건 충족 시에만 허용
- RISK_TIER_UPDATED 이벤트 생성 로직 구현

Paths:
- src/traffic_master_ai/defense/d0_poc/brain/__init__.py
- src/traffic_master_ai/defense/d0_poc/brain/risk_engine.py

---

### [GRGB-82] D0-2-T3 Action Planner Implementation
- PlannedAction dataclass 구현:
  - `action_type: str` ("THROTTLE" | "BLOCK" | "CHALLENGE" | "SANDBOX" | "HONEY")
  - `params: dict` (예: {"strength": "light"}, {"difficulty": "medium"})
- ActionPlanner.plan_actions() 구현:
  - Tier-Action Matrix 적용:
    - T0: No Action
    - T1: THROTTLE(light)
    - T2: THROTTLE(strong) + CHALLENGE(medium)
    - T3: BLOCK
  - F-5 (S6 Protection): S6에서 신규 개입 금지, 단 T3이면 BLOCK 허용
  - F-3 (S5 Streak): seat_taken_streak >= 7이면 THROTTLE(strong) 추가 또는 승격

Paths:
- src/traffic_master_ai/defense/d0_poc/brain/__init__.py
- src/traffic_master_ai/defense/d0_poc/brain/planner.py

---

### [GRGB-83] D0-2-T4 Actuator Implementation
- Actuator.execute_plans() 구현:
  - THROTTLE → DEF_THROTTLED 생성
    - light: duration_ms=200
    - strong: duration_ms=2000
    - payload: {"duration_ms": int, "strength": string}
  - BLOCK → DEF_BLOCKED 생성
    - payload: {"reason": "tier_t3"}
  - CHALLENGE → DEF_CHALLENGE_FORCED 생성
    - payload: {"difficulty": string}
  - SANDBOX → DEF_SANDBOXED 생성 (context.is_sandboxed == False일 때만)
- Event 공통 속성:
  - source = EventSource.DEFENSE
  - session_id, ts_ms = trigger_event에서 상속
  - event_id = uuid4 기반 생성

Paths:
- src/traffic_master_ai/defense/d0_poc/actions/__init__.py
- src/traffic_master_ai/defense/d0_poc/actions/actuator.py
