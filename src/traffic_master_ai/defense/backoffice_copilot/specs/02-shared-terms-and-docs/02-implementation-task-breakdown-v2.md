# 02-implementation-task-breakdown-v2

## 1. 문서 목적
이 문서는 Backoffice Copilot v1 구현을 위한 최종 작업 분해안이다.  
이미 확정된 문서 충돌 해석 기준을 반영해, coding agent가 바로 구현 프롬프트로 전환할 수 있는 수준의 작업 순서, 의존 관계, 병렬 가능 범위, 완료 조건을 고정한다.

이 문서는 새로운 요구사항을 추가하지 않는다.  
기존 SSOT 문서를 구현 가능한 순서로 재배열하고, task 경계를 명확히 설명하는 메타 구현 문서다.

---

## 2. 이 문서가 반영한 확정 기준
### 2.1 run 식별자
- v1 구현의 run 식별자는 `match_id`로 통일한다.
- `review_run_id`는 v1 구현 기준에서 제거한다.
- DB, DTO, graph state, 저장 규칙, export 매핑도 전부 `match_id` 기준으로 해석한다.

### 2.2 출력 기준
- 정식 저장은 PostgreSQL 2테이블(`post_review_runs`, `post_review_session_results`)이다.
- export 파일(`summary.json`, `suspicious_sessions.jsonl`, `suspicious_sessions.csv`)은 DB 저장 이후 생성되는 후속 산출물이다.
- DB 저장 실패 상태에서 export 성공만으로 완료 처리하지 않는다.

### 2.3 사후판단 대상 정의
- v1 후보 추출에는 `payment_success` 조건을 사용하지 않는다.
- 후보 추출은 방어 로그 기준 규칙으로만 수행한다.
- 핵심 후보 규칙은 `seen_t1 || seen_t2`, `block_event_count == 0`, `latest_action != BLOCK`, `latest_tier != T3`, `terminal_outcome == NOT_BLOCKED`다.

### 2.4 공식 해석 필드와 최소 row DTO
- 입력 row DTO는 최소 구조를 유지한다.
- `flowState`, `terminalReason`, `reasonCode`, `latest_*` 해석은 semantic mapping 계층이 담당한다.
- row loader와 event interpreter는 분리된 책임으로 구현한다.

### 2.5 backend 전달 범위
- 우리 범위는 `Backend request DTO` 생성, adapter 경계, `backend_delivery_status` 갱신까지다.
- 외부 backend 실제 구현은 범위 밖이다.
- Discord/Grafana 실제 연동도 범위 밖이다.

---

## 3. 구현 제외 범위
- 외부 backend 서버/API 실제 구현
- Discord/Grafana 실제 연동
- ClickHouse 결과 저장
- S3 결과 저장
- 관리자 UI/API 구현
- Runtime 실시간 판단 변경
- 제재 집행
- 정책 자동 반영
- 중간 산출물 전용 DB 테이블 추가

---

## 4. coding agent 사용 규칙
이 문서를 보고 구현 프롬프트를 작성할 때는 아래를 따른다.

1. 한 번에 하나의 task만 맡기는 것을 기본으로 한다.
2. task 프롬프트에는 반드시 `목적`, `구현 범위`, `구현 제외`, `입력`, `출력`, `관련 문서`, `완료 조건`을 포함한다.
3. 해당 task와 무관한 리팩터링, 파일 이동, API 확장, 저장소 추가는 금지한다.
4. task의 선행 작업이 끝나지 않았으면 구현 프롬프트를 작성하지 않는다.
5. 병렬 가능 task라도, 같은 파일을 동시에 강하게 건드릴 가능성이 있으면 병렬로 보내지 않는다.
6. `Task 11` 테스트는 별도 최종 단계이면서 동시에 각 task와 shadow-parallel로 따라붙어야 한다.

---

## 5. 전체 구현 맵 요약
| Phase | Task | 한 줄 목적 | 선행 | 병렬 가능 여부 |
| --- | --- | --- | --- | --- |
| Phase 0 | Task 0 | 충돌 해석을 문서 기준선으로 고정 | 없음 | 불가 |
| Phase 0 | Task 1 | DTO/state/module 경계 고정 | Task 0 | 불가 |
| Phase 1 | Task 2 | PostgreSQL 2테이블 저장 기반 확정 | Task 1 | Task 3와 병렬 가능 |
| Phase 1 | Task 3 | 입력 로딩과 semantic mapping 확정 | Task 1 | Task 2와 병렬 가능 |
| Phase 1 | Task 9a | 기본 validator 골격 선반영 | Task 1, Task 2 | Task 3 이후 세부 확장 가능 |
| Phase 2 | Task 4 | SessionSummary 집계와 candidate 추출 | Task 3 | 불가 |
| Phase 2 | Task 5 | raw fallback + SessionAnalysis 생성 | Task 4 | 세션별 내부 병렬 허용 |
| Phase 3 | Task 6 | LLM 입력/출력/세션 fallback 구현 | Task 5 | 세션별 bounded 병렬 허용 |
| Phase 3 | Task 7 | 3줄 window summary 생성 | Task 6 | 불가 |
| Phase 4 | Task 8 | DB 저장 + backend payload + export | Task 2, Task 6, Task 7 | 불가 |
| Phase 4 | Task 9b | 최종 상태 분류/운영 검증 완성 | Task 8 | 불가 |
| Phase 5 | Task 10 | LangGraph workflow 조립 | Task 3 ~ Task 9b | 불가 |
| Phase 6 | Task 11 | 테스트/검증 코드 최종 마감 | shadow-parallel 시작은 Task 1 이후, 최종 마감은 Task 10 이후 | 병행 + 최종 통합 |

---

## 6. 직렬/병렬 맵
### 6.1 직렬 백본
`Task 0 -> Task 1 -> Task 3 -> Task 4 -> Task 5 -> Task 6 -> Task 7 -> Task 8 -> Task 9b -> Task 10`

### 6.2 병렬 레인
- 저장소 레인: `Task 2`는 `Task 1` 직후 시작해서 `Task 8`에서 합류
- 검증 골격 레인: `Task 9a`는 `Task 2` 직후 시작해 Phase 4에서 `Task 9b`로 확장
- 테스트 레인: `Task 11`은 `Task 1` 이후 shadow-parallel로 시작하고, `Task 10` 이후 통합 마감

### 6.3 내부 병렬 허용 범위
- `Task 5`: candidate 세션별 병렬 허용
- `Task 6`: 세션별 bounded concurrency 허용

### 6.4 병렬하면 안 되는 구간
- `Task 4`와 `Task 5`는 순차 유지
- `Task 6`과 `Task 7`은 순차 유지
- `Task 8`은 저장 정합성 때문에 순차 유지
- `Task 10`은 전체 노드 준비가 끝난 뒤 조립

---

## 7. 상세 작업 설명
## Task 0. SSOT 동기화
### 목적
충돌하는 문장과 해석 기준을 v1 구현 기준으로 정렬한다.

### 이 task가 끝나면
coding agent가 더 이상 `review_run_id`, export-first, `payment_success`, backend 실제 구현 범위를 혼동하지 않는다.

### 구현 범위
- `match_id` 기준 run 식별자 반영
- DB-first 출력 기준 반영
- `payment_success` 제거
- semantic mapping 책임 명시
- backend 전달 범위를 DTO/adapter 경계로 제한

### 구현 제외
- 코드 구현
- DTO/DB schema 변경 구현
- 테스트 코드 작성

### 입력
- 현재 SSOT 14개 문서
- 확정된 5개 충돌 해석 기준

### 출력
- coding agent가 하나의 기준으로 읽을 수 있는 문서 세트

### 관련 문서
- `00-core-rules.*`
- `01-service-overview.*`
- `10-post-review-rules.*`
- `11-review-output-rules.*`
- `20-langgraph-node-spec.*`
- `21-data-contract.*`
- `30-ops-and-checks.*`

### 선행 작업
- 없음

### 병렬성
- 불가

### 리스크
- 문서 간 표현 차이를 한 곳만 고치고 다른 곳을 놓치면 다시 drift가 생긴다.

### 완료 조건
- 문서상 v1 구현 기준이 `match_id`, DB-first, no-`payment_success`, semantic mapping, backend boundary로 읽힌다.

### prompt 작성 시 강조점
- 문서 동기화 외 기능 추가 금지
- 새 요구사항 추가 금지

---

## Task 1. 공통 계약 및 패키지 골격
### 목적
후속 task가 공유할 DTO, graph state, warnings/errors, module boundary를 고정한다.

### 이 task가 끝나면
이후 task는 공통 import 기준과 명확한 책임 경계를 가진 상태에서 구현을 시작할 수 있다.

### 구현 범위
- `match_id` 기반 run context
- graph state 계약
- `DefenseAuditEventRow`, `SessionSummary`, `SessionAnalysis`
- LLM input/output DTO
- Backend request/response DTO
- warnings/errors 구조
- module/package boundary

### 구현 제외
- 비즈니스 로직
- DB 저장
- LLM 호출
- workflow 조립

### 입력
- Task 0 완료 문서

### 출력
- 공통 타입/모델 계층
- config skeleton
- module boundary 문서 또는 코드 골격

### 관련 문서
- `20-langgraph-node-spec.*`
- `21-data-contract.*`
- `00-core-rules.*`
- `10-post-review-rules.*`

### 선행 작업
- Task 0

### 병렬성
- 불가

### 리스크
- graph state에 불필요한 필드를 넣거나, 중간 persistence 여지를 남기면 후속 task가 흔들린다.

### 완료 조건
- 후속 task가 공통 계약을 재정의하지 않고 바로 사용할 수 있다.
- 중간 산출물은 메모리 DTO로만 처리된다는 점이 구조에 반영된다.

### prompt 작성 시 강조점
- undocumented field 추가 금지
- `review_run_id` 재도입 금지

---

## Task 2. PostgreSQL 저장소 기반
### 목적
정식 저장 2테이블과 저장 인터페이스를 먼저 확정한다.

### 이 task가 끝나면
후속 결과 저장 task는 이미 정의된 repository/DDL을 소비하는 구조로 구현할 수 있다.

### 구현 범위
- `post_review_runs`
- `post_review_session_results`
- repository/write adapter
- PK conflict policy 연결 지점
- allowed value/JSONB/type 검증 helper

### 구현 제외
- backend 실제 호출
- export 생성
- workflow 조립

### 입력
- Task 1 공통 계약
- PostgreSQL 연결 방식

### 출력
- DDL/migration
- repository 계층
- column-level validator 기초

### 관련 문서
- `11-review-output-rules.*`
- `21-data-contract.*`
- `30-ops-and-checks.*`
- `10-post-review-rules.*`

### 선행 작업
- Task 1

### 병렬성
- Task 3와 병렬 가능

### 리스크
- DB-first 구조를 잘못 잡으면 후속 export/상태 분류까지 모두 꼬인다.

### 완료 조건
- 허용 테이블은 2개뿐이다.
- `review_result`, `backend_delivery_status`, `status` 허용값이 반영된다.
- JSONB 저장 대상 구조를 검증할 수 있다.

### prompt 작성 시 강조점
- ClickHouse/S3 추가 금지
- 중간 테이블 추가 금지

---

## Task 3. 입력 row 로더 + semantic mapping
### 목적
입력 로딩과 의미 해석을 분리해 후속 집계/분석이 안정적으로 작동하게 만든다.

### 이 task가 끝나면
`analysis_input`과 event interpretation이 준비되어 `Task 4`부터 규칙 기반 파이프라인을 시작할 수 있다.

### 구현 범위
- `defense_audit_events` 시간 구간 필터 로딩
- `limit` 처리
- `raw_audit_available` 기록
- 핵심/보강/비사용 event 분류
- `flowState`, `terminalReason`, `reasonCode`, `latest_*` 해석 함수

### 구현 제외
- candidate 추출
- LLM 호출
- DB 저장

### 입력
- graph input
- `defense_audit_events.jsonl`

### 출력
- `analysis_input`
- semantic mapping/interpreter 계층

### 관련 문서
- `00-core-rules.*`
- `01-service-overview.*`
- `10-post-review-rules.*`
- `20-langgraph-node-spec.*`
- `21-data-contract.*`

### 선행 작업
- Task 1

### 병렬성
- Task 2와 병렬 가능

### 리스크
- 최소 row DTO와 공식 해석 필드 사이의 간극을 잘못 처리하면 후속 규칙이 전부 흔들린다.

### 완료 조건
- 입력 row DTO는 최소 구조를 유지한다.
- 해석 책임은 semantic mapping 계층에만 있다.
- `S3_CHALLENGE_HALTED`는 비사용으로 분리된다.

### prompt 작성 시 강조점
- loader와 interpreter를 한 함수에 섞지 말 것
- `payment_success` 같은 미합의 필드 도입 금지

---

## Task 9a. 기본 validator 골격
### 목적
후반부에 붙일 검증을 초기에 구조화해, 저장/상태 규칙이 늦게 새지 않도록 한다.

### 이 task가 끝나면
후속 task는 최소한의 입력/컬럼/허용값 validator 인터페이스를 공통으로 사용할 수 있다.

### 구현 범위
- 입력 파라미터 validator 골격
- DB 컬럼 validator 골격
- allowed value validator 골격
- warnings/errors container 골격

### 구현 제외
- 최종 상태 분류 완성
- stage별 실제 결과 집계 완성

### 입력
- Task 1 공통 계약
- Task 2 저장 계층

### 출력
- validator skeleton
- 상태/검증 인터페이스

### 관련 문서
- `30-ops-and-checks.*`
- `21-data-contract.*`
- `11-review-output-rules.*`

### 선행 작업
- Task 1
- Task 2

### 병렬성
- Task 3 이후 세부 확장 가능

### 리스크
- 너무 늦게 붙이면 검증이 후행 부가물처럼 변하고, 너무 많이 구현하면 중복이 생긴다.

### 완료 조건
- 최소 validator 뼈대가 존재하고, 후속 `Task 9b`에서 확장 가능한 형태다.

### prompt 작성 시 강조점
- 최종 status resolver까지 한 번에 끝내려 하지 말 것
- skeleton만 구현하고 Task 9b에서 완성할 것

---

## Task 4. SessionSummary 집계기 + candidate 추출기
### 목적
규칙 기반 분석의 첫 번째 실제 산출물인 `candidate_sessions`를 생성한다.

### 이 task가 끝나면
LLM 이전 단계에서 어떤 세션을 분석할지가 확정된다.

### 구현 범위
- `session_id` 기준 집계
- `SessionSummary` 필드 산출
- candidate 최소 규칙 적용

### 구현 제외
- raw fallback 조회
- SessionAnalysis 생성
- LLM 호출

### 입력
- `analysis_input`
- semantic interpreter

### 출력
- `session_summaries`
- `candidate_sessions`

### 관련 문서
- `10-post-review-rules.*`
- `20-langgraph-node-spec.*`
- `21-data-contract.*`
- `01-service-overview.*`

### 선행 작업
- Task 3

### 병렬성
- 불가

### 리스크
- 후보 조건에서 `payment_success`나 비정의 필드를 다시 끌어들이면 v1 기준이 깨진다.

### 완료 조건
- `candidate_sessions`가 최초 생성된다.
- `seen_t1 || seen_t2`, `NOT_BLOCKED` 등 현재 합의 규칙만 사용한다.

### prompt 작성 시 강조점
- 규칙은 문서 그대로 구현
- candidate가 0건이어도 경고만 남기고 구조는 유지

---

## Task 5. raw fallback 조회기 + SessionAnalysis 생성기
### 목적
candidate 세션을 LLM 입력 직전 분석 객체로 변환한다.

### 이 task가 끝나면
`session_analysis_list`가 완성되어 Node 4로 넘어갈 수 있다.

### 구현 범위
- `decision_audit` 제한 조회
- `session_id + time window` 제약
- `timeline_summary`
- `suspicious_signals`
- `needs_raw_fallback`
- `SessionAnalysis` 최소 구조 생성

### 구현 제외
- LLM input builder
- 최종 레이블 생성
- DB 저장

### 입력
- `candidate_sessions`
- `analysis_input`
- optional raw fallback rows

### 출력
- `session_analysis_list`

### 관련 문서
- `10-post-review-rules.*`
- `20-langgraph-node-spec.*`
- `21-data-contract.*`
- `30-ops-and-checks.*`

### 선행 작업
- Task 4

### 병렬성
- candidate 세션별 내부 병렬 허용

### 리스크
- raw fallback 범위를 넓히면 문서 위반이고, 너무 좁히면 `needs_raw_fallback`가 쓸모 없어질 수 있다.

### 완료 조건
- LLM 입력 직전 분석 객체가 문서 최소 구조대로 완성된다.
- full raw scan이 없다.

### prompt 작성 시 강조점
- raw fallback은 제한 조회만
- `SessionAnalysis`는 저장 가능한 JSON 구조여야 함

---

## Task 6. LLM 입력 빌더 + 출력 검증기 + 세션별 fallback
### 목적
세션별 `review_result`, `evidence_summary`를 생성한다.

### 이 task가 끝나면
`review_results`가 확정되어 저장기와 요약 생성기가 소비할 수 있다.

### 구현 범위
- LLM input DTO builder
- LLM output parser/validator
- 허용 레이블 강제
- hallucination 방지
- 세션별 fallback
- bounded concurrency

### 구현 제외
- 3줄 summary 생성
- DB 저장
- backend 전달

### 입력
- `match_id`
- window
- `session_analysis_list`

### 출력
- `review_results`

### 관련 문서
- `00-core-rules.*`
- `10-post-review-rules.*`
- `20-langgraph-node-spec.*`
- `21-data-contract.*`
- `30-ops-and-checks.*`

### 선행 작업
- Task 5

### 병렬성
- 세션별 bounded 병렬 허용

### 리스크
- 허용 레이블 이탈, 빈 evidence, fallback 추적 누락이 가장 큰 위험이다.

### 완료 조건
- `review_result`는 `NORMAL`/`SUSPICIOUS` 둘 중 하나다.
- LLM 실패 시에도 fallback으로 결과를 만든다.

### prompt 작성 시 강조점
- 입력 근거 밖 추측 금지
- `review_result` 허용값 외 결과 reject

---

## Task 7. Window summary 생성기
### 목적
시간 구간 3줄 요약을 독립 모듈로 구현한다.

### 이 task가 끝나면
`summary_text`가 완성되고, `Task 8`이 이를 소비해 run row와 export를 만들 수 있다.

### 구현 범위
- summary 입력 조립
- 3줄 요약 생성
- 길이 3 검증
- LLM 실패 시 template fallback

### 구현 제외
- DB 저장
- backend 전달
- export 생성

### 입력
- `review_results`
- `session_analysis_list`
- `match_id`
- window

### 출력
- `summary_text`

### 관련 문서
- `00-core-rules.*`
- `01-service-overview.*`
- `20-langgraph-node-spec.*`
- `21-data-contract.*`
- `11-review-output-rules.*`

### 선행 작업
- Task 6

### 병렬성
- 불가

### 리스크
- 독립 모듈이지만 저장기와 결합도가 높아, 나중에 Task 8에서 흡수해버리기 쉽다.

### 완료 조건
- 항상 길이 3의 summary를 반환한다.
- `Task 8`은 이 산출물을 소비만 한다.

### prompt 작성 시 강조점
- summary 생성기는 독립 모듈
- 저장기 안으로 요약 생성 로직 흡수 금지

---

## Task 8. 결과 저장기 + backend payload 생성기 + export 생성기
### 목적
Node 6 계약대로 DB-first 저장과 suspicious-only 전달 데이터를 만든다.

### 이 task가 끝나면
run/session 결과가 DB에 저장되고, backend payload와 optional export가 생성된다.

### 구현 범위
- run row 조립/저장
- session row 조립/저장
- `backend_request` 생성
- adapter boundary 호출
- `backend_response` 반영
- `backend_delivery_status` 갱신
- DB 기반 export 생성

### 구현 제외
- 외부 backend 실제 구현
- Discord/Grafana 실제 연동
- 최종 status 분류

### 입력
- Task 2 저장 계층
- `review_results`
- `summary_text`
- `session_analysis_list`
- `candidate_sessions`

### 출력
- DB rows
- `backend_request`
- `backend_response`
- optional export files

### 관련 문서
- `10-post-review-rules.*`
- `11-review-output-rules.*`
- `20-langgraph-node-spec.*`
- `21-data-contract.*`
- `30-ops-and-checks.*`

### 선행 작업
- Task 2
- Task 6
- Task 7

### 병렬성
- 불가

### 리스크
- 저장 정합성, suspicious-only delivery, export downstream 규칙을 동시에 맞춰야 한다.

### 완료 조건
- DB-first 저장이 성공한다.
- 전달 대상은 `SUSPICIOUS`만이다.
- `Task 7` 산출물을 그대로 소비한다.

### prompt 작성 시 강조점
- backend는 payload 생성과 상태 갱신까지만
- export는 DB 저장 이후 후속 단계

---

## Task 9b. 실행 상태/검증/체크 로직 완성
### 목적
초기 validator 골격을 실제 실행 결과 기준으로 완성하고 최종 상태를 분류한다.

### 이 task가 끝나면
run이 `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED` 중 무엇인지 문서 기준으로 판정할 수 있다.

### 구현 범위
- pre-run checks 완성
- stage checks 완성
- fallback checks 완성
- fatal/partial classification
- final status resolver
- warning/error accumulation 마감

### 구현 제외
- workflow 조립
- 테스트 코드 최종 통합

### 입력
- Task 9a validator skeleton
- Task 8 저장/전달 결과

### 출력
- validation report
- final run status
- warnings/errors finalized

### 관련 문서
- `30-ops-and-checks.*`
- `11-review-output-rules.*`
- `21-data-contract.*`
- `20-langgraph-node-spec.*`

### 선행 작업
- Task 8
- Task 9a

### 병렬성
- 불가

### 리스크
- 이 단계가 늦게 붙으면 운영 의미가 약해지고, 너무 일찍 완성하려 하면 실제 결과 없는 추상 validator가 된다.

### 완료 조건
- `SUCCESS / PARTIAL_SUCCESS / FAILED` 최종 분류가 문서 규칙대로 작동한다.
- DB 실패는 fatal이고, partial failure 허용 기준이 반영된다.

### prompt 작성 시 강조점
- Task 9a를 확장하는 구조 유지
- 상태 분류는 Task 8 결과 기반으로만 확정

---

## Task 10. LangGraph 파이프라인 조립
### 목적
고정된 노드 순서와 상태 흐름을 실제 workflow로 만든다.

### 이 task가 끝나면
Backoffice Copilot 전체가 실제 entrypoint 기준으로 실행 가능해진다.

### 구현 범위
- node wiring
- state 전달
- warnings/errors propagation
- 내부 병렬성 제한 반영

### 구현 제외
- 새로운 노드 추가
- 관리자 API 의존 구조 도입
- 외부 delivery 구현

### 입력
- Task 3 ~ Task 9b 산출물

### 출력
- workflow entrypoint
- LangGraph app 또는 동등 실행 엔트리포인트

### 관련 문서
- `20-langgraph-node-spec.*`
- `00-core-rules.*`
- `30-ops-and-checks.*`

### 선행 작업
- Task 3
- Task 4
- Task 5
- Task 6
- Task 7
- Task 8
- Task 9b

### 병렬성
- 불가

### 리스크
- 노드 수/순서/책임 경계가 무너지면 SDD 구조 자체가 깨진다.

### 완료 조건
- 노드 순서가 문서와 일치한다.
- 임의 분기나 중간 persistence가 없다.

### prompt 작성 시 강조점
- node count 변경 금지
- `Task 7`과 `Task 8`의 경계 유지

---

## Task 11. 테스트/검증 코드
### 목적
문서 계약을 회귀 가능한 테스트로 고정한다.

### 이 task가 끝나면
후속 리팩터링이나 coding agent 작업이 문서 계약을 깨면 테스트로 바로 드러난다.

### 구현 범위
- unit tests
- integration tests
- workflow tests
- fixture logs
- DB consistency tests
- fallback tests
- suspicious-only delivery tests

### 구현 제외
- 요구사항 추가
- 문서 충돌 자체 해결

### 입력
- Task 1 ~ Task 10 구현물

### 출력
- 회귀 테스트 스위트
- 통합 검증 세트

### 관련 문서
- 전 문서

### 선행 작업
- shadow-parallel 시작은 Task 1 이후
- 최종 통합 마감은 Task 10 이후

### 병렬성
- 병행 테스트 레인 + 최종 통합 테스트 마감의 두 겹 구조

### 리스크
- 마지막에만 붙이면 품질이 떨어지고, 너무 일찍 단독으로 진행하면 가짜 테스트가 늘어난다.

### 완료 조건
- 각 task 산출물별 최소 검증이 존재한다.
- 최종 workflow 기준 통합 테스트가 존재한다.

### prompt 작성 시 강조점
- 각 task 완료 후 shadow test 추가
- 최종 통합 테스트는 Task 10 이후 별도 마감

---

## 8. 권장 구현 순서 정렬본
### Phase 0. 문서 기준선 고정
1. Task 0
2. Task 1

### Phase 1. 기반 레이어
1. Task 2
2. Task 3
3. Task 9a

### Phase 2. 규칙 기반 분석 백본
1. Task 4
2. Task 5

### Phase 3. LLM 계층
1. Task 6
2. Task 7

### Phase 4. 저장/전달/운영 검증
1. Task 8
2. Task 9b

### Phase 5. 파이프라인 조립
1. Task 10

### Phase 6. 테스트 마감
1. Task 11 shadow-parallel 지속
2. Task 11 최종 통합 마감

---

## 9. coding agent 프롬프트를 만들 때의 최소 템플릿
각 task 프롬프트는 가능하면 아래 형식을 사용한다.

```md
Task: <Task 번호와 이름>

목적:
- ...

이번 task의 구현 범위:
- ...

이번 task에서 구현하면 안 되는 것:
- ...

입력:
- ...

출력:
- ...

관련 문서:
- ...

완료 조건:
- ...

검증:
- 어떤 테스트/체크를 통과해야 하는지
```

---

## 10. 최종 요약
Backoffice Copilot v1 구현은  
`문서 기준선 고정 -> 공통 계약 -> 저장소/입력 기반 -> 규칙 기반 분석 -> LLM -> 저장/전달 -> 상태 분류 -> workflow 조립 -> 테스트 마감`  
순서로 가는 것이 가장 안전하다.

특히 아래 4개는 coding agent 프롬프트에서 반복해서 강조해야 한다.
- `match_id`가 유일한 run 식별자다.
- 정식 출력은 DB-first다.
- semantic mapping 계층은 별도 책임이다.
- backend/Discord/Grafana 실제 구현은 범위 밖이다.
