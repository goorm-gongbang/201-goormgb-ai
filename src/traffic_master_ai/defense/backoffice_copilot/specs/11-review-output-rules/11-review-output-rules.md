## 1. 문서 목적

이 문서는 Backoffice Copilot 최종 출력 계약을 정의한다.

핵심 원칙:

- 정식 출력은 PostgreSQL 2개 테이블 저장이다.
- export 파일은 DB 저장 이후 생성되는 부가 산출물이다.
- 컬럼 계약은 `21-data-contract.md`와 일치해야 한다.

---

## 2. 출력 우선순위

1. `post_review_runs` 저장
2. `post_review_session_results` 저장
3. 필요 시 export 생성(`summary.json`, `suspicious_sessions.jsonl`, `suspicious_sessions.csv`)

DB 저장 실패 상태에서 export 성공만으로 완료 처리하면 안 된다.

---

## 3. 정식 저장 출력 계약

## 3.1 post_review_runs

역할: match 단위 실행 요약 저장

PK: `match_id`

| 컬럼명 | 타입 | NULL | 기본값 | PK/UK/Index | 의미 | 왜 필요한가 |
| --- | --- | --- | --- | --- | --- | --- |
| `match_id` | `TEXT` | 아니오 | 없음 | PK | 실행 식별자 | run 단위 결과를 유일하게 식별하기 위해 필요 |
| `window_start_ms` | `BIGINT` | 아니오 | 없음 | 인덱스 없음 | 시작 시각 | 실행 시간 범위 고정을 위해 필요 |
| `window_end_ms` | `BIGINT` | 아니오 | 없음 | 인덱스 없음 | 종료 시각 | 실행 시간 범위 고정을 위해 필요 |
| `candidate_count` | `INTEGER` | 아니오 | 없음 | 인덱스 없음 | 후보 수 | 분석 대상 규모 기록에 필요 |
| `suspicious_count` | `INTEGER` | 아니오 | 없음 | 인덱스 없음 | 의심 수 | 핵심 결과 수치 기록에 필요 |
| `summary_text_json` | `JSONB` | 아니오 | 없음 | 인덱스 없음 | 3줄 요약 배열 | 운영 요약 및 export 생성 원천으로 필요 |
| `status` | `TEXT` | 아니오 | 없음 | 인덱스 없음 | 실행 상태 | 실행 성공/실패 판단에 필요 |
| `created_at` | `TIMESTAMPTZ` | 아니오 | 없음 | 인덱스 없음 | 생성 시각 | 감사 추적에 필요 |
| `updated_at` | `TIMESTAMPTZ` | 아니오 | 없음 | 인덱스 없음 | 수정 시각 | 상태 변경 추적에 필요 |

`status` 허용값 예시: `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`

---

## 3.2 post_review_session_results

역할: match 내부 세션 결과 저장

PK: `(match_id, session_id)`

| 컬럼명 | 타입 | NULL | 기본값 | PK/UK/Index | 의미 | 왜 필요한가 |
| --- | --- | --- | --- | --- | --- | --- |
| `match_id` | `TEXT` | 아니오 | 없음 | PK 구성 | 실행 식별자 | run 결과와 세션 결과 연결에 필요 |
| `session_id` | `TEXT` | 아니오 | 없음 | PK 구성 | 세션 식별자 | 세션 결과 유일 식별에 필요 |
| `review_result` | `TEXT` | 아니오 | 없음 | 인덱스 없음 | 최종 레이블 | 분류 결과 저장 및 전송 대상 판정에 필요 |
| `evidence_summary` | `TEXT` | 아니오 | 없음 | 인덱스 없음 | 근거 문장 | 운영 확인용 최소 설명에 필요 |
| `session_analysis_json` | `JSONB` | 아니오 | 없음 | 인덱스 없음 | 분석 JSON | 판단 근거 구조화 저장에 필요 |
| `backend_delivery_status` | `TEXT` | 아니오 | 없음 | 인덱스 없음 | 전달 상태 | suspicious 전송 처리 추적에 필요 |
| `created_at` | `TIMESTAMPTZ` | 아니오 | 없음 | 인덱스 없음 | 생성 시각 | 결과 생성 추적에 필요 |
| `updated_at` | `TIMESTAMPTZ` | 아니오 | 없음 | 인덱스 없음 | 수정 시각 | 전달 상태 갱신 추적에 필요 |

`review_result` 허용값: `NORMAL`, `SUSPICIOUS`  
`backend_delivery_status` 허용값 예시: `PENDING`, `SENT`, `FAILED`

운영 전송 규칙:
- DB에는 `NORMAL` 저장 가능
- 운영 전송 대상은 `SUSPICIOUS`만 허용

---

## 4. DB 컬럼 ↔ export 필드 매핑

## 4.1 summary.json 매핑

| export 필드 | DB 컬럼 | 매핑 규칙 |
| --- | --- | --- |
| `match_id` | `post_review_runs.match_id` | 1:1 매핑 |
| `window_start_ms` | `post_review_runs.window_start_ms` | 1:1 매핑 |
| `window_end_ms` | `post_review_runs.window_end_ms` | 1:1 매핑 |
| `total_candidate_sessions` | `post_review_runs.candidate_count` | 이름만 변환 |
| `suspicious_count` | `post_review_runs.suspicious_count` | 1:1 매핑 |
| `summary_text` | `post_review_runs.summary_text_json` | JSON 배열 그대로 사용 |
| `status` | `post_review_runs.status` | 1:1 매핑 |

## 4.2 suspicious_sessions.* 매핑

| export 필드 | DB 컬럼 | 매핑 규칙 |
| --- | --- | --- |
| `match_id` | `post_review_session_results.match_id` | 1:1 매핑 |
| `session_id` | `post_review_session_results.session_id` | 1:1 매핑 |
| `review_result` | `post_review_session_results.review_result` | 1:1 매핑 |
| `evidence_summary` | `post_review_session_results.evidence_summary` | 1:1 매핑 |
| `backend_delivery_status` | `post_review_session_results.backend_delivery_status` | 필요 시 포함 |
| `created_at` | `post_review_session_results.created_at` | 1:1 매핑 |
| `updated_at` | `post_review_session_results.updated_at` | 1:1 매핑 |

필터 규칙:
- suspicious export는 `review_result='SUSPICIOUS'` row만 포함

---

## 5. 출력 정합성 규칙

1. `post_review_runs.suspicious_count == post_review_session_results`의 `SUSPICIOUS` row 수
2. `summary_text_json`은 길이 3 배열
3. export 생성 시 DB 기반 집계와 row 수가 일치해야 함
4. `backend_delivery_status`는 전달 시도 세션에서 비어 있으면 안 됨

---

## 6. 구현 금지 사항

1. DB 저장 대신 export를 정식 저장으로 간주
2. 결과 저장 테이블 2개 외 추가
3. `review_result` 허용값 외 값 저장
4. `NORMAL` 세션 운영 전송
5. DB 저장 실패를 정상 완료로 처리

---

## 7. 최종 요약

최종 출력의 기준은 PostgreSQL 2개 테이블이며, export 파일은 DB row를 변환한 후속 산출물이다.  
운영 전송은 `SUSPICIOUS` 세션만 대상으로 한다.
