# Production Operations Runbook

## 1. 문서 목적

이 문서는 현재 저장소에 반영된 아래 경계를 운영자가 실제로 다룰 수 있게
cutover, rollback, replay, resync 절차를 고정한다.

- ClickHouse raw-fact ingest
- PostgreSQL control-plane authoritative write
- PostgreSQL -> Redis runtime projection sync/resync
- runtime strict authority read

이번 문서는 scheduler, orchestration platform, alerting system 전체 설계 문서가 아니다.
현재 코드 기준으로 운영자가 무엇을 먼저 확인하고, 무엇을 다시 돌리고,
어디를 authoritative source로 봐야 하는지를 정리하는 runbook이다.

---

## 2. 운영 원칙

1. PostgreSQL은 policy control-plane authoritative source다.
2. Redis는 runtime projection이다.
3. runtime request path는 PostgreSQL을 직접 읽지 않는다.
4. ClickHouse `defense_audit_events`는 observability raw fact다.
5. S3 archive는 ClickHouse raw fact replay source다.
6. OfflineOptimizer는 local JSONL `AuditWarehouse`가 아니라 ClickHouse `defense_audit_events`를 직접 읽는다.
7. `AuditWarehouse`는 admin/debug compatibility 용도만 남고, production 판단 source로 쓰지 않는다.

authoritative source 우선순위:

- policy / rollout current state: PostgreSQL
- runtime serving payload: Redis projection
- observability raw replay source: S3 archive

---

## 3. prod required env / fail-fast 규칙

prod 기준은 `TM_ENV=prod` 또는 `TM_ENV=production`이다.

### 3.1 runtime strict authority

필수:

- `TM_REDIS_URL`
- `TM_ROLLOUT_SALT`

금지:

- `TM_POLICY_ALLOW_LOCAL_FALLBACK=true`
- `TM_ALLOW_IN_MEMORY_REDIS=true`

실패 규칙:

- `validate_runtime_policy_env_for_prod()`가 startup 전에 fail-fast 한다.
- projection missing/stale는 runtime path에서 조용히 broad fallback 하지 않는다.
- evaluate/check는 explicit degraded fail-open audit를 남기고, challenge issue/check conversion path는 503으로 surfaced 될 수 있다.

### 3.2 PostgreSQL control-plane / Redis projection

필수:

- `TM_PG_URL`
- `TM_REDIS_URL`

옵션:

- `TM_PROJECTION_RETRY_MAX_ATTEMPTS`
- `TM_PROJECTION_RETRY_BACKOFF_MS`

실패 규칙:

- `PostgresStrictPolicyAuthorityService.from_env()`는 prod에서 PG/Redis env가 없으면 시작하지 않는다.
- PostgreSQL write 실패 시 projection sync를 진행하지 않는다.
- Redis projection partial apply는 `RedisProjectionApplyError`로 surfaced 되고 resync hint를 남긴다.

### 3.3 ClickHouse ingest

필수:

- `TM_S3_BUCKET`
- `TM_CLICKHOUSE_URL`

옵션:

- `TM_S3_REGION`
- `TM_S3_PREFIX`
- `TM_S3_ARCHIVE_INTERVAL_SECONDS`
- `TM_CLICKHOUSE_AUDIT_TABLE`
- `TM_CLICKHOUSE_INGEST_BATCH_SIZE`
- `TM_CLICKHOUSE_INGEST_TIMEOUT_MS`
- `TM_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS`
- `TM_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS`
- `TM_ETL_PROCESSED_LEDGER_TTL_SECONDS`

실패 규칙:

- `validate_clickhouse_ingest_env_for_prod()`가 prod ETL 시작 전에 fail-fast 한다.
- ClickHouse write 실패는 `ClickHouseBatchWriteError`로 surfaced 된다.
- source-of-replay는 S3 object다. write 성공 전 processed 처리하면 안 된다.
- processed-key ledger는 성공 완료 object만 기록한다. parse/write 실패 object는 다음 run에서 다시 시도될 수 있어야 한다.
- `OfflineOptimizer` service는 `TM_CLICKHOUSE_URL`이 없으면 시작하지 않는다.

운영 권장값:

- staging: `TM_S3_ARCHIVE_INTERVAL_SECONDS=60`
- staging: `TM_CLICKHOUSE_INGEST_BATCH_SIZE=128`
- staging: `TM_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS=3`
- staging: `TM_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS=200`
- staging: `TM_ETL_PROCESSED_LEDGER_TTL_SECONDS=2592000`
- prod: `TM_S3_ARCHIVE_INTERVAL_SECONDS=300`
- prod: `TM_CLICKHOUSE_INGEST_BATCH_SIZE=256`
- prod: `TM_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS=3`
- prod: `TM_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS=200`
- prod: `TM_ETL_PROCESSED_LEDGER_TTL_SECONDS=2592000`

운영 메모:

- `3600`은 즉시성 요구가 있는 staging/prod 기본값으로 쓰지 않는다.
- `30` 미만은 incident 대응이나 단기 실험 외에는 상시 운영값으로 권장하지 않는다.
- interval을 줄여도 현재 loop는 empty file skip + atomic rename 기반이라 구조적으로는 안전하다.
- `TM_CLICKHOUSE_INGEST_BATCH_SIZE=1000`은 짧은 archive cadence에서 flush 단위가 너무 커질 수 있어 기본 운영값으로 두지 않는다.
- processed-key ledger TTL은 운영 dedup cache일 뿐 영구 ledger가 아니다.
- ClickHouse write 실패 로그는 `object key`, `flush_index`, `retry_max_attempts`, `retry_backoff_ms`, `last_error`를 같이 확인한다.
- ETL strict ingest는 canonical flat `snake_case` row만 허용한다. unknown top-level field, scalar `raw_payload`, legacy camelCase row는 replay 전 contract 보정 없이 투입하면 실패한다.

---

## 4. 계층별 failure handling

### 4.1 ClickHouse ingest

주요 예외:

- `ETLIngestError`
- `CanonicalAuditMappingError`
- `ClickHouseBatchWriteError`

운영 의미:

- `CanonicalAuditMappingError`: schema/contract drift 가능성. raw line sample과 canonical contract를 먼저 확인한다.
- `ClickHouseBatchWriteError`: network/auth/table/timeout 가능성. S3 archive는 그대로 replay source로 남는다.
- `ETLIngestError`: object-level ingest 실패. `key`, `flush_count`, `retry_max_attempts`, `last_error`를 보고 key 단위 replay를 수행한다.
- `skip`: processed-key ledger hit로 normal ingest가 object를 건너뛴 상태다. 실제 재적재가 필요하면 explicit force replay를 사용한다.

### 4.2 PostgreSQL control-plane write

주요 예외:

- `PostgresControlPlaneWriteError`

운영 의미:

- authoritative write 실패이므로 projection sync, rollout apply, operator promotion/rollback 절차를 이어서 진행하면 안 된다.
- 반드시 같은 repository/service write를 먼저 재시도한다.

### 4.3 Redis projection sync/resync

주요 예외:

- `PolicyProjectionNotFoundError`
- `RedisProjectionApplyError`

운영 의미:

- `PolicyProjectionNotFoundError`: PostgreSQL row 자체가 없는 상태다. 먼저 PG authoritative row를 확인한다.
- `RedisProjectionApplyError`: PostgreSQL write는 이미 성공했을 수 있고 runtime stale read가 가능하다. `resync_runtime_projection()` 또는 `run_runtime_projection_resync_from_env()`로 복구한다.

### 4.4 runtime projection read

주요 예외:

- `RuntimeProjectionNotFoundError`
- `RuntimeProjectionDecodeError`
- `RuntimeProjectionStaleError`
- `RuntimePolicyAuthorityError`

운영 의미:

- missing/stale/invalid projection은 Redis projection repair가 정상 복구 경로다.
- PostgreSQL direct read를 request path에 임시로 붙이면 안 된다.

### 4.5 archive / replay source

source-of-truth:

- raw observability replay: S3 archive `.jsonl`

운영 의미:

- ClickHouse raw fact 복구는 S3 object replay로 수행한다.
- Redis는 observability replay source가 아니다.

---

## 5. 운영 entrypoint

### 5.1 ClickHouse replay

코드 surface:

- `ETLWorker.run_once()`
- `ETLWorker.replay_key(key, force=False)`
- `ETLWorker.replay_keys(keys, force=False)`
- `run_etl()`
- `run_etl_replay_keys(keys, force=False)`

예시:

```bash
PYTHONPATH=src python3 - <<'PY'
from traffic_master_ai.defense.api.etl_worker import run_etl_replay_keys

run_etl_replay_keys([
    "ai-defense/audit/2026/04/06/audit_001.jsonl",
    "ai-defense/audit/2026/04/06/audit_002.jsonl",
], force=True)
PY
```

### 5.2 projection sync / resync

코드 surface:

- `PostgresStrictPolicyAuthorityService.sync_runtime_projection()`
- `PostgresStrictPolicyAuthorityService.resync_runtime_projection()`
- `run_runtime_projection_sync_from_env()`
- `run_runtime_projection_resync_from_env()`

예시:

```bash
PYTHONPATH=src python3 - <<'PY'
from traffic_master_ai.defense.backoffice_copilot.storage import (
    run_runtime_projection_resync_from_env,
)

result = run_runtime_projection_resync_from_env(rollout_id="rollout-prod-1")
print(result)
PY
```

### 5.3 authoritative write + sync

코드 surface:

- `PostgresStrictPolicyAuthorityService.save_policy_version(project_to_runtime=True)`
- `PostgresStrictPolicyAuthorityService.save_rollout_state()`
- `PostgresStrictPolicyAuthorityService.append_rollout_event()`
- `PostgresStrictPolicyAuthorityService.save_optimization_run()`
- `DefenseRuntime.offline_optimizer_service()`
- `OfflineOptimizer.run_once()`
- `OfflineOptimizer.start_canary()`
- `OfflineOptimizer.expand_rollout()`
- `OfflineOptimizer.rollback()`

운영 원칙:

- policy version activation과 rollout state current state 변경은 write 뒤 sync를 같은 절차로 묶는다.
- `policy_rollout_events`는 append-only다.
- strict mode의 optimizer/admin write는 local store/direct Redis/file fallback이 아니라 위 surface를 통해 PostgreSQL authoritative write 후 Redis projection sync로 이어져야 한다.

---

## 6. migration / bootstrap / cutover / rollback

### 6.1 migration 순서

1. PostgreSQL DDL 적용
   - `001_post_review_tables.sql`
   - `002_postgresql_policy_control_plane_tables.sql`
2. ClickHouse DDL 적용
   - `003_clickhouse_defense_audit_events.sql`
   - read model이 필요한 경우 `004_clickhouse_read_models.sql`
3. application deploy 전 prod env 검증
4. authoritative seed data 반영

### 6.2 bootstrap 순서

1. PostgreSQL `policy_versions`에 base policy document 저장
2. PostgreSQL `policy_rollout_state`에 current rollout row 저장
3. `PostgresStrictPolicyAuthorityService.resync_runtime_projection()` 실행
4. Redis key 3종 확인
   - `tm:decision-policy:version:{policyVersion}`
   - `tm:decision-policy:rollout-state`
   - `tm:decision-policy:version-index`
5. runtime startup

주의:

- prod에서는 baseline bootstrap direct write를 주경로로 사용하지 않는다.
- 정상 bootstrap source는 PostgreSQL authoritative rows다.

### 6.3 cutover 순서

1. prod env 검증
2. PostgreSQL authoritative seed 확인
3. Redis projection full resync
4. runtime instance restart
5. health check
   - runtime unavailable spike 여부
   - Redis projection stale/missing log 여부
6. ClickHouse ETL 시작
7. backlog archive replay가 있으면 explicit replay keys로 처리

### 6.4 rollback 순서

1. PostgreSQL `policy_rollout_state`를 이전 base/candidate 상태로 업데이트
2. `policy_rollout_events`에 rollback event append
3. `resync_runtime_projection()` 실행
4. runtime에서 projected rollout state 재확인
5. 필요 시 candidate policy doc projection key와 version index를 재검토

원칙:

- rollback은 PostgreSQL state update 성공 후 Redis projection overwrite 순서다.
- Redis만 직접 수정해서 rollback하면 안 된다.

---

## 7. 장애 대응 절차

### 7.1 runtime에서 projection unavailable/stale 발생

1. runtime log에서 `RuntimePolicyAuthorityError`, `RuntimeProjectionStaleError`, `RuntimeProjectionNotFoundError` 확인
2. PostgreSQL `policy_rollout_state` current row 확인
3. `run_runtime_projection_resync_from_env(rollout_id=...)` 실행
4. Redis key 3종 확인
5. runtime degraded/fail-open audit 감소 여부 확인

### 7.2 projection sync 실패

1. `RedisProjectionApplyError` scope 확인
2. PostgreSQL authoritative row 존재 확인
3. Redis connectivity/auth 확인
4. 같은 rollout_id로 resync 재실행
5. 반복 실패 시 runtime stale/missing projection 상태를 incident로 승격

### 7.3 ClickHouse ingest 실패

1. 실패한 S3 key 확인
2. `CanonicalAuditMappingError`인지 `ClickHouseBatchWriteError`인지 분리
3. mapping 오류면 canonical contract/ingest code 확인
4. connection/write 오류면 ClickHouse health, table 존재, auth 확인
5. `run_etl_replay_keys([key])`로 key 단위 replay

### 7.4 PostgreSQL write 실패

1. `PostgresControlPlaneWriteError` table / record_key 확인
2. authoritative row가 저장되지 않았음을 전제로 본다
3. projection sync나 rollout promotion을 이어서 진행하지 않는다
4. 같은 write call을 재시도하거나 admin/operator input을 보정한다

---

## 8. 현재 남는 운영 gap

1. background worker / scheduler / lag alerting은 아직 없다.
2. real PostgreSQL / Redis / ClickHouse infra-backed integration smoke는 아직 없다.
3. ClickHouse processed-key ledger와 archive mark-processed orchestration은 아직 없다.

이 3가지는 운영 안전장치 이후 다음 phase에서 다뤄야 한다.

---

## 9. 확인 파일

- `src/traffic_master_ai/defense/storage_env.py`
- `src/traffic_master_ai/defense/api/etl_worker.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
- `src/traffic_master_ai/defense/d0_mvp/api/runtime.py`
