# Session Rollup / Match Rollup / Candidate View Minimum Contract

## 1. 문서 목적

이 문서는 Task 1의 canonical audit 최소 계약과
Task 2의 `defense_audit_events` 최소 raw fact DDL 초안을 입력으로 받아,

- `defense_session_rollups`
- `defense_match_rollups`
- `defense_post_review_candidates_v1`

의 최소 입력/출력 계약을 고정한다.

이번 문서는 SQL 구현이나 MV 최적화 문서가 아니다.
현재 코드와 Task 2 raw fact 범위에서
안전하게 잠글 수 있는 최소 계약만 다룬다.

---

## 2. 먼저 드러내는 충돌

현재 기준으로 아래 충돌이 있다.

1. `32`는 `match_id` 중심 session/match rollup을 전제한다.
2. Task 2 raw fact 초안은 `match_id`를 explicit gap으로 남겼다.
3. 현재 코드의 기본 안전 join은 여전히 `session_id + 시간 구간`이다.
4. 현재 challenge/VQA 경로 일부는 `session_id`에 plain sid가 아니라 `sid:matchId` 형태의 state key를 기록한다.
5. 따라서 현재 session 축도 완전한 canonical session identity라고 가정하면 안 된다.
6. `defense_match_rollups`는 목표 방향으로는 필요하지만, 현재 raw fact만으로는 fully reliable match axis를 보장하지 못한다.

즉 이번 문서는
`session rollup = 지금 바로 잠글 수 있는 1차 입력 계약`,
`match rollup = 목표 방향을 가진 최소 계약`,
`candidate view = selection layer`
로 읽어야 한다.

---

## 3. 계층별 역할 분리

| 계층 | canonical name | 최소 역할 | 이번 task에서 하지 않는 일 |
| --- | --- | --- | --- |
| raw fact | `defense_audit_events` | raw event 보존, drill-down, rollup 입력 | final result 저장, candidate 결정, policy control-plane 책임 |
| session rollup | `defense_session_rollups` | `session_id + window` 기준 Backoffice 1차 입력 요약 | final result 저장, 운영 상황판 전체 요약 |
| match rollup | `defense_match_rollups` | match/window 기준 운영 요약 | session drill-down, final result 저장 |
| candidate view | `defense_post_review_candidates_v1` | session rollup에서 post-review 대상 선별 | 정식 결과 저장, scoring engine 확장 |
| final result store | `post_review_runs`, `post_review_session_results` | 사후판단 결론 저장 | runtime observability aggregation |

핵심 원칙:

- raw fact / rollup / candidate / final result 저장소의 책임을 섞지 않는다.
- candidate view는 결과 저장소가 아니라 selection layer다.
- 이번 문서는 observability 축만 잠근다.

---

## 4. `defense_session_rollups` 최소 계약

### 4.1 역할

`defense_session_rollups`의 최소 역할은 아래다.

- Backoffice Copilot의 1차 입력
- 같은 `session_id`에 대한 window 내 raw event 요약
- candidate selection의 직접 입력

이 테이블은 PostgreSQL 최종 결과 저장소가 아니다.

### 4.2 최소 row key

현재 기준 최소 row key는 아래로 둔다.

- `window_start_ms`
- `window_end_ms`
- `session_id`

`match_id`는 아직 row key에 넣지 않는다.

### 4.3 최소 컬럼 목록

| column | type | required | 현재 raw fact 파생 가능 여부 | 메모 |
| --- | --- | --- | --- | --- |
| `window_start_ms` | `UInt64` | required | yes | rollup materialization 또는 조회 window 입력에서 결정 |
| `window_end_ms` | `UInt64` | required | yes | rollup materialization 또는 조회 window 입력에서 결정 |
| `session_id` | `String` | required | yes | Task 2 raw fact typed column에서 바로 집계 가능 |
| `first_ts_ms` | `UInt64` | required | yes | `min(ts_ms)` |
| `last_ts_ms` | `UInt64` | required | yes | `max(ts_ms)` |
| `event_count` | `UInt32` | required | yes | row count |
| `latest_flow_state` | `Nullable(String)` | nullable | yes | latest non-null `flow_state` |
| `latest_action` | `Nullable(String)` | nullable | yes | latest non-null `action` |
| `latest_risk_tier` | `Nullable(String)` | nullable | yes | latest non-null `risk_tier` |
| `latest_reason_code` | `Nullable(String)` | nullable | yes | latest non-null `reason_code` |
| `latest_policy_version` | `Nullable(String)` | nullable | yes | latest non-null `policy_version` |
| `throttle_action_count` | `UInt32` | required | yes | `action='THROTTLE'` count |
| `block_action_count` | `UInt32` | required | yes | `action='BLOCK'` count |
| `challenge_issue_count` | `UInt32` | required | yes | `event_type='CHALLENGE_ISSUED'` count |
| `challenge_verified_count` | `UInt32` | required | yes | `event_type='CHALLENGE_VERIFIED'` count |

### 4.4 이번 task에서 session rollup에 넣지 않는 항목

아래는 목표 방향으로는 유효하지만 이번 최소 계약에서는 제외한다.

- `match_id`
- `trace_count`
- `terminal_outcome`
- `challenge_pass_count`
- `challenge_fail_count`
- `challenge_halt_count`
- `turnstile_seen`
- VQA 관련 집계 전체
- dedup 관련 집계 전체
- rollout / policy comparison 필드 전체

제외 이유:

- Task 2 raw fact typed column만으로는 안정 파생이 약하다.
- 일부 값은 `raw_payload_json` 해석과 enum 정규화가 필요하다.
- 이번 task 목표는 Backoffice 1차 입력 최소 계약 잠금이지 분석 컬럼 확대가 아니다.

---

## 5. `defense_match_rollups` 최소 계약

### 5.1 역할

`defense_match_rollups`의 최소 역할은 아래다.

- 운영 요약 / 상황판용 match-window 집계
- Grafana 및 운영 배치의 상위 수준 요약 입력

이 테이블은 session drill-down 책임을 가져가지 않는다.

### 5.2 최소 row key

목표 방향 row key는 아래다.

- `window_start_ms`
- `window_end_ms`
- `match_id`

단, 현재 `match_id`는 explicit gap이다.
따라서 이 row key는 “목표 방향 계약”이며,
현재 구현 기준 안정성은 session rollup보다 낮다.

### 5.3 최소 컬럼 목록

| column | type | required | 현재 raw fact / session rollup 파생 가능 여부 | 메모 |
| --- | --- | --- | --- | --- |
| `window_start_ms` | `UInt64` | required | yes | 집계 window |
| `window_end_ms` | `UInt64` | required | yes | 집계 window |
| `match_id` | `Nullable(String)` | nullable | weak gap | 현재 top-level raw fact typed field 없음 |
| `session_count` | `UInt32` | required | partial | `match_id`가 확보될 때만 stable |
| `event_count` | `UInt32` | required | partial | `match_id` 기준 분모 확보 시 stable |
| `block_action_count` | `UInt32` | required | partial | `match_id` 기준 분류 시 stable |
| `throttle_action_count` | `UInt32` | required | partial | `match_id` 기준 분류 시 stable |
| `challenge_issue_count` | `UInt32` | required | partial | `match_id` 기준 분류 시 stable |
| `challenge_verified_count` | `UInt32` | required | partial | `match_id` 기준 분류 시 stable |
| `latest_policy_version` | `Nullable(String)` | nullable | partial | session rollup 또는 raw fact에서 파생 가능하지만 `match_id` 축 안정화가 선행돼야 함 |

### 5.4 match rollup explicit gap

아래는 현재 코드와의 핵심 공백이다.

- raw fact top-level `match_id` 부재
- 일부 challenge row의 `session_id`가 `sid:matchId` state key 형태로 기록됨
- `raw_payload_json` 또는 path 기반 보강 없이는 reliable match grouping이 어렵다

따라서 현재 단계에서
`defense_match_rollups`는 “필요한 최소 계약”까지만 잠그고,
실제 materialization 안정화는 후속 schema 보강 이후로 미룬다.

---

## 6. `defense_post_review_candidates_v1` 최소 계약

### 6.1 역할

`defense_post_review_candidates_v1`의 최소 역할은 아래다.

- `defense_session_rollups`에서 post-review 대상 session만 선별
- Backoffice Copilot 실행 단위에 넘길 입력 집합 제공

이 view는 정식 결과 저장소가 아니다.
이 view 자체가 suspicious verdict를 확정하지도 않는다.

### 6.2 최소 입력 계층

기본 입력은 `defense_session_rollups`다.

raw fact 직접 조회는 기본 경로가 아니라 fallback 성격으로만 본다.

### 6.3 최소 selection 기준

window 안에서 아래 조건 중 하나라도 만족하면 candidate로 포함한다.

1. `block_action_count > 0`
2. `challenge_issue_count > 0`
3. `challenge_verified_count > 0`
4. `throttle_action_count > 0`
5. `latest_action IS NOT NULL AND latest_action != 'NONE'`

이 기준은 “defensive signal이 전혀 없는 session은 제외한다”는 최소 filter다.
점수화, ranking, ML/LLM scoring 확장은 이번 범위 밖이다.

### 6.4 최소 출력 컬럼

| column | type | required | source |
| --- | --- | --- | --- |
| `window_start_ms` | `UInt64` | required | session rollup |
| `window_end_ms` | `UInt64` | required | session rollup |
| `session_id` | `String` | required | session rollup |
| `first_ts_ms` | `UInt64` | required | session rollup |
| `last_ts_ms` | `UInt64` | required | session rollup |
| `latest_action` | `Nullable(String)` | nullable | session rollup |
| `latest_risk_tier` | `Nullable(String)` | nullable | session rollup |
| `latest_reason_code` | `Nullable(String)` | nullable | session rollup |
| `latest_policy_version` | `Nullable(String)` | nullable | session rollup |
| `block_action_count` | `UInt32` | required | session rollup |
| `throttle_action_count` | `UInt32` | required | session rollup |
| `challenge_issue_count` | `UInt32` | required | session rollup |
| `challenge_verified_count` | `UInt32` | required | session rollup |
| `candidate_reason` | `String` | required | selection layer derived |

### 6.5 candidate view에서 하지 않는 일

- suspicious / benign 최종 판정 저장
- backend delivery 상태 저장
- evidence_summary 생성 및 저장
- PostgreSQL `post_review_*` 대체
- Discord payload 생성

---

## 7. 소비자와 비소비자

| 계층 | 소비자 | 비소비자 |
| --- | --- | --- |
| `defense_audit_events` | Grafana runtime drill-down, 운영 deep query, rollup builder | Discord 본문 소스, Backoffice 기본 selection 소스, final result store |
| `defense_session_rollups` | Backoffice Copilot 1차 입력, candidate view builder | Grafana 운영 상황판의 기본 요약 소스, Discord 본문 소스, final result store |
| `defense_match_rollups` | Grafana 운영 요약, 운영 batch/orchestration | Backoffice 기본 분석 입력, session drill-down, final result store |
| `defense_post_review_candidates_v1` | Backoffice selection stage, post-review 실행 오케스트레이션 | Grafana 기본 패널, Discord 본문 소스, final result store |
| `post_review_runs`, `post_review_session_results` | Discord, post-review 패널, backend delivery consumer | runtime observability rollup source |

메모:

- Grafana는 runtime 관측 쪽에서는 raw fact 또는 match rollup을 읽고,
  post-review 결과는 PostgreSQL `post_review_*`를 읽는다.
- Discord는 `post_review_*`를 본문으로 삼고 observability 계층은 보강 정보로만 붙인다.
- Backoffice Copilot은 raw fact 직접 조회보다 session rollup / candidate view 우선 원칙을 따른다.

---

## 8. 기본 join 기준과 현재 코드 gap 메모

### 8.1 현재 기준 기본 join

현재 기준 가장 안전한 join 방식은 아래다.

1. `session_id + 시간 구간`
2. session drill-down 시 `session_id`, `window_start_ms`, `window_end_ms`
3. raw fact 보강 시 동일 `session_id + ts_ms window`

이 기준은 Task 1, Task 2, `31`, `33`과 맞춘다.

### 8.2 현재 코드 gap

아래 공백은 이번 문서에서 숨기지 않는다.

1. `match_id`가 raw fact typed column으로 아직 잠기지 않았다.
2. `event_type` taxonomy가 SSOT authoritative catalog와 다르다.
3. `action` enum 의미가 target semantics와 완전히 정렬되지 않았다.
4. 일부 challenge/VQA row는 `session_id`에 `sid:matchId` state key를 기록한다.
5. challenge result, VQA result, dedup 집계는 현재 `raw_payload_json` 해석이나 추가 schema 보강 없이는 최소 계약으로 잠그기 어렵다.

따라서:

- session rollup은 stored `session_id` 기준으로 잠근다.
- match rollup은 목표 방향 계약으로만 남긴다.
- candidate view는 match-centric selection이 아니라 session/window selection으로 둔다.

---

## 9. observability 축을 어디까지 잠갔는가

이번 task는 observability 축을 아래까지만 잠근다.

- raw fact
- session rollup
- match rollup
- candidate view
- 각 계층의 소비자 / 비소비자
- 현재 기준 join 방식

이번 task에서 의도적으로 잠그지 않은 것은 아래다.

- PostgreSQL policy control-plane DDL
- rollout state authoritative schema
- Redis projection schema
- final result 저장소 schema 변경
- candidate scoring 확장
- Grafana / Discord 실제 구현

즉 Task 4가 PostgreSQL control-plane 최소 DDL 초안을 작성할 때,
이번 문서는 observability 계층의 read contract만 제공하고
control-plane schema 결정에는 간섭하지 않는다.

---

## 10. Task 4에 바로 넘길 입력

Task 4가 관측 축과 섞이지 않게 바로 사용할 입력은 아래다.

1. observability 계층 경계
   - raw fact = `defense_audit_events`
   - Backoffice 1차 입력 = `defense_session_rollups`
   - 운영 요약 = `defense_match_rollups`
   - selection layer = `defense_post_review_candidates_v1`
   - final result store = PostgreSQL `post_review_*`
2. 기본 join 규칙
   - `session_id + 시간 구간`
3. explicit gap
   - `match_id`
   - dedup
   - challenge result typed aggregation
   - VQA typed aggregation
   - rollout / policy comparison field
4. consumer boundary
   - Backoffice는 session rollup / candidate view 우선
   - Grafana는 match rollup 또는 raw fact + PostgreSQL post-review 결과 병행
   - Discord는 `post_review_*` 본문 + observability 보강

---

## 11. 검증 메모

수동 검토 기준은 아래였다.

- `32-storage-architecture.md`
  - session rollup / match rollup / candidate view의 역할 분리와 기본 소비자를 유지했다.
- `31-observability-merge-strategy.md`
  - `session_id + 시간 구간` 기본 병합 원칙과 소비자 분리를 유지했다.
- `04-canonical-audit-minimum-contract.md`
  - 현재 기준 안전 join과 `match_id` gap을 그대로 이어받았다.
- `05-defense-audit-events-minimum-ddl.md`
  - rollup 최소 컬럼이 Task 2 raw fact typed column에서 과도하게 벗어나지 않도록 제한했다.
- `audit.py`, `main.py`
  - 지금 당장 계산 가능한 필드와 future gap을 구분했다.

이번 task에서는 MV 생성, view 생성, SQL migration 적용, PostgreSQL control-plane 설계는 하지 않았다.
