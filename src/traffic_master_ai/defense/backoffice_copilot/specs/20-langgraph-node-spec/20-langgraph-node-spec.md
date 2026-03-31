## 1. 문서 목적

이 문서는 Backoffice Copilot 사후 판단 파이프라인의 LangGraph 노드 구조와 노드 간 입출력 계약을 정의한다.

핵심 목적은 다음과 같다.

- 노드 수와 노드 책임을 고정한다.
- `match_id` 기반 실행 입력을 고정한다.
- Node 6 저장 책임을 PostgreSQL 2테이블 기준으로 고정한다.
- suspicious-only backend 전달 경계를 고정한다.

필드 의미/필요 이유 상세는 `21-data-contract.md`를 따른다.

---

## 2. 그래프 개요

그래프는 아래 6개 노드로 구성된다.

1. 입력 수집 노드
2. 후보 세션 추출 노드
3. 세션 분석 노드
4. 사후 판단 노드
5. 운영 요약 생성 노드
6. 결과 저장/전달 노드

그래프는 노드 간 직렬 흐름을 유지한다.

---

## 3. 그래프 시작 입력 계약

```json
{
  "match_id": "match_123",
  "window_start_ms": 1773817200000,
  "window_end_ms": 1773824400000,
  "limit": 1000,
  "use_raw_audit_fallback": true
}
```

규칙:

- `review_run_id`는 사용하지 않는다.
- 실행 식별자는 `match_id`로 고정한다.

---

## 4. 그래프 공통 상태(State) 계약

```json
{
  "match_id": "match_123",
  "window_start_ms": 1773817200000,
  "window_end_ms": 1773824400000,
  "limit": 1000,
  "use_raw_audit_fallback": true,

  "analysis_input": {},
  "candidate_sessions": [],
  "session_analysis_list": [],
  "review_results": [],
  "summary_text": [],

  "post_review_runs_row": {},
  "post_review_session_result_rows": [],
  "backend_request": {},
  "backend_response": {},

  "warnings": [],
  "errors": []
}
```

---

## 5. Node 1. 입력 수집 노드

### 목적

시간 구간 기준 입력 로그를 수집해 `analysis_input`을 준비한다.

### 입력

그래프 시작 입력 전체

### 출력

`analysis_input`

### 책임

- `defense_audit_events` 조회
- 시간 구간 필터 적용
- 원시 `DefenseAuditEventRow` 로딩
- raw fallback 가능 여부 기록

### 금지

- `flowState`/`terminalReason`/`reasonCode`/`latest_*` 의미 해석
- 후보 판정
- 최종 레이블 생성
- DB 저장

---

## 6. Node 2. 후보 세션 추출 노드

### 목적

사후 판단 대상 후보(`SessionSummary[]`)를 생성한다.

### 입력

`analysis_input`

### 출력

`candidate_sessions`

### 책임

- `session_id` 기준 집계
- semantic mapping 계층을 통해 `latest_*`, `terminal_outcome` 산출
- 후보 조건 적용
- 차단 세션 제외

### 규칙

- 후보 hard filter는 `seen_t1 || seen_t2`, `block_event_count == 0`, `latest_action != BLOCK`, `latest_tier != T3`, `terminal_outcome == NOT_BLOCKED`를 따른다.
- `payment_success`, 결제 단계 이후, payment stage 같은 표현을 후보 조건으로 사용하지 않는다.

### 금지

- 세션 상세 분석
- LLM 호출
- DB 저장

---

## 7. Node 3. 세션 분석 노드

### 목적

후보 세션별 `SessionAnalysis[]`를 생성한다.

### 입력

- `candidate_sessions`
- `analysis_input`
- 필요 시 제한적 raw fallback 조회 결과

### 출력

`session_analysis_list`

### 책임

- 타임라인 재구성
- suspicious 신호 생성
- `needs_raw_fallback` 판정
- semantic mapping 결과를 사용해 흐름 의미를 해석

### 책임 경계

- row loader는 raw row 로딩만 담당한다.
- semantic mapping 계층은 `flowState`, `terminalReason`, `reasonCode`, `latest_*` 해석만 담당한다.
- 세션 분석 노드는 semantic mapping 결과를 소비해 타임라인/신호를 조립한다.

### 병렬 처리

- 세션별 병렬 허용

---

## 8. Node 4. 사후 판단 노드

### 목적

세션별 `review_result`, `evidence_summary`를 생성한다.

### 입력

`session_analysis_list`

### 출력

`review_results`

### 책임

- LLM 입력 생성/호출
- 출력 검증
- fallback 적용

### 규칙

- 허용 레이블: `NORMAL`, `SUSPICIOUS`

### 병렬 처리

- 세션별 bounded concurrency 허용

---

## 9. Node 5. 운영 요약 생성 노드

### 목적

시간 구간 요약 3줄(`summary_text`)을 생성한다.

### 입력

- `review_results`
- `session_analysis_list`
- 기본 상태 필드

### 출력

`summary_text`

### 규칙

- 배열 길이 3 고정

---

## 10. Node 6. 결과 저장/전달 노드

### 목적

최종 결과를 PostgreSQL 2개 테이블에 저장하고, suspicious 세션만 backend로 전달한다.

### 입력

- `match_id`, `window_start_ms`, `window_end_ms`
- `candidate_sessions`
- `review_results`
- `session_analysis_list`
- `summary_text`

### 출력

- `post_review_runs_row`
- `post_review_session_result_rows`
- `backend_request`
- `backend_response`(전달 수행 시)

### 책임

- `post_review_runs` row 조립/저장
- `post_review_session_results` row 조립/저장
- suspicious 세션만 `Backend request DTO` 생성
- backend adapter 경계로 전달
- 전달 결과를 `backend_delivery_status`에 반영
- 필요 시 export 파일 후속 생성

### 범위 제한

- 외부 backend 서버/API 자체 구현은 범위 밖이다.
- Discord/Grafana 실제 연동은 범위 밖이다.

### DB 컬럼 매핑(요약)

| 소스 데이터 | 저장 대상 컬럼 |
| --- | --- |
| `match_id` | `post_review_runs.match_id`, `post_review_session_results.match_id` |
| `window_start_ms`, `window_end_ms` | `post_review_runs.window_start_ms`, `post_review_runs.window_end_ms` |
| 후보 집계 수 | `post_review_runs.candidate_count` |
| suspicious 집계 수 | `post_review_runs.suspicious_count` |
| 요약 3줄 | `post_review_runs.summary_text_json` |
| 실행 상태 | `post_review_runs.status` |
| `review_result` | `post_review_session_results.review_result` |
| `evidence_summary` | `post_review_session_results.evidence_summary` |
| `SessionAnalysis` 객체 | `post_review_session_results.session_analysis_json` |
| backend 전달 상태 | `post_review_session_results.backend_delivery_status` |

### 필수 저장 규칙

1. `post_review_runs` 저장 성공
2. `post_review_session_results` 저장 성공
3. `suspicious_count` 정합성 유지
4. 전달 대상은 suspicious 세션만 허용

### 실패 처리

- DB 저장 실패는 치명 오류
- backend 전달 실패는 상태 기록 후 정책에 따라 재시도 가능
- export 실패는 정책에 따라 경고 처리 가능

---

## 11. 노드 연결 규칙

1. 입력 수집
2. 후보 세션 추출
3. 세션 분석
4. 사후 판단
5. 운영 요약 생성
6. 결과 저장/전달

연결:

- Node1 → Node2
- Node2 → Node3
- Node3 → Node4
- Node4 → Node5
- Node4 + Node5 → Node6

---

## 12. 구현 금지 사항

1. 노드 수 임의 변경
2. `review_run_id` 재도입
3. 중간 테이블 추가 저장
4. NORMAL 세션 backend 전달
5. DB 저장 실패 무시

---

## 13. 최종 요약

그래프 구조는 유지하되 실행 식별자는 `match_id`로 통일하고, Node 6에서 PostgreSQL 2테이블 저장을 최우선으로 처리하며 suspicious 세션만 backend 전달한다.
