# Repository and Adapter Boundary Minimum Draft

## 1. 문서 목적

이 문서는 Task 2~6에서 잠근
raw fact / rollup / control-plane / projection / env / failure 계약을 입력으로 받아,
구현 단계 직전의 repository / adapter 경계를 고정한다.

이번 문서는 아래만 다룬다.

- ClickHouse raw fact writer/reader 경계
- session rollup / candidate read model 경계
- PostgreSQL control-plane repository 경계
- PostgreSQL -> Redis projection adapter 경계
- runtime read adapter 경계
- S3 archive / replay source 경계

이번 문서는 실제 repository 코드, adapter 코드, DB connection 구현 문서가 아니다.

---

## 2. 먼저 드러내는 충돌

현재 기준으로 아래 충돌이 있다.

1. `32`는 ClickHouse warehouse, PostgreSQL control-plane, Redis runtime projection, S3 archive를 분리한다.
2. 현재 `etl_worker.py`는 S3 -> ClickHouse가 아니라 S3 -> PostgreSQL prototype이다.
3. 현재 `AuditWarehouse`는 ClickHouse repository가 아니라 local JSONL warehouse adapter다.
4. 현재 `loader.py`는 runtime read, Redis key read/write, file fallback을 한 군데에 같이 들고 있다.
5. PostgreSQL control-plane repository와 PostgreSQL -> Redis projection worker는 아직 없다.

따라서 이번 문서는
"현재 코드의 구조 설명"이 아니라
"현재 코드를 무리 없이 다음 단계로 분리하기 위한 boundary 초안"으로 읽어야 한다.

---

## 3. Boundary 기본 원칙

### 3.1 Repository 정의

이번 문서에서 repository는 아래를 뜻한다.

- 특정 저장소에 대한 읽기/쓰기 API
- 저장소별 schema / keyspace / table / object 경계를 감싼다
- domain rule을 결정하지 않는다

repository가 하면 안 되는 일:

- post-review candidate scoring
- rollout assignment 결정
- suspicious / benign 최종 판정
- privacy 정책 임의 변경

### 3.2 Adapter 정의

이번 문서에서 adapter는 아래를 뜻한다.

- storage contract와 domain/runtime contract 사이 변환
- canonical row shaping
- projection payload shaping
- query result를 read model DTO로 변환

adapter가 하면 안 되는 일:

- 저장소 transaction 정책 결정
- rollout 승인/거절 판단
- 운영 절차 자체 결정

### 3.3 저장소별 책임 재고정

- ClickHouse: observability warehouse
- PostgreSQL: authoritative control-plane / final result
- Redis: runtime projection / authority cache
- S3: archive / replay source

---

## 4. 전체 경계 맵

| 계층 | repository | adapter | 주 소비자 | 금지 책임 |
| --- | --- | --- | --- | --- |
| S3 archive | `S3AuditArchiveRepository` | `AuditArchiveObjectAdapter` | archive loop, replay worker | KPI 집계, candidate selection |
| ClickHouse raw fact | `ClickHouseAuditEventWriterRepository`, `ClickHouseAuditEventReadRepository` | `CanonicalAuditRowAdapter` | ingest worker, drill-down query | request path direct insert, post-review scoring |
| ClickHouse read model | `ClickHouseSessionRollupReadRepository`, `ClickHouseMatchRollupReadRepository`, `ClickHousePostReviewCandidateReadRepository` | `SessionRollupReadModelAdapter`, `PostReviewCandidateAdapter` | Backoffice Copilot, Grafana, ops batch | final result 저장, control-plane state 변경 |
| PostgreSQL control-plane | `PolicyVersionRepository`, `PolicyRolloutStateRepository`, `PolicyRolloutEventRepository`, `PolicyOptimizationRunRepository` | `PolicyDocumentAdapter`, `RolloutStateRowAdapter` | optimizer/admin workflow, projection worker | runtime request path read |
| PostgreSQL final result | `PostReviewResultRepository` | `PostReviewResultAdapter` | Backoffice result save, Discord/backend consumer | runtime observability aggregation |
| Redis projection | `RedisPolicyProjectionRepository` | `PolicyProjectionAdapter` | projection worker, runtime read adapter | authoritative history 저장 |
| runtime read path | none or thin `RuntimePolicyReadAdapter` over Redis repo | `RuntimePolicyReadAdapter` | request path | PostgreSQL direct read, projection repair |

---

## 5. ClickHouse Raw Fact 계층 경계

### 5.1 writer repository

이름:

- `ClickHouseAuditEventWriterRepository`

입력:

- sanitized canonical audit row batch
- target table name `defense_audit_events`

출력:

- inserted row count 또는 write success/failure

책임:

- raw fact batch insert
- partition/order key에 맞는 insert shape 유지
- storage-level write error 전달

금지 책임:

- `audit.py` raw payload 직접 파싱
- privacy 금지 필드 판단
- rollup 계산
- request path direct insert

### 5.2 reader repository

이름:

- `ClickHouseAuditEventReadRepository`

입력:

- `session_id`
- `ts_ms` window
- optional `event_type`

출력:

- raw fact row list

책임:

- drill-down 조회
- 운영 deep query 기본 조회

금지 책임:

- candidate selection
- final result 생성
- match reconstruction heuristic 내장

### 5.3 raw fact adapter

이름:

- `CanonicalAuditRowAdapter`

입력:

- JSONL audit row or `AuditEntry`

출력:

- `defense_audit_events` insert row

책임:

- Task 1/2 최소 typed field 매핑
- `risk_tier <- defense_tier` rename
- `raw_payload_json` sanitation

금지 책임:

- ClickHouse connection
- retry/backfill orchestration

---

## 6. Session Rollup / Candidate Read Model 경계

### 6.1 session rollup reader

이름:

- `ClickHouseSessionRollupReadRepository`

입력:

- `window_start_ms`
- `window_end_ms`
- optional session filters

출력:

- `defense_session_rollups` row list

책임:

- Backoffice Copilot 1차 입력 조회
- session/window 요약 조회

금지 책임:

- candidate scoring
- PostgreSQL final result 저장
- raw fact 재집계 로직 내장

### 6.2 candidate reader

이름:

- `ClickHousePostReviewCandidateReadRepository`

입력:

- `window_start_ms`
- `window_end_ms`
- optional paging/filter

출력:

- `defense_post_review_candidates_v1` row list

책임:

- candidate selection layer 결과 조회
- Backoffice post-review 실행 입력 제공

금지 책임:

- suspicious / benign 최종 판정
- Discord payload 생성

### 6.3 optional match rollup reader

이름:

- `ClickHouseMatchRollupReadRepository`

입력:

- `window_start_ms`
- `window_end_ms`
- optional `match_id`

출력:

- `defense_match_rollups` row list

책임:

- Grafana / ops summary read

금지 책임:

- session drill-down 대체
- `match_id` heuristic 보정 내장

### 6.4 read model adapter

이름:

- `SessionRollupReadModelAdapter`
- `PostReviewCandidateAdapter`

책임:

- ClickHouse row를 Backoffice read DTO로 변환
- nullable / typed field normalization

금지 책임:

- DB query 자체
- candidate selection 기준 변경

---

## 7. PostgreSQL Control-Plane Repository 경계

### 7.1 policy version repository

이름:

- `PolicyVersionRepository`

입력:

- `policy_version`
- `schema_version`
- `document_json`
- status/source/validation metadata

출력:

- stored row or lookup row

책임:

- `policy_versions` CRUD 중 create/read/update status 범위
- active/candidate version source row 조회

금지 책임:

- Redis projection write
- rollout assignment

### 7.2 rollout state repository

이름:

- `PolicyRolloutStateRepository`

입력:

- current authoritative rollout row

출력:

- current rollout row

책임:

- `policy_rollout_state` current row read/write
- source-of-control 제공

금지 책임:

- Redis projection ordering
- rollback guardrail 판단

### 7.3 rollout event repository

이름:

- `PolicyRolloutEventRepository`

입력:

- append-only rollout/rollback event row

출력:

- appended event ack

책임:

- `policy_rollout_events` append
- 운영 이력 보존

금지 책임:

- current rollout row 변경
- runtime current state 계산

### 7.4 optimization run repository

이름:

- `PolicyOptimizationRunRepository`

입력:

- optimization run metadata row

출력:

- stored run metadata

책임:

- `policy_optimization_runs` persistence

금지 책임:

- ClickHouse KPI 계산
- policy patch 생성

### 7.5 control-plane adapters

이름:

- `PolicyDocumentAdapter`
- `RolloutStateRowAdapter`

책임:

- `PolicySnapshot`/policy document <-> PostgreSQL row 변환
- `RolloutState` <-> PostgreSQL row 변환

금지 책임:

- repository transaction 관리
- Redis projection write

---

## 8. PostgreSQL -> Redis Projection Adapter 경계

### 8.1 projection repository

이름:

- `RedisPolicyProjectionRepository`

입력:

- key name
- JSON payload

출력:

- key write/delete result

책임:

- `tm:decision-policy:version:{policyVersion}`
- `tm:decision-policy:rollout-state`
- `tm:decision-policy:version-index`
  key 3종에 대한 read/write

금지 책임:

- authoritative source 결정
- projection ordering 판단
- rollout 승인/거절

### 8.2 projection adapter

이름:

- `PolicyProjectionAdapter`

입력:

- `policy_versions` source row
- `policy_rollout_state` current row

출력:

- Redis key 3종 payload

책임:

- version doc payload shaping
- rollout-state minimum payload shaping
- version-index derivation

금지 책임:

- PostgreSQL query
- Redis network write
- retry scheduler

### 8.3 projection worker orchestration boundary

최소 호출 관계:

1. `PolicyVersionRepository`에서 referenced version doc read
2. `PolicyRolloutStateRepository`에서 current row read
3. `PolicyProjectionAdapter`로 Redis payload 생성
4. `RedisPolicyProjectionRepository`로 version docs -> rollout-state -> version-index 순서 write
5. 실패 시 retry/reconcile enqueue

worker가 하지 않는 일:

- runtime request path serve
- ClickHouse effect measurement

---

## 9. Runtime Read Adapter 경계

### 9.1 runtime policy read adapter

이름:

- `RuntimePolicyReadAdapter`

입력:

- `session_id`
- Redis projection keys
- rollout salt

출력:

- resolved `PolicySnapshot`
- optional current rollout-state snapshot

책임:

- Redis projection read
- `resolve_policy_version()` 호출에 필요한 minimum field 제공
- parse failure 시 fail-safe fallback 연결

금지 책임:

- PostgreSQL direct read
- projection repair
- rollout state update

### 9.2 current code relation

현재 `PolicyLoader`는 아래가 섞여 있다.

- Redis key read
- file fallback
- rollout resolution
- document parse/validation

후속 구현에서는 이를 전부 갈라 쓰되,
runtime read 원칙은 유지한다.

즉:

- request path는 `RuntimePolicyReadAdapter`만 호출
- adapter 내부에서만 Redis projection을 읽음
- PostgreSQL repository는 request path에 들어오지 않음

---

## 10. S3 Archive / Replay Source 경계

### 10.1 archive repository

이름:

- `S3AuditArchiveRepository`

입력:

- rotated audit file path

출력:

- uploaded object key

책임:

- rotated JSONL archive upload
- object list / get for replay source 제공

금지 책임:

- raw fact row parsing
- warehouse insert

### 10.2 replay source adapter

이름:

- `AuditArchiveObjectAdapter`

입력:

- local rotated file or S3 object bytes

출력:

- canonical audit JSON row iterable

책임:

- JSONL line split
- empty/invalid row 분리
- replay input iteration 제공

금지 책임:

- ClickHouse insert
- rollup recompute

### 10.3 ingest worker boundary

최소 호출 관계:

1. `S3AuditArchiveRepository`에서 object list/read
2. `AuditArchiveObjectAdapter`에서 row iteration
3. `CanonicalAuditRowAdapter`에서 raw fact row 변환
4. `ClickHouseAuditEventWriterRepository`에 batch write

현재 gap:

- current `etl_worker.py`는 4단계가 ClickHouse가 아니라 PostgreSQL prototype insert다.

---

## 11. Backoffice / Final Result 흐름 경계

### 11.1 Backoffice read path

Backoffice Copilot은 아래 순서를 우선한다.

1. `ClickHousePostReviewCandidateReadRepository`
2. 필요 시 `ClickHouseSessionRollupReadRepository`
3. 필요 시 `ClickHouseAuditEventReadRepository` drill-down

### 11.2 final result write path

Backoffice final verdict 저장은 observability repository가 아니라
별도 PostgreSQL final result repository가 맡아야 한다.

핵심 원칙:

- read model source는 ClickHouse
- final result authority는 PostgreSQL
- candidate view는 결과 저장소가 아니다

---

## 12. 이후 구현 순서 메모

구현 단계(Task 8+) 최소 순서는 아래가 안전하다.

1. `CanonicalAuditRowAdapter` 확정
2. `ClickHouseAuditEventWriterRepository` / `ClickHouseAuditEventReadRepository`
3. `ClickHouseSessionRollupReadRepository` / `ClickHousePostReviewCandidateReadRepository`
4. PostgreSQL control-plane repositories 4종
5. `PolicyProjectionAdapter` + `RedisPolicyProjectionRepository`
6. `RuntimePolicyReadAdapter`
7. `S3AuditArchiveRepository` + `AuditArchiveObjectAdapter`

이 순서를 쓰는 이유:

- raw fact writer가 먼저 있어야 warehouse read model이 의미를 가진다.
- authoritative PostgreSQL source가 먼저 있어야 projection adapter가 의미를 가진다.
- runtime read adapter는 projection target이 잠긴 뒤 분리하는 것이 안전하다.

---

## 13. 현재 코드와의 Gap 메모

### 13.1 observability side gap

- `AuditWarehouse`는 local JSONL warehouse adapter이지 ClickHouse repository가 아니다.
- `etl_worker.py`는 raw fact writer repository 대신 PostgreSQL prototype insert를 직접 수행한다.

### 13.2 control-plane side gap

- `loader.py`에 Redis key read/write와 file fallback이 섞여 있다.
- PostgreSQL control-plane repositories가 아직 없다.

### 13.3 projection side gap

- Redis projection repository와 projection adapter가 아직 분리돼 있지 않다.
- projection ordering/retry/reconcile을 담당할 worker 경계도 없다.

### 13.4 runtime side gap

- request path runtime은 여전히 `PolicyLoader`가 storage concern과 parse concern을 함께 가진다.
- 그래도 PostgreSQL direct read를 하지 않는다는 점은 목표 구조와 맞는다.

---

## 14. Task 8+에 바로 넘길 입력

구현 단계가 바로 사용할 인터페이스 수준 입력은 아래다.

1. ClickHouse raw fact
   - writer repo: sanitized canonical row batch -> `defense_audit_events`
   - reader repo: `session_id + ts_ms window` drill-down
2. ClickHouse read model
   - session rollup reader
   - candidate reader
   - optional match rollup reader
3. PostgreSQL control-plane
   - version/state/event/run repository 4종
4. Redis projection
   - key repo: version doc / rollout-state / version-index
   - adapter: PG row -> Redis payload
5. runtime read
   - Redis projection only
   - PostgreSQL direct read 금지
6. S3 replay
   - archive repo for upload/list/read
   - adapter for JSONL object -> canonical audit rows

---

## 15. 검증 메모

수동 검토 기준은 아래였다.

- `32-storage-architecture.md`
  - 저장소 책임 분리와 request path direct PostgreSQL 금지 원칙을 유지했다.
- Task 2~6 산출물
  - raw fact / rollup / control-plane / projection / env/failure 경계와 모순되지 않게 맞췄다.
- `etl_worker.py`
  - current S3 -> PostgreSQL prototype를 explicit gap으로 반영했다.
- `runtime.py`, `loader.py`, `keyspace.py`
  - runtime Redis-first, keyspace 고정, loader 혼합 책임을 현재 코드 gap으로 반영했다.
- `warehouse.py`
  - 현재 `AuditWarehouse`가 local JSONL adapter라는 점을 경계 문서에 반영했다.

테스트 메모:

- repository / adapter 경계를 직접 잠그는 관련 테스트 파일은 찾지 못했다.
- 이번 task에서는 새 테스트를 추가하지 않았다.
