# Defense PoC-0 — D0-4 Living Log

> Append-only.
> Records only merged, verified implementation facts.
> No speculation, no TODOs.

---

## 2026-02-XX

### [D0-4] initialized
- D0-4 문서 초기화 완료
- SPEC_SNAPSHOT.md: D0-1~D0-3 상속 계약 및 D0-4 목적 정의
- ARCHIVE_LOG.md: 헤더만 생성
- 목표: Decision Log & Audit Trail 시스템 구축

Paths:
- src/traffic_master_ai/defense/d0_poc/Specs/D0-4/SPEC_SNAPSHOT.md
- src/traffic_master_ai/defense/d0_poc/Specs/D0-4/LIVING_LOG.md
- src/traffic_master_ai/defense/d0_poc/Specs/D0-4/ARCHIVE_LOG.md

---

### [GRGB-100] D0-4-T1 Decision Log Schema & Context Snapshot
- DecisionLogEntry dataclass 구현 (`observability/schema.py`):
  - 필수 필드: ts, trace_id, seq, event, state_transition, tier_transition, evidence_snapshot, decision
  - 모든 top-level 필드 항상 존재 (값 없으면 None)
  - to_dict(): datetime → ISO8601 변환
  - to_json(): JSON 문자열 반환
- Static factory methods:
  - create_event_dict(): 이벤트 정보 표준화
  - create_state_transition(): 상태 전이 기록
  - create_tier_transition(): 티어 전이 기록
  - create_evidence_snapshot(): EvidenceState 매핑
  - create_decision(): 결정 정보 기록
- log_entry_from_step_result(): StepResult → DecisionLogEntry 변환 헬퍼
- 검증 완료: JSON 직렬화 테스트 통과

Paths:
- src/traffic_master_ai/defense/d0_poc/observability/__init__.py
- src/traffic_master_ai/defense/d0_poc/observability/schema.py

---

### [GRGB-101] D0-4-T2 Structured Logger & Middleware Implementation
- DecisionLogger 클래스 구현 (`logger.py`):
  - JSONL 포맷 출력 (1 line = 1 DecisionLogEntry)
  - setup(): 디렉토리 생성, 파일 truncate (clear) 후 새로 생성
  - log(): 에러 발생 시 print만 하고 예외 throw 안함 (fail-safe)
  - close(): 리소스 정리
  - Context manager 지원 (__enter__, __exit__)
- Factory 함수 패턴:
  - get_default_logger(): 기본 인스턴스 재사용
  - reset_default_logger(): 테스트용 초기화
- 검증 완료: 3개 엔트리 로깅, 모든 줄 JSON 파싱 성공

Paths:
- src/traffic_master_ai/defense/d0_poc/observability/logger.py
- src/traffic_master_ai/defense/d0_poc/observability/__init__.py

---

### [GRGB-102] D0-4-T3 Integration with Scenario Runner
- ScenarioRunner 수정 (`runner.py`):
  - `__init__`: `logger: DecisionLogger | None = None` 파라미터 추가
  - Backward compatible: logger가 None이면 기존 동작 유지
  - `_log_step()`: 각 Step 종료 후 DecisionLogEntry 생성 및 로깅
  - 로깅 순서: Event 주입 → Evidence 업데이트 → RiskEngine → ActionPlanner → Actuator → **모든 결과 완료 후** 로깅
  - try/except 감싸기: 로깅 오류는 print만 하고 예외 throw 안함
- DecisionLogEntry 생성 규칙:
  - trace_id = scenario.id (E2E 추적)
  - seq = step index (1-based)
  - event = 입력 이벤트 요약
  - state_transition = (from_state → to_state)
  - tier_transition = (from_tier → to_tier)
  - evidence_snapshot = 현재 EvidenceState 요약
  - decision = planned_actions + terminal_reason/failure_code
- run_all.py 수정:
  - DecisionLogger 초기화 (`setup()` 호출)
  - ScenarioRunner 생성 시 logger 주입
  - 모든 시나리오 실행 후 `logger.close()` 호출
- 검증 완료:
  - 15개 시나리오 전체 PASS
  - logs/decision_audit.jsonl 생성 (89 Step 로그)
  - 모든 줄 JSON 파싱 성공

Paths:
- src/traffic_master_ai/defense/d0_poc/scenarios/runner.py
- src/traffic_master_ai/defense/d0_poc/scenarios/run_all.py
