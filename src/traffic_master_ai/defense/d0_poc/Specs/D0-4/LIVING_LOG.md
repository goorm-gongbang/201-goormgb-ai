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

---

### [GRGB-103] D0-4-T4 Log Analyzer & CLI Replay Reporter
- CLI 도구 구현 (`tools/analyze_logs.py`):
  - 기능 1: Summary Report (기본 동작)
    - trace_id(Scenario ID) 기준 그룹핑
    - 출력 컬럼: Scenario ID, Steps, Final State, Final Tier, Terminal Reason
    - SX 상태 강조 표시 (ANSI color)
  - 기능 2: Detail Replay (`--id SCN-XX`)
    - Step 타임라인: seq, event.type, state from→to, tier from→to, actions, terminal
    - BLOCK 액션 및 SX 상태 강조 표시
  - 옵션:
    - `--log-path`: 로그 파일 경로 오버라이드
    - `--no-color`: ANSI color 비활성화
  - 에러 처리: 사용자 친화적 메시지 출력 (stacktrace 노출 안함)
- 표준 라이브러리만 사용: json, argparse, pathlib
- 검증 완료:
  - 요약표 출력 (15 scenarios, 89 steps)
  - SCN-08 상세 로그 출력 (6 steps, BLOCK 강조)
  - --no-color 옵션 정상 작동
  - 유효하지 않은 trace_id 시 에러 메시지 + 가용 목록 출력

Paths:
- src/traffic_master_ai/defense/d0_poc/tools/__init__.py
- src/traffic_master_ai/defense/d0_poc/tools/analyze_logs.py

---

### [GRGB-104] D0-4-T5 Web-based Admin Dashboard & E2E Verification
- Streamlit 기반 "PoC-0 Cockpit" 구현 (`tools/dashboard.py`):
  - Section 1: System Health Check
    - [🚀 Run Full Diagnostics] 버튼
    - 순차 실행: pytest → run_all.py → logs 검증
    - st.status로 단계별 진행상황 업데이트
    - 각 단계 결과 expander로 stdout/stderr 표시
  - Section 2: Audit Log Explorer
    - decision_audit.jsonl 읽어서 DataFrame 생성
    - 컬럼: Timestamp, TraceID, Seq, Event Type, State, Tier, Actions, Reason
    - TraceID/Tier 드롭다운 필터링
    - Summary metrics: Total Entries, Unique Traces, T3 Escalations, Blocked Sessions
    - Raw JSON viewer for selected trace
- subprocess 실행: cwd=PROJECT_ROOT, capture_output=True, text=True
- st.session_state로 실행 결과 유지
- 오류 발생 시 앱 중단 없이 stderr 화면 표시
- `run_dashboard.sh` 런처 스크립트 생성
- 검증: Python syntax 검사 통과

Paths:
- src/traffic_master_ai/defense/d0_poc/tools/dashboard.py
- src/traffic_master_ai/defense/d0_poc/tools/run_dashboard.sh
