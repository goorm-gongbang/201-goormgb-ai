## 1. 문서 목적

이 문서는 Backoffice Copilot 사후판단의 데이터 계약을 **PostgreSQL 컬럼 설계 수준**으로 고정한다.

이 문서의 목적은 다음과 같다.

- 정식 저장 테이블 2개의 컬럼 계약을 확정한다.
- DTO와 DB 컬럼 매핑 관계를 확정한다.
- undocumented field 추가를 금지한다.

---

## 2. 공통 원칙

1. 정식 저장소는 PostgreSQL이다.
2. 정식 저장 테이블은 `post_review_runs`, `post_review_session_results` 2개만 사용한다.
3. `match_id`는 1차 구현에서 review run 식별자 역할을 겸한다.
4. 중간 과정(`SessionSummary`, `SessionAnalysis`, 후보 리스트)은 메모리 DTO로만 처리한다.
5. ClickHouse는 최소 구현 결과 저장소로 사용하지 않는다.
6. S3는 최소 구현 기본 저장소로 사용하지 않는다.
7. 본 문서에 없는 필드 추가는 금지한다.
8. row loader는 최소 row DTO만 읽고, `flowState`, `terminalReason`, `reasonCode`, `latest_*`, `terminal_outcome` 해석은 semantic mapping 계층이 담당한다.

---

## 3. PostgreSQL 컬럼 계약

## 3.1 post_review_runs

역할: 경기 1개의 사후판단 실행 요약(run-level)을 저장한다.

PK: `match_id`

| 컬럼명 | PostgreSQL 타입 | NULL 허용 | 기본값 | PK/UK/Index | 의미 | 왜 필요한가 |
| --- | --- | --- | --- | --- | --- | --- |
| `match_id` | `TEXT` | 아니오 | 없음 | PK(자동 Unique Index 포함) | 경기/실행 식별자 | 1차 구현에서 run 식별을 단일 키로 고정하기 위해 필요 |
| `window_start_ms` | `BIGINT` | 아니오 | 없음 | 인덱스 없음 | 분석 시작 시각(ms) | 실행 범위를 명확히 고정해 재현 가능한 검증을 하기 위해 필요 |
| `window_end_ms` | `BIGINT` | 아니오 | 없음 | 인덱스 없음 | 분석 종료 시각(ms) | 실행 범위를 명확히 고정해 재현 가능한 검증을 하기 위해 필요 |
| `candidate_count` | `INTEGER` | 아니오 | 없음 | 인덱스 없음 | 후보 세션 수 | 전체 분석 대상 규모를 기록하고 결과 해석 기준으로 사용하기 위해 필요 |
| `suspicious_count` | `INTEGER` | 아니오 | 없음 | 인덱스 없음 | 의심 세션 수 | 핵심 결과 수치를 기록하고 운영 판단 기준으로 사용하기 위해 필요 |
| `summary_text_json` | `JSONB` | 아니오 | 없음 | 인덱스 없음 | 3줄 요약 배열 JSON | 시간 구간 결과를 구조화된 텍스트로 저장하고 후속 export 생성 근거로 쓰기 위해 필요 |
| `status` | `TEXT` | 아니오 | 없음 | 인덱스 없음 | 실행 상태 | 실행 완료 상태를 운영/모니터링에서 일관되게 판정하기 위해 필요 |
| `created_at` | `TIMESTAMPTZ` | 아니오 | 없음 | 인덱스 없음 | 생성 시각 | 실행 생성 시점을 감사/추적하기 위해 필요 |
| `updated_at` | `TIMESTAMPTZ` | 아니오 | 없음 | 인덱스 없음 | 수정 시각 | 실행 상태/요약 갱신 시점을 추적하기 위해 필요 |

`status` 허용값 예시:
- `SUCCESS`
- `PARTIAL_SUCCESS`
- `FAILED`

추가 정합성 규칙:
- `candidate_count >= suspicious_count`
- `summary_text_json`은 길이 3 배열

---

## 3.2 post_review_session_results

역할: 경기 1개의 사후판단 결과 중 세션별 결과(session-level)를 저장한다.

PK: `(match_id, session_id)`

| 컬럼명 | PostgreSQL 타입 | NULL 허용 | 기본값 | PK/UK/Index | 의미 | 왜 필요한가 |
| --- | --- | --- | --- | --- | --- | --- |
| `match_id` | `TEXT` | 아니오 | 없음 | PK 구성 컬럼 | 어떤 실행에 속한 세션 결과인지 식별 | run 테이블과 세션 결과를 연결하기 위해 필요 |
| `session_id` | `TEXT` | 아니오 | 없음 | PK 구성 컬럼 | 세션 식별자 | 세션 결과를 run 내부에서 유일하게 식별하기 위해 필요 |
| `review_result` | `TEXT` | 아니오 | 없음 | 인덱스 없음 | 세션 최종 레이블 | 세션 분류 결과를 저장하고 전송 대상을 결정하기 위해 필요 |
| `evidence_summary` | `TEXT` | 아니오 | 없음 | 인덱스 없음 | 근거 요약 문장 | 사람이 결과를 확인할 최소 설명을 제공하기 위해 필요 |
| `session_analysis_json` | `JSONB` | 아니오 | 없음 | 인덱스 없음 | 규칙 기반 세션 분석 JSON | 레이블의 구조화 근거를 저장하고 재검증 가능성을 보장하기 위해 필요 |
| `backend_delivery_status` | `TEXT` | 아니오 | 없음 | 인덱스 없음 | 백엔드 전달 상태 | suspicious 전달 처리 상태를 세션 단위로 추적하기 위해 필요 |
| `created_at` | `TIMESTAMPTZ` | 아니오 | 없음 | 인덱스 없음 | 생성 시각 | 세션 결과 생성 시점을 추적하기 위해 필요 |
| `updated_at` | `TIMESTAMPTZ` | 아니오 | 없음 | 인덱스 없음 | 수정 시각 | 전달 상태 변경 시점을 추적하기 위해 필요 |

`review_result` 허용값:
- `NORMAL`
- `SUSPICIOUS`

`backend_delivery_status` 허용값 예시:
- `PENDING`
- `SENT`
- `FAILED`

운영 전송 규칙:
- DB에는 최소 구현상 `NORMAL`도 저장 가능
- 운영 전송 대상은 `SUSPICIOUS`만 허용

---

## 4. DTO 계약 (최소 구조)

## 4.1 DefenseAuditEventRow

```json
{
  "ts_ms": 1773817200000,
  "trace_id": "trace_001",
  "session_id": "sess_001",
  "event_type": "DEF_ORCH_EXECUTED",
  "payload": {}
}
```

`DefenseAuditEventRow`는 원시 입력 row 계약이다.  
이 DTO는 로딩 계약만 정의하며 `flowState`, `terminalReason`, `reasonCode` 해석이나 `latest_*`/`terminal_outcome` 계산 책임을 포함하지 않는다.

## 4.2 SessionSummary

```json
{
  "session_id": "sess_001",
  "seen_t1": true,
  "seen_t2": true,
  "block_event_count": 0,
  "vqa_fail_count": 1,
  "throttle_event_count": 1,
  "latest_flow_state": "F4M",
  "latest_action": "NONE",
  "latest_tier": "T1",
  "terminal_outcome": "NOT_BLOCKED"
}
```

## 4.3 SessionAnalysis

```json
{
  "session_id": "sess_001",
  "latest_flow_state": "F4M",
  "latest_action": "NONE",
  "latest_tier": "T1",
  "terminal_outcome": "NOT_BLOCKED",
  "seen_t1": true,
  "seen_t2": true,
  "vqa_fail_count": 1,
  "throttle_event_count": 1,
  "suspicious_signals": [
    "Reached T2 during session",
    "VQA failure observed"
  ],
  "timeline_summary": [
    "Session reached elevated tier",
    "VQA failure observed without final block"
  ],
  "needs_raw_fallback": false
}
```

## 4.4 LLM input DTO

```json
{
  "match_id": "match_123",
  "window_start_ms": 1773817200000,
  "window_end_ms": 1773824400000,
  "session_analysis": { ... },
  "task": {
    "labels": ["NORMAL", "SUSPICIOUS"],
    "required_fields": ["review_result", "evidence_summary"]
  }
}
```

## 4.5 LLM output DTO

```json
{
  "review_result": "SUSPICIOUS",
  "evidence_summary": "T2 흔적과 VQA 실패가 함께 관찰되어 사후 검토가 필요합니다."
}
```

## 4.6 Backend request DTO

```json
{
  "match_id": "match_123",
  "window_start_ms": 1773817200000,
  "window_end_ms": 1773824400000,
  "suspicious_count": 2,
  "candidates": [
    {
      "session_id": "sess_001",
      "review_result": "SUSPICIOUS",
      "reason_summary": "T2 흔적과 VQA 실패가 함께 관찰되어 검토 후보로 등록합니다."
    }
  ]
}
```

이 DTO는 우리 구현의 backend adapter 경계를 정의한다.  
외부 backend 서버/API 자체 구현은 이 문서 범위 밖이다.

## 4.7 Backend response DTO

```json
{
  "match_id": "match_123",
  "accepted_count": 2,
  "rejected_count": 0,
  "status": "ACCEPTED",
  "received_at": "2026-03-23T20:12:10+09:00"
}
```

---

## 5. DTO ↔ DB 컬럼 매핑

| DTO/필드 | DB 컬럼 매핑 | 매핑 설명 |
| --- | --- | --- |
| `LLM output.review_result` | `post_review_session_results.review_result` | LLM 세션 레이블 결과를 세션 row에 저장 |
| `LLM output.evidence_summary` | `post_review_session_results.evidence_summary` | LLM 근거 문장을 세션 row에 저장 |
| `SessionAnalysis` 전체 | `post_review_session_results.session_analysis_json` | 규칙 기반 분석 결과를 JSONB로 저장 |
| 집계 `candidate_count` | `post_review_runs.candidate_count` | 후보 집계 수를 run row에 저장 |
| 집계 `suspicious_count` | `post_review_runs.suspicious_count` | suspicious 집계 수를 run row에 저장 |
| 요약 3줄 | `post_review_runs.summary_text_json` | 시간 구간 요약 배열을 run row에 저장 |
| 실행 상태 | `post_review_runs.status` | 실행 성공/부분성공/실패 상태 저장 |
| backend 전송 상태 | `post_review_session_results.backend_delivery_status` | 세션별 전달 상태 저장 |

추가 매핑 규칙:
- `Backend request DTO`는 `post_review_session_results` 중 `review_result='SUSPICIOUS'` row만 변환해 생성한다.
- `Backend response DTO`는 응답 수신 후 대상 세션 row의 `backend_delivery_status` 갱신 근거로 사용한다.
- backend 계약은 adapter 경계까지만 정의하며 외부 backend 서버/API 동작 자체는 정의하지 않는다.

---

## 6. 구현 금지 사항

1. `review_run_id`를 별도 필수 식별자로 재도입
2. 중간 DTO용 DB 테이블 추가
3. 컬럼 계약 외 undocumented field 추가
4. ClickHouse/S3를 최소 구현 기본 결과 저장소로 사용
5. `NORMAL` 세션을 운영 전송 대상으로 포함

---

## 7. 최종 요약

최소 구현은 PostgreSQL 2테이블만 사용하며, 각 컬럼은 타입/NULL/기본값/키 계약을 고정한다.  
DTO는 메모리 처리 후 지정 컬럼으로 매핑 저장하고, backend 전송은 `SUSPICIOUS` 세션만 허용한다.
