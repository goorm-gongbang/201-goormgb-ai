# Canonical Audit Minimum Contract Draft

## 1. 문서 목적

이 문서는 현재 `decision_audit` 기준으로
ClickHouse `defense_audit_events` 최소 DDL 초안 작성에 바로 넘길 수 있는
입력 계약 초안을 잠근다.

이번 문서는 `32-storage-architecture.md`의 이상 상태를 그대로 선언하지 않는다.
현재 SSOT와 `audit.py`가 실제로 받쳐주는 범위만 최소 계약으로 고정하고,
부족한 항목은 gap으로만 기록한다.

---

## 2. 현재 코드와 목표 구조의 충돌 메모

먼저 충돌 사실을 드러낸다.

1. `32`는 `match_id`, `http_status`, `dedup_is_duplicate`, `policy rollout`, `VQA typed column`까지 포함한 ClickHouse raw fact를 기대한다.
2. 현재 [audit.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/audit.py)는 그 수준의 top-level typed field를 일관되게 쓰지 않는다.
3. 현재 canonical audit row shape는 최소 두 종류다.
4. evaluate row:
   - `ts_ms`, `session_id`, `trace_id`, `request_id`, `correlation_id`, `flow_state`, `event_type=EVALUATE`, `defense_tier`, `action`, `reason_code`, `policy_version`, `decision_id`, `risk_score`, `rule_hits`, `path`, `method`, `allow`, `runtime_state`, `telemetry_features`
5. challenge row:
   - `ts_ms`, `session_id`, `challenge_id`, `event_type`, `payload`
6. 따라서 현재는 `trace_id`, `flow_state`, `policy_version`, `risk_tier`, `action`, `reason_code`가 모든 row에서 보장되지 않는다.
7. SSOT의 `decision_audit.required_min_schema`는 `traceId`, `flowState`, `serverDecision`, `result` 구조를 요구하지만 현재 `audit.py`는 snake_case top-level + challenge payload 분리 구조라 1:1 정합이 아니다.
8. `31-observability-merge-strategy.md`의 현재 기준 안전한 join은 여전히 `session_id + 시간 구간`이다.
9. 테스트 탐색 결과 canonical audit payload 계약을 직접 잠그는 관련 테스트 파일은 찾지 못했다.

이번 문서는 위 충돌을 숨기지 않고,
현재 기준으로 안전한 최소 계약만 확정한다.

---

## 3. 최소 typed field 목록

아래 목록은 다음 task의 `defense_audit_events` 최소 DDL 초안에서
우선 typed column으로 뽑아도 되는 최소 집합이다.

### 3.1 필수 non-null typed field

이 3개만 현재 `audit.py` 두 row shape 모두에서 즉시 매핑 가능하다.

| field | status | 현재 소스 | 메모 |
| --- | --- | --- | --- |
| `ts_ms` | required | evaluate row / challenge row 공통 | 시간축, day partition, window filter의 최소 키 |
| `session_id` | required | evaluate row / challenge row 공통 | 현재 기준 가장 안전한 운영 join 키 |
| `event_type` | required | evaluate row / challenge row 공통 | 이벤트 분류 최소 축 |

### 3.2 nullable typed field

이 필드들은 지금 바로 typed column으로 둘 수 있지만,
모든 canonical audit row에서 non-null 보장은 못 한다.

| field | nullable | 현재 소스 | 메모 |
| --- | --- | --- | --- |
| `trace_id` | yes | evaluate row만 top-level 보장 | challenge row에는 현재 없음 |
| `challenge_id` | yes | challenge row top-level | evaluate row에는 없음 |
| `flow_state` | yes | evaluate row top-level | challenge row에서는 payload 안에도 일관 보장되지 않음 |
| `risk_tier` | yes | evaluate row의 `defense_tier` | 필드명 정규화 필요 |
| `action` | yes | evaluate row top-level | challenge row에서는 payload 파생이라 이번 최소 계약에서는 보장 안 함. 값 enum도 후속 정규화 필요 |
| `reason_code` | yes | evaluate row top-level | challenge row는 payload 구조가 이벤트별로 다름 |
| `policy_version` | yes | evaluate row top-level | challenge row에는 현재 없음 |

### 3.3 이번 task에서 typed field로 확정하지 않는 항목

아래는 `32`에서 중요하지만 이번 task에서는 gap 또는 JSON 보존 영역으로만 둔다.

- `match_id`
- `http_status`
- `dedup_is_duplicate`
- `request_id`
- `correlation_id`
- `request_meta` 세부 필드
- `requested_policy_version`
- `rollout_stage`
- `base_policy_version`
- `candidate_policy_version`
- `challenge_result`
- `challenge_reason_code`
- `vqa_attempt_score`
- `vqa_terminal`

이 항목들은 현재 SSOT 또는 코드의 top-level 보장이 약하거나,
event subtype마다 위치가 달라서 다음 단계에서 바로 non-ambiguous typed contract로 잠그기 어렵다.

---

## 4. JSON 보존 컬럼 후보 목록

원칙은 단순하다.
typed로 확정하지 않은 나머지는 JSON으로 보존한다.

### 4.1 최소 권장안

| JSON column candidate | 보존 범위 | 메모 |
| --- | --- | --- |
| `raw_payload_json` | typed field를 제외한 나머지 원본 row 내용 | 다음 task의 최소 DDL에서 가장 안전한 기본안 |

### 4.2 `raw_payload_json`에 남겨야 하는 현재 후보

- evaluate row의 `runtime_state`
- evaluate row의 `telemetry_features`
- evaluate row의 `request_id`
- evaluate row의 `correlation_id`
- evaluate row의 `decision_id`
- evaluate row의 `risk_score`
- evaluate row의 `rule_hits`
- evaluate row의 `path`
- evaluate row의 `method`
- evaluate row의 `allow`
- challenge row의 `payload` 전체

### 4.3 이번 task에서 분리 컬럼으로 확정하지 않는 JSON 영역

`32`의 이상 구조인 아래 분리 JSON 컬럼은 이번 task에서 아직 확정하지 않는다.

- `request_meta_json`
- `guard_json`
- `analyzer_json`
- `planner_json`
- `orchestrator_json`
- `challenge_json`
- `vqa_json`

현재 `audit.py`는 그렇게 모듈별 JSON을 안정적으로 분리해 기록하지 않기 때문이다.
이번 최소 계약에서는 `raw_payload_json` 1개가 더 안전하다.

---

## 5. 현재 코드와의 gap 메모

### 5.1 event_type taxonomy gap

- SSOT의 authoritative eventType는 `DEF_ORCH_EXECUTED`, `DEF_PLAN_COMPUTED`, `S3_CHALLENGE_RESULT` 같은 runtime catalog를 전제한다.
- 현재 `audit.py`는 evaluate row에 `EVALUATE`를 쓰고,
  challenge row에는 `CHALLENGE_ISSUED`, `CHALLENGE_VERIFIED` 같은 별도 taxonomy를 쓴다.
- 따라서 다음 task의 DDL은 현재 event_type 값을 그대로 수용하되,
  event catalog 정규화는 별도 후속 task로 분리하는 것이 안전하다.

### 5.2 schema shape gap

- SSOT는 `serverDecision`, `result`, `dedup` 같은 nested canonical shape를 전제한다.
- 현재 `audit.py`는 evaluate row를 flat snake_case top-level로 쓰고,
  challenge row는 `payload` object 하나에 세부값을 넣는다.
- 따라서 typed extractor는 현재 row shape를 기준으로 설계해야 하며,
  SSOT shape 강제는 후속 canonical normalization task가 필요하다.

### 5.3 action semantic gap

- 현재 evaluate row의 `action`은 `NONE`, `CHALLENGE`, `THROTTLE`, `GATE`, `BLOCK` 계열이다.
- SSOT/target 문맥은 `NONE`, `THROTTLE`, `REQUIRE_S3`, `BLOCK` 계열을 더 강하게 전제한다.
- 따라서 이번 최소 계약에서는 `action`을 nullable typed column으로만 두고,
  enum 정규화나 의미 치환은 별도 후속 task로 분리한다.

### 5.4 match-centric gap

- `32`는 `match_id` 중심 정렬/조회 구조를 전제한다.
- 현재 `main.py`는 경로 파싱, state key, challenge payload 수준에서는 `match_id`를 다루지만,
  canonical audit top-level typed field로는 일관 보장하지 않는다.
- 그래서 지금 기준 기본 join/key는 `match_id`가 아니라 `session_id + 시간 구간`이다.

### 5.5 challenge / VQA typed gap

- 현재 challenge row payload 안에는 `result`, `reasonCodes`, `vqaAttemptScore`, `featureSummary`, `matchId` 같은 값이 들어갈 수 있다.
- 하지만 이벤트별 payload key가 고정되어 있지 않고,
  evaluate row와 합쳐 동일 typed contract로 잠그기에는 아직 이르다.
- 따라서 이번 task에서는 JSON 보존만 허용하고 typed 승격은 보류한다.

### 5.6 observability warehouse gap

- `32`는 ClickHouse `defense_audit_events`를 canonical warehouse로 본다.
- 현재 구현은 local JSONL + S3 archive + PostgreSQL ETL 초안에 가깝다.
- 따라서 이번 문서는 ClickHouse 운영 상태를 설명하는 문서가 아니라,
  ClickHouse DDL 초안 입력 계약을 준비하는 문서로 읽어야 한다.

---

## 6. 현재 기준 안전한 join 관점 메모

현재 기준 가장 안전한 조인/탐색 관점은 아래다.

1. 기본 join key는 `session_id`다.
2. 시간 조건은 반드시 함께 붙인다.
3. 실무 표현은 `session_id + 시간 구간`으로 고정한다.
4. `trace_id`는 evaluate row drill-down에는 유용하지만 challenge row 전반의 공통 키로는 아직 약하다.
5. `match_id`는 현재 top-level 보장이 없으므로 기본 join key로 쓰지 않는다.
6. post-review 후보 선택이나 운영 병합도 당분간 `session_id + 시간 구간`을 우선 기준으로 본다.

즉 다음 task의 최소 DDL도
`session_id`와 `ts_ms` 기반 조회가 먼저 잘 되도록 설계하는 것이 맞다.

---

## 7. privacy / undocumented field 관점에서 넣지 말아야 할 필드

아래는 audit 최소 계약에 추가하면 안 된다.

### 7.1 SSOT privacy 금지 항목

- PII 전체
- 사용자 입력 원문
- DOM / selector / full HTML
- raw mouse trajectory / raw key events
- full IP address

### 7.2 현재 코드 문맥에서 추가 금지해야 할 민감 값

- `Authorization` 헤더 원문
- JWT 원문
- `cfToken` 원문
- `challenge_token`
- `active_challenge_token`
- 전체 request/response headers dump
- raw challenge pointer event array

### 7.3 undocumented field 취급 원칙

아래는 현재 일부 payload에 존재하더라도
이번 최소 typed contract로 승격하지 않는다.

- `catchTsMs`
- `catchXNorm`
- `catchYNorm`
- 상세 `featureSummary` 내부 원소
- runtime state 내부 세부 counter와 임시 상태 전부

이 값들은 privacy 또는 schema stability 검토 없이
다음 DDL의 typed column으로 올리면 안 된다.

---

## 8. 다음 task에 바로 넘길 입력

다음 task인 ClickHouse `defense_audit_events` 최소 DDL 초안 작성에는 아래만 넘기면 된다.

1. non-null typed field:
   - `ts_ms`
   - `session_id`
   - `event_type`
2. nullable typed field:
   - `trace_id`
   - `challenge_id`
   - `flow_state`
   - `risk_tier`
   - `action`
   - `reason_code`
   - `policy_version`
3. JSON preservation:
   - `raw_payload_json`
4. join guidance:
   - 기본 조회/병합은 `session_id + ts_ms window`
5. explicit gaps:
   - `match_id`, `http_status`, `dedup_is_duplicate`, rollout fields, VQA typed fields는 이번 DDL 최소안에서 강제하지 않음

---

## 9. 검증 메모

수동 검토 기준은 아래였다.

- `32-storage-architecture.md`
  - typed column 우선 원칙은 유지하되, 현재 코드가 못 받치는 항목은 gap으로만 남겼다.
- `33-docs-vs-current-code-gap-analysis.md`
  - 현재가 과도기 구조이며 `match_id`보다 `session_id + 시간 구간`이 안전하다는 설명과 맞춘다.
- `31-observability-merge-strategy.md`
  - 외부 소비와 병합 기준을 현재 현실에 맞게 `session_id + 시간 구간`으로 유지했다.
- `defense_observability_ssot.yaml`
  - privacy 금지 규칙과 canonical audit 의미를 유지했다.
- `audit.py`, `main.py`
  - 현재 실제 payload shape에서 즉시 매핑 가능한 필드만 최소 계약에 포함했다.

테스트 메모:

- canonical audit 최소 계약을 잠그는 직접 테스트 파일은 현재 찾지 못했다.
- 이번 task에서는 새 테스트를 추가하지 않았다.
