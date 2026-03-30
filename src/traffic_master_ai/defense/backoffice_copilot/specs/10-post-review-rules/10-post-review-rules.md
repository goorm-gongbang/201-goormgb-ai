## 1. 문서 목적

이 문서는 Backoffice Copilot 사후 판단 파이프라인의 도메인 규칙을 정의한다.

핵심 목적은 다음과 같다.

- 후보 세션 추출 규칙을 고정한다.
- 세션 분석 생성 규칙을 고정한다.
- raw fallback 사용 규칙을 고정한다.
- LLM 판단 규칙과 backend 전달 규칙을 고정한다.

스키마의 필드 상세 정의(의미/필요 이유)는 `21-data-contract.md`를 단일 기준으로 따른다.

---

## 2. 범위

### 2.1 포함 범위

- 지정 시간 구간 기준 후보 세션 추출
- 세션 타임라인 기반 분석 생성
- LLM을 통한 `review_result`/`evidence_summary` 생성
- suspicious 세션 backend 전달 규칙

### 2.2 제외 범위

- 실시간 Runtime 차단
- 제재 집행
- 정책 자동 변경
- 인프라 전송 구현 세부

---

## 3. 실행 식별자 및 저장 원칙

- 실행 식별자는 `match_id`를 사용한다.
- `review_run_id`는 1차 구현에서 사용하지 않는다.
- 정식 저장은 PostgreSQL 2개 테이블(`post_review_runs`, `post_review_session_results`)만 사용한다.
- 중간 산출물(`SessionSummary`, `SessionAnalysis`)은 메모리 DTO로만 처리한다.

---

## 4. 입력 소스 우선순위

1. `defense_audit_events` (기본 입력)
2. `decision_audit` (raw fallback용 제한 조회)

원칙:

- 시간 구간 필터는 항상 필수다.
- raw fallback은 대상 세션에만 좁은 범위로 조회한다.
- row loader는 최소 `DefenseAuditEventRow`만 읽는다.
- `flowState`, `terminalReason`, `reasonCode`, `latest_*`, `terminal_outcome` 해석은 semantic mapping 계층이 담당한다.
- event interpreter는 semantic mapping 결과를 사용해 집계/타임라인을 구성하며, 원시 row 해석 책임과 섞지 않는다.

---

## 5. 후보 세션 규칙

후보 세션은 아래 조건을 기준으로 추출한다.

1. `session_id` 존재
2. 시간 구간 내 이벤트 존재
3. `seen_t1` 또는 `seen_t2` 흔적 존재
4. `block_event_count == 0`
5. `latest_action != BLOCK`
6. `latest_tier != T3`
7. `terminal_outcome == NOT_BLOCKED`

후보 추출은 방어 로그 기준 규칙으로만 수행하며 `payment_success`, 결제 단계 도달 여부, payment stage 같은 표현을 hard filter로 사용하지 않는다.

후보 집계 DTO는 `SessionSummary` 최소 구조를 따른다.

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

---

## 6. 세션 분석 규칙

세션 분석은 후보 세션별 타임라인을 재구성해 `SessionAnalysis`를 생성한다.

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

원칙:

- `suspicious_signals`는 규칙 기반으로 생성한다.
- 근거 부족 시 `needs_raw_fallback=true`로 표시한다.

---

## 7. raw fallback 규칙

raw fallback은 아래 조건에서만 수행한다.

- payload 파싱 실패
- semantic mapping 이후에도 핵심 해석 필드 누락
- 근거 요약 생성에 필요한 문맥 부족

조회 제한:

- `session_id` 제한 필수
- 시간 구간 제한 필수
- 전량 스캔 금지

---

## 8. LLM 입력/출력 규칙

LLM 입력 DTO는 아래 구조를 따른다.

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

LLM 출력 DTO는 아래 구조를 따른다.

```json
{
  "review_result": "SUSPICIOUS",
  "evidence_summary": "T2 흔적과 VQA 실패가 함께 관찰되어 사후 검토가 필요합니다."
}
```

규칙:

- 허용 레이블: `NORMAL`, `SUSPICIOUS`
- 입력 근거 밖 추측 금지
- 실패 시 fallback으로 결과 생성 가능해야 함

---

## 9. backend 전달 규칙

backend request DTO는 아래 구조를 따른다.

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

backend response DTO는 아래 구조를 따른다.

```json
{
  "match_id": "match_123",
  "accepted_count": 2,
  "rejected_count": 0,
  "status": "ACCEPTED",
  "received_at": "2026-03-23T20:12:10+09:00"
}
```

규칙:

- backend로는 suspicious 세션만 전달한다.
- 우리 구현 범위는 `Backend request DTO` 생성, adapter 경계 정의, 응답 기반 `backend_delivery_status` 갱신까지다.
- 외부 backend 서버/API 구현은 범위 밖이다.
- Discord/Grafana 실제 연동도 범위 밖이다.
- 전달 상태는 `post_review_session_results.backend_delivery_status`에 저장한다.

---

## 10. 결과 저장 규칙

- run 결과는 `post_review_runs`에 저장한다.
- session 결과는 `post_review_session_results`에 저장한다.
- `suspicious_count`는 session table의 `SUSPICIOUS` 건수와 일치해야 한다.
- export 파일은 DB 저장 이후 후속 산출물이다.

---

## 11. 구현 금지 사항

1. `review_run_id`를 다시 필수 실행 키로 도입
2. 중간 산출물 테이블 추가
3. NORMAL 세션 backend 전달
4. undocumented field 추가
5. DB 저장 실패를 무시하고 완료 처리

---

## 12. 최종 요약

도메인 규칙의 핵심은 `match_id` 기준 단일 실행 식별, 최소 DTO, suspicious 전송 제한, PostgreSQL 2테이블 저장 우선이다.
