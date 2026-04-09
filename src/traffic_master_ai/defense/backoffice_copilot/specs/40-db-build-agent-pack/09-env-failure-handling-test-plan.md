# Env, Failure Handling, and Test Plan Minimum Draft

## 1. 문서 목적

이 문서는 Task 1~5에서 잠근 DB/storage/projection 계약을
운영 가능한 최소 수준으로 이어주기 위해
env 요구사항, failure handling 규칙, test plan을 고정한다.

이번 문서는 아래만 다룬다.

- ClickHouse / PostgreSQL / Redis / S3 최소 env 계약
- env 누락 시 계층별 기대 동작
- ingest / projection / warehouse / control-plane 축의 failure handling 규칙
- retry / replay / backfill 필요 지점
- unit / contract / integration / smoke test 최소 계획

이번 문서는 실제 env wiring, retry worker 구현, integration test 코드 작성 문서가 아니다.

---

## 2. 먼저 드러내는 충돌

현재 기준으로 아래 충돌이 있다.

1. `32`는 `JSONL -> S3 -> ClickHouse`, `PostgreSQL(control plane) -> Redis(runtime projection)`을 전제한다.
2. 현재 코드의 실제 observability 적재 초안은 `JSONL -> S3 -> PostgreSQL ETL`이며 ClickHouse writer는 없다.
3. 현재 코드에는 PostgreSQL control-plane도, PostgreSQL -> Redis projection worker도 없다.
4. runtime state Redis는 non-CI 환경에서 `TM_REDIS_URL`을 강제하지만, policy runtime authority는 `RedisPolicyStore + FilePolicyStore fallback`으로 bootstrap/local dev fallback을 허용한다.
5. 관련 DB/storage integration test와 projection test는 아직 없다.

따라서 이번 문서는
"현재 구현된 운영 시스템 설명"이 아니라
"Task 7 이후 구현이 지켜야 할 최소 운영 계약과 현재 코드 gap 정리"로 읽어야 한다.

---

## 3. 계층별 운영 경계

이번 문서에서 다루는 계층은 아래다.

1. audit append / rotate / S3 archive
2. S3 archive -> warehouse ingest
3. PostgreSQL policy control-plane write
4. PostgreSQL -> Redis projection
5. runtime read path

핵심 원칙:

- Redis는 runtime authority이지만 authoritative history 저장소가 아니다.
- S3는 archive / replay source다.
- ClickHouse는 observability warehouse다.
- PostgreSQL은 post-review final result와 policy control-plane authority다.
- request path는 PostgreSQL과 ClickHouse를 직접 읽지 않는다.

---

## 4. 최소 Env 변수 목록

### 4.1 공통 표

| env | 계층 | required 여부 | 현재 코드 지원 여부 | 목적 | 누락 시 기대 동작 |
| --- | --- | --- | --- | --- | --- |
| `TM_DEFENSE_AUDIT_LOG_PATH` | audit append | optional | yes | 로컬 append-only JSONL 파일 경로 | 누락 시 `/tmp/logs/defense_decision_audit.jsonl` 기본값 사용 |
| `TM_S3_BUCKET` | S3 archive / ETL source | optional for local, required for archive/ETL | partial yes | rotated audit JSONL archive source bucket | 누락 시 S3 archiving 비활성, ETL worker 실행 불가 |
| `TM_S3_REGION` | S3 archive / ETL source | optional | partial yes | S3 client region 지정 | 누락 시 boto 기본 region resolution 사용 |
| `TM_S3_PREFIX` | S3 archive / ETL source | optional | yes | audit archive prefix | 누락 시 `ai-defense/audit/` 사용 |
| `TM_S3_ARCHIVE_INTERVAL_SECONDS` | audit rotate/upload | optional | yes | archive loop 주기 | 누락 시 `300` 사용 |
| `TM_PG_URL` | PostgreSQL result plane / control-plane / current ETL prototype | required for PG-backed workers | partial yes | PostgreSQL connection string | 누락 시 current ETL prototype skip, future PG control-plane/projection worker fail-fast |
| `TM_REDIS_URL` | runtime state / policy projection target | required in non-CI | yes | runtime Redis and projection target Redis connection | non-CI에서 누락 시 fail-fast, CI에서만 memory fallback 허용 |
| `TM_ROLLOUT_SALT` | policy selection | required for prod | partial yes | deterministic session assignment salt | 현재 코드는 빈 문자열 fallback, prod 계약상 명시 설정 권장 |
| `TM_POLICY_CACHE_SECONDS` | runtime policy loader | optional | yes | policy/rollout Redis read cache TTL | 누락 시 `5` 사용 |
| `TM_POLICY_STORE_PATH` | local bootstrap fallback | optional, dev-only | yes | file policy store 경로 | 누락 시 `/tmp/logs/policy_store.json` 사용 |
| `TM_CLICKHOUSE_URL` | ClickHouse warehouse ingest | required for target architecture | gap | ClickHouse connection string | 누락 시 ClickHouse ingest worker는 시작하지 않아야 하며 replay source는 S3에 남아야 함 |
| `TM_CLICKHOUSE_AUDIT_TABLE` | ClickHouse warehouse ingest | optional | gap | raw fact table name override | 누락 시 `defense_audit_events` 고정값 사용 |
| `TM_CLICKHOUSE_INGEST_BATCH_SIZE` | ClickHouse warehouse ingest | optional | gap | batch insert 크기 | 누락 시 구현 기본값 사용 |
| `TM_CLICKHOUSE_INGEST_TIMEOUT_MS` | ClickHouse warehouse ingest | optional | gap | ingest timeout | 누락 시 구현 기본값 사용 |
| `TM_PROJECTION_RETRY_MAX_ATTEMPTS` | PG -> Redis projection | optional | gap | projection retry 상한 | 누락 시 구현 기본값 사용 |
| `TM_PROJECTION_RETRY_BACKOFF_MS` | PG -> Redis projection | optional | gap | projection retry backoff | 누락 시 구현 기본값 사용 |

### 4.2 이번 task에서 env로 빼지 않는 것

- ClickHouse / PostgreSQL DDL 자체
- Redis key name
- canonical audit typed field 목록
- rollup / candidate selection 규칙

제외 이유:

- 이미 앞선 task에서 계약으로 잠갔고
- env로 빼면 schema drift만 늘어나기 때문이다.

---

## 5. Env 누락 시 계층별 기대 동작

### 5.1 audit append / rotate / S3 archive

- `TM_DEFENSE_AUDIT_LOG_PATH` 누락:
  - local default path 사용
  - request path는 계속 append 시도
- `TM_S3_BUCKET` 누락:
  - S3 archive loop는 비활성
  - local JSONL은 authoritative append log로 남음
- `TM_S3_REGION` 누락:
  - explicit failure로 보지 않고 SDK 기본 resolution 사용

### 5.2 S3 -> warehouse ingest

- `TM_S3_BUCKET` 누락:
  - ingest worker는 시작하지 않거나 즉시 종료해야 한다.
- `TM_CLICKHOUSE_URL` 누락:
  - target architecture 기준 ClickHouse ingest는 시작 금지
  - replay source는 S3 archive에 남아 있어야 한다.
- `TM_PG_URL` 누락:
  - current `etl_worker.py` Postgres prototype은 skip/fail-fast

### 5.3 PostgreSQL control-plane

- `TM_PG_URL` 누락:
  - policy control-plane writer / repository / projection source reader는 시작 금지
  - rollout state 변경은 authoritative write 없이 적용되면 안 된다.

### 5.4 PostgreSQL -> Redis projection

- `TM_PG_URL` 또는 `TM_REDIS_URL` 누락:
  - projection worker는 시작 금지
  - runtime은 기존 Redis 마지막 정상 projection만 읽는다.

### 5.5 runtime read path

- `TM_REDIS_URL` 누락:
  - current code 기준 non-CI는 fail-fast
  - CI에서만 in-memory fallback 허용
- `TM_ROLLOUT_SALT` 누락:
  - current code는 빈 문자열로 deterministic hash를 계속 계산한다.
  - prod 계약상 이는 weak config로 보고 env 명시를 요구한다.

---

## 6. 주요 실패 시나리오와 처리 원칙

### 6.1 audit append 실패

현재 코드 기준:

- `DefenseDecisionAuditLogger.log()` 자체는 append 실패를 내부에서 삼키지 않는다.
- d0_mvp runtime `_emit_audit()`는 append/collector 실패를 잡아 log만 남기고 request path를 계속 진행한다.

운영 원칙:

- request path를 audit append 실패 때문에 즉시 중단시키지 않는다.
- 하지만 failure는 반드시 log/metric으로 드러나야 한다.
- append 실패가 반복되면 local file path, disk 권한, disk full 상태를 우선 확인해야 한다.

### 6.2 audit rotate / S3 upload 실패

현재 코드 기준:

- rotate는 atomic rename 후 upload 시도
- upload 성공 시에만 rotated local file 삭제
- upload 실패 시 rotated file은 로컬에 남는다

운영 원칙:

- upload 실패는 숨기지 않는다.
- rotated local file은 retry / manual replay source로 보존한다.
- partial upload 이후 원본 삭제를 선행하면 안 된다.

### 6.3 S3 -> ClickHouse ingest 실패

현재 코드 gap:

- current worker는 ClickHouse가 아니라 PostgreSQL prototype이다.

운영 원칙:

- S3 object는 warehouse commit 성공 전 processed로 간주하지 않는다.
- ingest 실패 시 source-of-replay는 S3 object다.
- row-level schema mismatch와 connection failure를 분리해 기록한다.
- raw fact 재적재가 가능해야 하므로 idempotent ingest 전략이 필요하다.

### 6.4 PostgreSQL control-plane write 실패

운영 원칙:

- PostgreSQL authoritative write 실패 시 rollout 적용이나 Redis projection을 진행하지 않는다.
- optimizer / admin workflow는 write fail을 즉시 operator-visible failure로 올려야 한다.
- `policy_rollout_events`와 `policy_optimization_runs` 기록도 authoritative write 성공 순서와 섞이면 안 된다.

### 6.5 PostgreSQL -> Redis projection 실패

운영 원칙:

- truth는 PostgreSQL에 남아 있다.
- runtime은 stale Redis projection을 읽을 수 있다.
- 이 상태는 partial apply다.
- retry 또는 reconcile job으로 재투영해야 한다.
- rollout / rollback 운영 로그에는 projection failure와 stale-read 가능성을 남겨야 한다.

### 6.6 runtime read path failure

운영 원칙:

- runtime은 PostgreSQL direct read로 복구하지 않는다.
- Redis projection parse failure / eviction 시 baseline default policy 또는 file fallback은 fail-safe일 뿐이며, 정상 복구 경로는 projection repair다.
- non-CI 환경에서 `TM_REDIS_URL` 누락은 fail-fast가 맞다.

---

## 7. Replay / Retry / Backfill 필요 지점

### 7.1 retry 필요 지점

- rotated local audit file -> S3 upload 재시도
- PostgreSQL -> Redis projection 재시도
- ClickHouse batch ingest 재시도

### 7.2 replay / reconcile 필요 지점

- rotated local file에서 S3 archive 재업로드
- S3 archive에서 raw fact warehouse 재적재
- PostgreSQL control-plane에서 Redis key 3종 재투영

### 7.3 backfill 필요 지점

- `decision_audit JSONL` / rotated file -> S3 archive backfill
- S3 archive -> `defense_audit_events` raw fact backfill
- raw fact -> session rollup / match rollup / candidate recompute

핵심 원칙:

- backfill source-of-truth는 S3 archive 또는 PostgreSQL authoritative tables다.
- Redis는 backfill source가 아니다.
- rollup / candidate는 raw fact 재계산으로 복구해야지 앱 request log 재실행으로 복구하면 안 된다.

---

## 8. 테스트 계획

### 8.1 Unit Test 최소 계획

- audit logger:
  - `TM_DEFENSE_AUDIT_LOG_PATH` default path resolution
  - rotate 후 upload 성공/실패 시 local file 보존 규칙
- env parsing:
  - `TM_S3_BUCKET`, `TM_PG_URL`, `TM_REDIS_URL`, `TM_ROLLOUT_SALT`, `TM_POLICY_CACHE_SECONDS`
- runtime state / Redis builder:
  - non-CI에서 `TM_REDIS_URL` 누락 시 fail-fast
  - CI에서 memory fallback 허용
- policy projection payload:
  - version doc payload가 `schemaVersion + parameters + flags` shape인지
  - rollout-state payload가 minimum field만 유지하는지

### 8.2 Contract Test 최소 계획

- canonical audit -> raw fact mapping contract
- `defense_audit_events` DDL field mapping contract
- `policy_versions` / `policy_rollout_state` -> Redis key 3종 payload contract
- env required/optional matrix contract
- privacy 금지 필드가 audit / Redis projection payload에 승격되지 않는지 확인

### 8.3 Integration Test 최소 계획

- JSONL append -> rotate -> S3 stub 업로드 -> ingest worker 경로
- PostgreSQL control-plane row write -> projection worker -> Redis key update 경로
- runtime이 PostgreSQL 없이 Redis projection만 읽어 policy assignment 하는 경로
- Redis eviction 이후 reconcile job이 key를 복구하는 경로

주의:

- 현재 저장소에는 ClickHouse adapter, PG control-plane repo, projection worker가 없으므로 이 항목은 future integration test 계획이다.

### 8.4 Smoke Test 최소 계획

- required env가 모두 있을 때 서비스/worker가 기본 startup을 통과하는지
- `TM_S3_BUCKET` 없이 API가 기동되고 S3 archiving만 비활성화되는지
- non-CI에서 `TM_REDIS_URL` 누락 시 즉시 실패하는지
- projection worker가 PG/Redis 둘 다 연결 가능할 때 대상 key 3종을 채우는지
- ingest worker가 source bucket 접근 불가 시 즉시 실패를 기록하는지

---

## 9. Task 7 이후 구현 검증 기준

Task 7 이후 repository / adapter 경계를 구현할 때 최소 acceptance 기준은 아래다.

1. app request path는 ClickHouse / PostgreSQL을 직접 읽지 않는다.
2. audit raw source는 append-only JSONL 또는 그 archive에서 replay 가능하다.
3. warehouse ingest는 source delete 이전에 durable write 성공을 보장한다.
4. PostgreSQL control-plane write 실패 시 Redis projection이 선행되지 않는다.
5. Redis projection 손상 시 PostgreSQL authoritative source에서 재동기화할 수 있다.
6. env 누락 정책이 fail-fast와 fail-safe로 일관되게 나뉜다.

---

## 10. 현재 코드와의 Gap 메모

### 10.1 observability ingest gap

- `etl_worker.py`는 ClickHouse가 아니라 PostgreSQL prototype이다.
- current code에는 ClickHouse connection env, adapter, batch writer가 없다.

### 10.2 control-plane / projection gap

- PostgreSQL policy control-plane 4테이블이 없다.
- PostgreSQL -> Redis projection worker가 없다.
- projection retry / reconcile / partial apply event 기록도 없다.

### 10.3 env governance gap

- 일부 env는 현재 코드에서 strict fail-fast지만, 일부는 default fallback이 강하다.
- `TM_ROLLOUT_SALT`는 SSOT상 중요하지만 current code는 빈 문자열 fallback을 허용한다.
- `TM_CLICKHOUSE_*` env는 문서상 필요하지만 current code에는 아직 없다.

### 10.4 test gap

- 관련 unit/integration/contract/smoke test 파일을 찾지 못했다.
- CI에서 DB/storage adapter를 검증하는 하네스도 아직 없다.

---

## 11. Task 7에 바로 넘길 입력

Task 7이 repository / adapter 경계를 정리할 때 바로 사용할 입력은 아래다.

1. minimum env surface
   - `TM_DEFENSE_AUDIT_LOG_PATH`
   - `TM_S3_BUCKET`, `TM_S3_REGION`, `TM_S3_PREFIX`, `TM_S3_ARCHIVE_INTERVAL_SECONDS`
   - `TM_PG_URL`
   - `TM_REDIS_URL`
   - `TM_ROLLOUT_SALT`
   - `TM_POLICY_CACHE_SECONDS`
   - planned `TM_CLICKHOUSE_URL`, `TM_CLICKHOUSE_AUDIT_TABLE`, `TM_CLICKHOUSE_INGEST_BATCH_SIZE`, `TM_CLICKHOUSE_INGEST_TIMEOUT_MS`
2. fail-fast rules
   - non-CI `TM_REDIS_URL` 누락은 즉시 실패
   - PostgreSQL control-plane write 실패 시 projection 금지
   - ClickHouse env 누락 시 target ingest worker 시작 금지
3. fail-safe rules
   - S3 bucket 누락 시 archive loop만 비활성
   - audit append failure는 request path를 즉시 죽이지 않되 log/metric으로 노출
   - Redis projection 손상 시 stale read + reconcile
4. replay/backfill source
   - observability: local rotated files / S3 archive
   - projection: PostgreSQL authoritative tables
5. test plan slices
   - unit: env + payload shaping
   - contract: schema/keyspace mapping
   - integration: ingest/projection/runtime read
   - smoke: startup + required env enforcement

---

## 12. 검증 메모

수동 검토 기준은 아래였다.

- `32-storage-architecture.md`
  - storage 책임 분리, env 목록 후보, failure handling checklist와 충돌 없도록 맞췄다.
- `33-docs-vs-current-code-gap-analysis.md`
  - current code가 아직 ClickHouse 미구현, S3 -> PostgreSQL ETL 초안, Redis-first runtime이라는 점을 gap으로 반영했다.
- `31-observability-merge-strategy.md`
  - observability 외부 소비는 warehouse + PostgreSQL 결과 조합이라는 큰 방향과 충돌하지 않도록 유지했다.
- `08-postgresql-to-redis-projection-contract.md`
  - projection key, payload, failure 규칙과 env/failure/test 문서가 일관되도록 맞췄다.
- `audit.py`, `etl_worker.py`, `runtime.py`, `loader.py`, `keyspace.py`, `api/state.py`, `d0_mvp/state/redis_client.py`
  - 실제 env 사용, fail-fast/fallback, rotate/upload, ETL prototype, Redis authority 경로를 확인했다.

테스트 메모:

- 관련 테스트 파일을 찾지 못했다.
- 이번 task에서는 새 테스트를 추가하지 않았다.
