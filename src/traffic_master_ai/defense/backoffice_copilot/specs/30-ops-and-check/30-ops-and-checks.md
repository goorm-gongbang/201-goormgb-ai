## 1. 문서 목적

이 문서는 Backoffice Copilot 운영/검증 규칙을 **PostgreSQL 컬럼 검증 수준**으로 정의한다.

핵심 목적:

- DB 저장 성공을 최우선 검증한다.
- 컬럼 타입/NULL/허용값/PK 충돌을 검증한다.
- JSON 컬럼 구조(`summary_text_json`, `session_analysis_json`)를 검증한다.
- export 검증은 DB 저장 이후 후속 단계로 다룬다.

관련 문서:

- `../00-core-rules/00-core-rules.md`: 최상위 운영/책임 분리 원칙
- `../10-post-review-rules/10-post-review-rules.md`: 후보/세션 분석/backend 전달 규칙
- `../11-review-output-rules/11-review-output-rules.md`: 정식 저장과 export 우선순위
- `../21-data-contract/21-data-contract.md`: 컬럼/DTO 계약
- `31-observability-merge-strategy.md`: Grafana/Discord 외부 소비 시 검증 포인트와 데이터 소스 분리 원칙

---

## 2. 운영 범위

포함:
- 입력/설정 사전 점검
- 단계별 처리 검증
- DB row 저장 검증(컬럼 수준)
- backend adapter 경계 전달 및 `backend_delivery_status` 검증
- fallback 검증
- export 후속 검증

제외:
- 외부 backend 서버/API 구현 검증
- Discord/Grafana 실제 연동 검증
- 인프라 배포
- DB 물리 튜닝
- LLM 모델 선택

---

## 3. 실행 전 점검

1. PostgreSQL 연결 가능
2. `post_review_runs`/`post_review_session_results` 쓰기 가능
3. `match_id`, `window_start_ms`, `window_end_ms` 유효
4. fallback 설정/semantic mapping 설정 존재
5. PK 충돌 처리 정책(upsert/retry/fail-fast) 명시

---

## 4. DB 저장 검증 (핵심)

## 4.1 post_review_runs row 검증

필수 검증:

| 검증 항목 | 기준 |
| --- | --- |
| row 존재 | `match_id` 기준 1 row 저장/갱신 성공 |
| PK 충돌 | 충돌 시 정책대로 처리되고 실행이 비정상 종료되지 않음 |
| 타입 검증 | `match_id(TEXT)`, `window_start_ms(BIGINT)`, `window_end_ms(BIGINT)`, `candidate_count(INTEGER)`, `suspicious_count(INTEGER)`, `summary_text_json(JSONB)`, `status(TEXT)`, `created_at/updated_at(TIMESTAMPTZ)` |
| NULL 검증 | 모든 필수 컬럼 NOT NULL 충족 |
| 허용값 검증 | `status ∈ {SUCCESS, PARTIAL_SUCCESS, FAILED}` |
| JSON 구조 검증 | `summary_text_json`이 길이 3 배열 |
| 수치 정합성 | `candidate_count >= suspicious_count` |

실패 기준:
- row 저장 실패
- 필수 컬럼 NULL 저장
- 타입 불일치 저장
- 허용값 외 status 저장

---

## 4.2 post_review_session_results row 검증

필수 검증:

| 검증 항목 | 기준 |
| --- | --- |
| row 존재 | 분석 완료 세션 기준 row 저장/갱신 성공 |
| PK 충돌 | `(match_id, session_id)` 충돌 처리 정책 준수 |
| 타입 검증 | `match_id(TEXT)`, `session_id(TEXT)`, `review_result(TEXT)`, `evidence_summary(TEXT)`, `session_analysis_json(JSONB)`, `backend_delivery_status(TEXT)`, `created_at/updated_at(TIMESTAMPTZ)` |
| NULL 검증 | 필수 컬럼 NOT NULL 충족 |
| 허용값 검증 | `review_result ∈ {NORMAL, SUSPICIOUS}` |
| 전달상태 검증 | `backend_delivery_status ∈ {PENDING, SENT, FAILED}` |
| JSON 구조 검증 | `session_analysis_json`이 SessionAnalysis 최소 구조를 포함 |

실패 기준:
- row 저장 실패
- PK 충돌 미처리
- 허용값 외 `review_result` 또는 `backend_delivery_status` 저장
- `session_analysis_json` 직렬화/구조 검증 실패

---

## 5. 전달 및 상태 검증

1. backend 요청 후보는 `review_result='SUSPICIOUS'` row만 사용
2. 우리 검증 범위는 `Backend request DTO` 생성, adapter 경계 호출, 응답 기반 상태 갱신까지다.
3. backend 응답 수신 후 대상 row의 `backend_delivery_status` 갱신
4. 전달 시도 이력이 있는데 `backend_delivery_status`가 비어 있으면 실패
5. `updated_at`은 상태 변경 시 갱신되어야 함

---

## 6. 단계별 처리 검증

1. 입력 수집: 시간 구간 필터 적용 여부, row loader가 raw row만 로딩하는지 검증
2. 후보 추출: `SessionSummary` 필드 생성 여부와 `payment_success` 없는 hard filter 적용 여부 검증
3. 세션 분석: semantic mapping이 `flowState`, `terminalReason`, `reasonCode`, `latest_*`를 해석하고 `SessionAnalysis` 필드/배열/fallback 플래그를 생성하는지 검증
4. 사후 판단: `review_result` 허용값과 `evidence_summary` 생성 여부

---

## 7. Fallback 검증

raw fallback:
- `needs_raw_fallback=true` 세션만 조회
- `session_id + time window` 제한 조회
- 전량 스캔 금지

LLM fallback:
- LLM 실패 시 `review_result`/`evidence_summary` 생성 가능
- fallback 사용 이력 추적 가능

---

## 8. export 검증(후속)

export는 DB 저장 이후 선택 검증이다.

검증 대상:
- `summary.json`
- `suspicious_sessions.jsonl`
- `suspicious_sessions.csv`

검증 기준:
1. export 집계가 DB 집계와 일치
2. suspicious export는 `SUSPICIOUS` row만 포함
3. export 실패만으로 DB 저장 성공 실행을 무조건 실패 처리하지 않음(운영 정책 적용)

---

## 9. 실패 허용 기준

허용:
- 일부 세션 분석 실패
- 일부 세션 LLM fallback
- suspicious 0건
- export 실패(정책 허용 시)

허용 불가:
- PostgreSQL 저장 실패
- 필수 컬럼 NULL/타입/허용값 위반
- PK 충돌 미처리로 인한 실행 중단

---

## 10. 최종 요약

운영 검증의 최우선은 PostgreSQL 2테이블 row 저장의 컬럼 정합성이다.  
`review_result/status/backend_delivery_status` 허용값과 JSON 컬럼 구조를 반드시 검증하고, export 검증은 DB 저장 이후 후속 단계로 처리한다.
