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
