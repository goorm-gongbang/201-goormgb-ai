# ClickHouse `defense_audit_events` Minimum DDL Draft

## 1. 문서 목적

이 문서는 Task 1 산출물인
`04-canonical-audit-minimum-contract.md`를 입력으로 받아
ClickHouse raw fact table `defense_audit_events`의 최소 DDL 초안을 고정한다.

이번 문서는 `32-storage-architecture.md`의 전체 이상 구조를 구현하지 않는다.
현재 `audit.py`와 `main.py`로 안정적으로 매핑 가능한 최소 raw fact table만 다룬다.

---

## 2. 먼저 드러내는 충돌

현재 기준으로 아래 충돌이 있다.

1. `32`는 `match_id`, `http_status`, `dedup_is_duplicate`, rollout 계열, VQA typed field까지 포함한 richer raw fact를 전제한다.
2. Task 1 최소 계약은 이번 단계에서 허용되는 typed field를 `ts_ms`, `session_id`, `event_type` + 일부 nullable field로 줄였다.
3. 현재 `audit.py` row shape는 evaluate row와 challenge row가 다르다.
4. 현재 `event_type` taxonomy는 SSOT authoritative event catalog와 다르다.
5. 현재 `runtime_state`에는 `user_id`, `active_challenge_token` 같은 값이 들어갈 수 있으므로, `raw_payload_json`은 원본 row blind copy가 아니라 privacy-safe sanitized JSON이어야 한다.

즉 이 DDL 초안은
“현재 코드에서 바로 적재 가능한 최소 fact shape”를 잠그는 문서이지,
“최종 canonical normalized schema”를 잠그는 문서가 아니다.

---

## 3. Raw Fact Table 역할과 적재 가정

### 3.1 역할

`defense_audit_events`의 이번 최소 역할은 아래만 다룬다.

- canonical audit row의 raw fact 저장
- `session_id + ts_ms window` 기준 drill-down
- 후속 session rollup / match rollup / candidate view의 입력 기반 제공
- replay / backfill 가능한 보존층 제공

### 3.2 적재 가정

이번 초안은 아래 적재 흐름을 전제로 한다.

1. 앱이 request path에서 canonical audit JSONL append
2. JSONL rotate
3. S3 archive upload
4. collector / ETL이 S3 또는 rotated file을 batch 읽기
5. privacy-safe sanitation 후 ClickHouse insert

즉 앱이 request path에서 ClickHouse에 row-by-row direct insert하는 구조는 전제하지 않는다.

---

## 4. 최소 DDL 초안

```sql
CREATE TABLE defense_audit_events
(
    ts_ms UInt64,
    session_id String,
    event_type String,

    trace_id Nullable(String),
    challenge_id Nullable(String),
    flow_state Nullable(String),
    risk_tier Nullable(String),
    action Nullable(String),
    reason_code Nullable(String),
    policy_version Nullable(String),

    raw_payload_json String
)
ENGINE = MergeTree
PARTITION BY toDate(fromUnixTimestamp64Milli(ts_ms))
ORDER BY (session_id, ts_ms, event_type);
```

DDL 해석 메모:

- `ts_ms`는 현재 audit 원본과 1:1로 맞추기 위해 epoch ms `UInt64`로 둔다.
- `raw_payload_json`은 JSON 보존 컬럼이지만 ClickHouse 버전 의존도를 줄이기 위해 최소 초안에서는 `String`으로 둔다.
- `raw_payload_json` 값은 JSON 직렬화 문자열이어야 하며, 빈 경우에도 `NULL` 대신 `'{}'`를 기본 입력으로 본다.
- `raw_payload_json`은 금지 필드 제거 후 payload만 보존해야 한다.

---

## 5. 컬럼 정의 표

### 5.1 non-null typed column

| column | ClickHouse type | required | 구분 | 현재 코드 매핑 여부 또는 gap |
| --- | --- | --- | --- | --- |
| `ts_ms` | `UInt64` | required | typed | `audit.py` evaluate row / challenge row 공통 top-level `ts_ms`에서 바로 매핑 가능 |
| `session_id` | `String` | required | typed | `audit.py` evaluate row / challenge row 공통 top-level `session_id`에서 바로 매핑 가능 |
| `event_type` | `String` | required | typed | `audit.py` evaluate row / challenge row 공통 top-level `event_type`에서 바로 매핑 가능. 단, SSOT catalog와 값 taxonomy gap 존재 |

### 5.2 nullable typed column

| column | ClickHouse type | required | 구분 | 현재 코드 매핑 여부 또는 gap |
| --- | --- | --- | --- | --- |
| `trace_id` | `Nullable(String)` | nullable | typed | evaluate row top-level `trace_id`에서 바로 매핑 가능. challenge row에는 없음 |
| `challenge_id` | `Nullable(String)` | nullable | typed | challenge row top-level `challenge_id`에서 바로 매핑 가능. evaluate row에는 없음 |
| `flow_state` | `Nullable(String)` | nullable | typed | evaluate row top-level `flow_state`에서 매핑 가능. challenge row에는 현재 안정 top-level 필드 없음 |
| `risk_tier` | `Nullable(String)` | nullable | typed | evaluate row top-level `defense_tier`를 rename 매핑해야 함 |
| `action` | `Nullable(String)` | nullable | typed | evaluate row top-level `action`에서 매핑 가능. 값 enum은 target semantics와 gap 존재 |
| `reason_code` | `Nullable(String)` | nullable | typed | evaluate row top-level `reason_code`에서 매핑 가능. challenge row는 payload 구조가 이벤트별로 달라 typed 승격 안 함 |
| `policy_version` | `Nullable(String)` | nullable | typed | evaluate row top-level `policy_version`에서 매핑 가능. challenge row에는 없음 |

### 5.3 JSON preservation column

| column | ClickHouse type | required | 구분 | 현재 코드 매핑 여부 또는 gap |
| --- | --- | --- | --- | --- |
| `raw_payload_json` | `String` | required | JSON preservation | typed column으로 분리하지 않은 나머지를 JSON 직렬화 문자열로 저장. 현재 코드는 바로 만들 수 있지만, insert 전 sanitation이 필요 |

---

## 6. `raw_payload_json` 보존 범위

### 6.1 보존 허용 범위

현재 기준 최소 보존 후보는 아래다.

- evaluate row의 `request_id`
- evaluate row의 `correlation_id`
- evaluate row의 `decision_id`
- evaluate row의 `risk_score`
- evaluate row의 `rule_hits`
- evaluate row의 `path`
- evaluate row의 `method`
- evaluate row의 `allow`
- evaluate row의 `telemetry_features`
- challenge row의 `payload`

### 6.2 조건부 보존 범위

아래는 blind copy 금지다.
보존이 필요하면 sanitation 이후에만 `raw_payload_json`으로 들어간다.

- evaluate row의 `runtime_state`

sanitation 이유:

- `RuntimeStateSnapshot`에는 `user_id`, `active_challenge_token` 같은 값이 들어갈 수 있다.
- Task 1 최소 계약의 privacy 금지 규칙과 그대로 충돌한다.
- 따라서 ETL은 `runtime_state` 전체 보존이 아니라
  허용 필드만 남기거나 아예 제외하는 방식으로 sanitize해야 한다.

### 6.3 보존 금지 범위

아래는 `raw_payload_json`에도 넣지 않는다.

- `Authorization` 헤더 원문
- JWT 원문
- `cfToken`
- `challenge_token`
- `active_challenge_token`
- 전체 request/response headers dump
- raw challenge pointer event array
- PII
- 사용자 입력 원문
- DOM / selector / full HTML
- raw mouse trajectory / raw key events
- full IP address

---

## 7. 파티션 키와 정렬 키 초안

### 7.1 partition key

```sql
PARTITION BY toDate(fromUnixTimestamp64Milli(ts_ms))
```

선정 이유:

- `32`의 일 단위 파티션 원칙과 맞는다.
- 현재 최소 계약의 필수 필드 `ts_ms`만으로 계산 가능하다.
- 별도 `event_date` derived column을 추가하지 않아도 된다.

### 7.2 order key

```sql
ORDER BY (session_id, ts_ms, event_type)
```

선정 이유:

- 현재 기준 안전한 조회/병합은 `session_id + ts_ms window`다.
- `event_type`을 끝에 두면 동일 세션 시간축 drill-down과 기본 필터에 무리가 없다.
- `trace_id`는 일부 row에서만 존재하므로 이번 최소안의 leading key로 두지 않는다.
- `match_id`는 아직 top-level 보장이 없으므로 order key에 넣지 않는다.

---

## 8. 현재 코드 기준 매핑 가능한 컬럼과 explicit gap

### 8.1 지금 바로 채울 수 있는 컬럼

- `ts_ms`
- `session_id`
- `event_type`
- `trace_id`
- `challenge_id`
- `flow_state`
- `risk_tier`
- `action`
- `reason_code`
- `policy_version`
- `raw_payload_json`

단, 아래 보정은 필요하다.

- `risk_tier`는 `defense_tier` rename 매핑이 필요하다.
- `raw_payload_json`은 typed field 제거 + privacy sanitation이 필요하다.

### 8.2 이번 task에서 DDL에 넣지 않는 explicit gap

아래는 후속 task로 넘긴다.

- `match_id`
- `http_status`
- `dedup_is_duplicate`
- `request_id` typed 승격
- `correlation_id` typed 승격
- `requested_policy_version`
- `rollout_stage`
- `base_policy_version`
- `candidate_policy_version`
- `challenge_result`
- `challenge_reason_code`
- `vqa_attempt_score`
- `vqa_terminal`

보류 이유:

- 현재 top-level 안정 매핑이 약하다.
- event subtype마다 위치가 다르다.
- `32`의 목표 구조에는 중요하지만 이번 최소 raw fact DDL 범위를 넘는다.

---

## 9. 현재 코드 및 문서와의 모순 방지 메모

### 9.1 `32`와의 관계

- typed column 우선 원칙은 유지한다.
- 다만 `32`의 richer typed field를 이번 DDL에 모두 넣지 않는다.
- 이번 DDL은 `32`의 Phase 0 raw fact minimum으로 읽어야 한다.

### 9.2 `33`과의 관계

- 현재 코드는 ClickHouse 미구현 과도기 구조라는 설명과 맞춘다.
- 기본 join은 `session_id + 시간 구간`이라는 현실을 그대로 반영한다.

### 9.3 `31`과의 관계

- Runtime 관측의 기본 read source는 `defense_audit_events`라는 방향과 맞춘다.
- post-review 병합 기준도 당분간 `session_id + 시간 구간`으로 유지한다.

### 9.4 SSOT와의 관계

- `decision_audit`가 증거 SSOT라는 원칙은 유지한다.
- 다만 current `audit.py` row shape가 SSOT canonical nested shape와 다르므로,
  이번 DDL은 current payload-compatible raw fact layer로 둔다.

---

## 10. 다음 task에 바로 넘길 입력

Task 3가 `defense_session_rollups`, `defense_match_rollups`,
`defense_post_review_candidates_v1` 계약을 정의할 때 바로 사용할 입력은 아래다.

1. raw fact 안정 column
   - `ts_ms`
   - `session_id`
   - `event_type`
   - `trace_id`
   - `challenge_id`
   - `flow_state`
   - `risk_tier`
   - `action`
   - `reason_code`
   - `policy_version`
2. raw JSON preservation
   - `raw_payload_json`
3. 기본 조회 규칙
   - `session_id + ts_ms window`
4. session rollup에 바로 쓸 수 있는 최소 축
   - 시간축
   - session 축
   - event_type 분포
   - risk_tier 분포
   - action 분포
   - reason_code 분포
5. 아직 raw fact 단계에서 약한 축
   - `match_id`
   - dedup
   - challenge result typed field
   - VQA typed field
   - rollout/policy comparison field

---

## 11. 검증 메모

수동 검토 기준은 아래였다.

- `04-canonical-audit-minimum-contract.md`
  - non-null typed / nullable typed / JSON preservation 분리를 그대로 반영했다.
- `32-storage-architecture.md`
  - raw fact table, 일 단위 파티션, batch/ETL insert 원칙과 충돌하지 않게 유지했다.
- `33-docs-vs-current-code-gap-analysis.md`
  - 현재 ClickHouse 미구현, `session_id + 시간 구간` 우선, `match_id` 약함을 그대로 반영했다.
- `31-observability-merge-strategy.md`
  - runtime 관측 기본 read source와 join 관점을 유지했다.
- `audit.py`, `main.py`
  - 현재 payload에서 바로 채울 수 있는 필드만 typed column으로 유지했다.

이번 task에서는 migration 실행, collector 구현, ClickHouse 연결, rollup 설계는 하지 않았다.
