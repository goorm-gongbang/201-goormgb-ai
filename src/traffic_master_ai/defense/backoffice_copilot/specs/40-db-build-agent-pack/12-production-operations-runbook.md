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

### 5.4 Post-Review 운영 CLI

command:

- `tm-ai-post-review`

기본 입력:

- ClickHouse `defense_session_rollups`
- ClickHouse `defense_post_review_candidates_v1`

기본 출력:

- PostgreSQL `post_review_runs`
- PostgreSQL `post_review_session_results`

선택 옵션:

- `--match-id`
- `--window-start-ms`
- `--window-end-ms`
- `--window-seconds`

운영 옵션:

- `--limit`
- `--dry-run`
- `--conflict-policy upsert|fail_fast`
- `--require-llm`
- `--export-dir`

local/dev 전용 옵션:

- `--fixture-jsonl`
- `--use-raw-audit-fallback`

예시:

```bash
tm-ai-post-review \
  --match-id match-20260414-0001 \
  --window-start-ms 1776111600000 \
  --window-end-ms 1776112200000 \
  --limit 1000 \
  --dry-run
```

동작 규칙:

- 기본 실행은 fixture JSONL을 읽지 않는다.
- fixture JSONL은 `--fixture-jsonl`을 명시한 local/dev 실행에서만 쓴다.
- window를 명시하지 않으면 UTC 기준 현재 시각을 10분 단위로 내림하고, 그 직전 10분 구간을 사용한다.
- 기본 window는 `[window_start_ms, window_end_ms]` 값으로 workflow에 전달된다.
- `--match-id`를 명시하지 않으면 `post-review-<window_end_utc_yyyymmddhhmm>` 형식으로 생성한다.
- 같은 기본 window를 재실행하면 같은 기본 `match_id`가 생성된다.
- `--dry-run`은 ClickHouse 입력과 workflow를 실행하지만 PostgreSQL에는 쓰지 않는다.
- 입력 candidate row가 0개면 status `no_input`으로 종료하고 PostgreSQL에 쓰지 않는다.
- 같은 window 재실행의 idempotency key는 `match_id`다.
- 기본 `--conflict-policy upsert`는 `post_review_runs.match_id`, `post_review_session_results(match_id, session_id)`를 overwrite한다.
- `--conflict-policy fail_fast`는 같은 key 중복을 운영 오류로 surfaced 한다.
- 실행 결과는 JSON stdout으로 `mode`, `status`, `input_count`, `candidate_count`, `output_count`, `skipped_count`, `warning_count`, `error_count`, `duration_ms`, `dry_run`을 남긴다.

Discord / notification:

- Discord payload builder, Discord webhook sender, Discord Secret, notification retry 설계는 이 command 범위가 아니다.
- Discord 본문 authority는 후속 작업에서도 PostgreSQL `post_review_*`를 기준으로 둔다.

### 5.5 command exit code / summary 계약

공통 원칙:

- 정상 성공, 정상 skip, `no_input`, `dry_run`은 exit code `0`이다.
- 설정 누락, DB/Redis/ClickHouse 연결 실패, migration 전제조건 실패, workflow `FAILED`는 exit code `1`이다.
- 각 command는 마지막 stdout 줄에 JSON summary를 출력한다.
- 운영 로그는 `<command>_summary` 형태의 단일 summary event를 남긴다.

summary 공통 필드:

- `command`: 실행 command 이름
- `mode`: `dry_run`, `apply`, `disabled`, `fixture_dry_run`, `fixture_apply`
- `status`: `success`, `skip`, `no_input`, `dry_run`, `disabled`, `failed` 또는 worker 세부 status
- `input_count`: 읽거나 평가한 대상 수
- `output_count`: 쓰거나 반영한 대상 수
- `skipped_count`: 정상적으로 건너뛴 대상 수
- `error_count`: 실패 수
- `duration_ms`: command 시작부터 summary 생성까지 걸린 시간
- `dry_run`: write side effect 비활성 여부

command별 정상 skip:

- `tm-ai-policy-bootstrap`: 기존 policy/rollout row가 모두 있으면 `status=skip`, exit `0`
- `tm-ai-policy-optimizer`: disabled, lock_missed, no_change, waiting, insufficient_data, cooldown, dry_run은 exit `0`
- `tm-ai-post-review`: candidate row 0개는 `status=no_input`, exit `0`, PostgreSQL write 없음

command별 fail-fast:

- `tm-ai-clickhouse-migrate`: `TM_CLICKHOUSE_URL` 누락, `004_clickhouse_read_models.sql` 파일 누락, HTTP DDL 실행 실패
- `tm-ai-storage-migrate`: `TM_PG_URL` 누락, SQL file 누락, DDL 실행 실패
- `tm-ai-policy-bootstrap`: `TM_PG_URL` 누락, `policy_versions`/`policy_rollout_state` table 부재, seed read/write 실패
- `tm-ai-policy-projection-resync`: `TM_PG_URL`/`TM_REDIS_URL` 누락, current rollout row 부재, policy row 부재, Redis apply 실패
- `tm-ai-policy-optimizer`: prod 필수 env 누락, unsafe fallback env, `TM_CLICKHOUSE_URL` 누락, invalid numeric env
- `tm-ai-post-review`: ClickHouse read 실패, PostgreSQL write 실패, `--require-llm` 상태에서 LLM key 누락, workflow `FAILED`

### 5.6.0 ClickHouse DDL migrate (PreSync 0)

command:

- `tm-ai-clickhouse-migrate`

목적:

- ClickHouse read model VIEW DDL을 ArgoCD sync마다 자동 적용한다.
- `/docker-entrypoint-initdb.d` init script는 PVC가 유지된 환경에서 재실행되지 않으므로,
  VIEW 정의 변경은 이 command를 통해서만 운영 ClickHouse에 반영된다.
- `CREATE OR REPLACE VIEW`를 사용하므로 매번 실행해도 idempotent하다.

적용 범위 (`004_clickhouse_read_models.sql`):

1. `defense_session_rollups` — **CRITICAL**: 5분→10분 window mismatch 수정 (staging `no_input` 원인)
2. `defense_match_rollups` — 독립 5분 집계, 전체 DDL sync 일관성
3. `defense_post_review_candidates_v1` — `defense_session_rollups` 참조, window 자동 상속

| 항목 | 계약 |
|---|---|
| command | `tm-ai-clickhouse-migrate` |
| 필수 env | `TM_CLICKHOUSE_URL` |
| 불필요 env | `TM_PG_URL`, `TM_REDIS_URL`, `TM_ROLLOUT_SALT`, `TM_POLICY_*`, `TM_PROJECTION_*`, S3/AWS |
| serviceAccount | `ai-defense` 재사용 가능 (ClickHouse는 클러스터 내부 HTTP, IAM 불필요) |
| dry-run | `tm-ai-clickhouse-migrate --dry-run` |
| exit `0` | DDL 적용 성공 또는 dry-run plan 성공 |
| exit `1` | `TM_CLICKHOUSE_URL` 누락, SQL 파일 누락, HTTP 실패 |
| summary status | `success`, `dry_run`, `failed` |
| target | `clickhouse_ddl` |
| 재실행 가능 여부 | 가능. `CREATE OR REPLACE VIEW`는 매 ArgoCD sync 안전 |
| 선행 조건 | ClickHouse Pod 기동 완료 (clickhouse StatefulSet sync-wave 1 이후) |

staging `no_input` 원인 및 재발 방지:

- 원인: `defense_session_rollups` VIEW가 `WITH 300000 AS window_ms` (5분)으로 생성되었으나,
  `tm-ai-post-review`는 `DEFAULT_POST_REVIEW_WINDOW_SECONDS=600` (10분) window로 exact-match 조회한다.
  `window_end_ms - window_start_ms = 300000`인 row는 600000ms window WHERE 절에 한 건도 매칭되지 않는다.
- 해결: `tm-ai-clickhouse-migrate`가 `WITH 600000 AS window_ms`로 VIEW를 교체한다.
- 재발 방지: `test_session_rollup_uses_600000ms_window` 회귀 테스트가 상시 검증한다.

### 5.7 ArgoCD 자동 배포 순서

최종 자동화 순서 (수동 SQL 실행 없음):

1. ArgoCD PreSync Job 0: `tm-ai-clickhouse-migrate` — ClickHouse VIEW DDL 자동 적용
2. ArgoCD PreSync Job 1: `tm-ai-storage-migrate` — PostgreSQL DDL 자동 적용
3. ArgoCD PreSync Job 2: `tm-ai-policy-bootstrap` — baseline policy / rollout seed
4. ArgoCD PreSync Job 3: `tm-ai-policy-projection-resync --current` — Redis projection 반영
5. `ai-defense` Deployment rollout
6. `tm-ai-policy-optimizer` CronJob
7. `tm-ai-post-review` CronJob

운영 계약:

- 사람이 수동 one-shot Job을 치는 배포 절차로 만들지 않는다.
- PreSync Job 4개는 ArgoCD sync 내부 단계로 숨긴다.
- PreSync 실패 시 이후 Deployment와 CronJob rollout은 진행하지 않는다.
- SQL/DDL 수동 적용은 요청하지 않고 AI image command가 모든 DDL, bootstrap, projection resync를 책임진다.
- ClickHouse VIEW 변경은 `004_clickhouse_read_models.sql` 수정 → 이미지 빌드 → ArgoCD sync로 자동 반영된다.
- optimizer와 post-review는 새 generic chart보다 기존 `ai-etl` CronJob 패턴 복제를 우선 검토한다.

세부 인프라 전달 계약:

- [18-argocd-presync-infra-handoff.md](/Users/shadowmoon/Desktop/실무프로젝트/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/18-argocd-presync-infra-handoff.md)

---

## 6. migration / bootstrap / cutover / rollback

### 6.1 migration 순서

ArgoCD PreSync를 통한 완전 자동화 경로 (운영 표준):

1. ClickHouse DDL 자동 적용
   - command: `tm-ai-clickhouse-migrate` (PreSync syncWave: `-1`)
   - scope: `004_clickhouse_read_models.sql` — 3개 VIEW (`CREATE OR REPLACE VIEW`)
   - `defense_session_rollups` (10분 window), `defense_match_rollups` (5분), `defense_post_review_candidates_v1`
2. PostgreSQL DDL 자동 적용
   - command: `tm-ai-storage-migrate` (PreSync syncWave: `0`)
   - scope: PostgreSQL DDL only
   - `001_post_review_tables.sql`
   - `002_postgresql_policy_control_plane_tables.sql`
   - `005_post_review_runs_schema_drift.sql`
   - `006_post_review_session_results_schema_drift.sql`
3. application deploy 전 prod env 검증
4. authoritative seed data 반영

비고:
- ClickHouse `defense_audit_events` 기반 테이블 (`003_clickhouse_defense_audit_events.sql`)은
  `CREATE TABLE IF NOT EXISTS`로 정의되어 있으며, ClickHouse StatefulSet 초기화 시 init script로 적용된다.
  이 테이블은 PreSync migrate 범위에 포함하지 않는다 (PVC가 있으면 init script도 실행되지 않으므로,
  신규 클러스터에서만 init script 경로가 유효하다).
- 수동 SQL 실행은 장애 fallback 절차이며 운영 표준이 아니다.

### 6.2 bootstrap 순서

1. `tm-ai-policy-bootstrap --dry-run`으로 seed 계획 확인
2. `tm-ai-policy-bootstrap`으로 PostgreSQL seed 반영
   - `policy_versions`에 baseline policy document가 없으면 생성
   - `policy_rollout_state`에 대상 `rollout_id` row가 없으면 생성
   - 기존 row가 있으면 overwrite하지 않고 skip
3. `tm-ai-policy-projection-resync --current`로 Redis projection 반영
4. Redis key 3종 확인
   - `tm:decision-policy:version:{policyVersion}`
   - `tm:decision-policy:rollout-state`
   - `tm:decision-policy:version-index`
5. runtime startup

주의:

- schema migration, bootstrap, Redis projection resync는 같은 command에 묶지 않는다.
- `tm-ai-policy-bootstrap`은 PostgreSQL seed만 수행하고 Redis projection을 쓰지 않는다.
- `tm-ai-policy-projection-resync` 기본 범위는 active rollout row이며, 특정 `rollout_id` 또는 특정 `policy_version`만 지정할 수 있다.
- 전체 table scan 기반 full resync는 현재 운영 command 범위가 아니다.
- migration이 안 된 상태에서 bootstrap을 실행하면 PostgreSQL table 부재 오류를 `status=failed`, exit `1`로 surfaced 한다.
- active/latest rollout row가 없을 때 resync는 `status=failed`, exit `1`로 종료한다.
- PG/Redis env 누락은 command 시작 단계에서 fail-fast 한다.
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

### 7.5 Post-Review 실행 실패

1. stdout JSON의 `status`, `final_status`, `warning_count`, `error_count`를 확인한다.
2. `input_source=clickhouse_read_model`이면 `TM_CLICKHOUSE_URL`과 ClickHouse read model table/view 존재를 먼저 확인한다.
3. `TM_PG_URL` 누락 또는 SQLAlchemy import 실패는 write 경로 문제로 분리한다.
4. `no_input`은 정상 no-op이다. 같은 window에 candidate row가 존재해야 하는 상황이면 ClickHouse rollup/candidate 생성 경로를 확인한다.
5. `fail_fast` conflict 오류는 같은 `match_id` 재실행인지 먼저 확인한다.
6. Discord 미전송은 이 command의 장애가 아니다.

---

## 8. runtime / optimizer env contract

### 8.1 ai-defense runtime 필수 env

prod strict runtime:

- `TM_ENV=prod`
- `TM_REDIS_URL`
- `TM_ROLLOUT_SALT`
- `TM_POLICY_ALLOW_LOCAL_FALLBACK=false`
- `TM_ALLOW_IN_MEMORY_REDIS=false`

PostgreSQL authoritative projection:

- `TM_PG_URL`
- `TM_REDIS_URL`
- `TM_PROJECTION_RETRY_MAX_ATTEMPTS`
- `TM_PROJECTION_RETRY_BACKOFF_MS`

runtime freshness:

- `TM_POLICY_PROJECTION_MAX_STALENESS_MS`
- 기본값은 300000ms
- 값이 설정되면 stale projection은 strict runtime에서 fail-fast 계열 오류로 다룬다.

fallback 기준:

- prod에서는 file policy fallback과 in-memory Redis fallback을 허용하지 않는다.
- CI/local에서는 명시적으로 허용된 경우에만 fallback을 쓴다.
- projection reconciler는 strict authority, `TM_PG_URL`, `TM_REDIS_URL`, Redis backend 조건이 모두 맞을 때만 활성화된다.

### 8.2 tm-ai-policy-optimizer 실행 계약

command:

- `tm-ai-policy-optimizer`

skip 조건:

- `TM_POLICY_OPTIMIZER_ENABLED=false` 또는 미설정이면 status `disabled`로 종료한다.

fail-fast 조건:

- `TM_POLICY_OPTIMIZER_DRY_RUN=false`인데 `TM_POLICY_OPTIMIZER_APPLY_ENABLED=true`가 아님
- prod에서 `TM_PG_URL`, `TM_REDIS_URL`, `TM_ROLLOUT_SALT` 누락
- prod에서 `TM_POLICY_ALLOW_LOCAL_FALLBACK=true`
- prod에서 `TM_ALLOW_IN_MEMORY_REDIS=true`
- `TM_CLICKHOUSE_URL` 누락
- strict authority mode에서 `TM_PG_URL` 누락
- active rollout state 부재
- Redis projection missing/stale/mismatch
- mutation 후 authoritative state와 Redis projection post-check 불일치
- invalid numeric env

dry-run 조건:

- `TM_POLICY_OPTIMIZER_DRY_RUN=true`
- Redis lock은 사용한다.
- baseline bootstrap, canary start, rollout expand, rollback은 수행하지 않는다.
- active rollout이 없으면 metrics read까지만 수행한다.
- active rollout이 있으면 guardrail read/evaluate까지만 수행하고 결과를 `wouldStatus`로 출력한다.

apply 조건:

- `TM_POLICY_OPTIMIZER_ENABLED=true`
- `TM_POLICY_OPTIMIZER_DRY_RUN=false`
- `TM_POLICY_OPTIMIZER_APPLY_ENABLED=true`
- Redis lock 획득 성공
- strict authority와 storage env 검증 성공
- active rollout state 존재
- PostgreSQL authoritative state와 Redis projection 일치
- proposal 또는 rollout guardrail 조건 충족

auto-apply 허용 mutation:

- canary start: baseline `FULL` rollout에서 proposal이 있고 precondition/post-check가 모두 통과할 때 허용
- rollout expand: `CANARY` 또는 `EXPAND` stage가 경과했고 guardrail rollback 조건이 없을 때 허용
- rollback: `CANARY` 또는 `EXPAND` stage에서 guardrail rollback 조건이 발생했을 때 허용

apply 금지 상태:

- `apply_blocked`: apply gate 누락
- `no_active_rollout`: active rollout 없음
- `no_candidate_or_no_baseline`: stage에 필요한 base/candidate policy version 누락
- `projection_not_ready`: Redis projection missing/stale/mismatch
- `metrics_read_failed`: ClickHouse metrics read 실패
- `insufficient_data`: guardrail 비교 데이터 부족
- `rollout_waiting`, `rollback_cooling_down`, `rollout_cooling_down`: 시간 조건 미충족

post-check 검증:

- mutation 이후 PostgreSQL rollout state를 다시 읽는다.
- Redis `tm:decision-policy:rollout-state`를 다시 읽는다.
- stage, base policy version, candidate policy version, ratio, updated_at_ms가 authoritative state와 일치해야 한다.
- Redis version index에 필요한 base/candidate policy version이 있어야 한다.
- Redis policy version key가 필요한 base/candidate version마다 있어야 한다.
- `projection_refreshed_at_ms`가 존재하고 양수여야 한다.
- post-check 실패는 `status=failed`, exit `1`이다.

상태 출력:

- `apply_blocked`
- `disabled`
- `failed`
- `lock_missed`
- `metrics_read_failed`
- `no_active_rollout`
- `no_candidate_or_no_baseline`
- `no_change`
- `projection_not_ready`
- `proposal_applied`
- `rollout_waiting`
- `insufficient_data`
- `rollout_expanded`
- `rolled_back`
- `rollback_cooling_down`
- `rollout_cooling_down`
- `dry_run`

summary 해석:

- `disabled`: 정상 skip, exit `0`
- `lock_missed`: 다른 worker가 실행 중인 정상 skip, exit `0`
- `no_change`: proposal 없음, exit `0`
- `rollout_waiting`: canary/expand window 미도달, exit `0`
- `insufficient_data`: guardrail 비교 데이터 부족, exit `0`
- `rollback_cooling_down`, `rollout_cooling_down`: cooldown 중, exit `0`
- `dry_run`: mutation 없이 metrics/guardrail 평가만 수행, exit `0`
- `proposal_applied`, `rollout_expanded`, `rolled_back`: apply side effect 발생, exit `0`
- `apply_blocked`, `no_active_rollout`, `no_candidate_or_no_baseline`, `projection_not_ready`, `metrics_read_failed`, `failed`: exit `1`

summary 추가 필드:

- `apply_enabled`: `TM_POLICY_OPTIMIZER_APPLY_ENABLED` 반영 여부
- `guardrail_result`: rollout guardrail 평가 결과
- `attempted_action`: 시도한 mutation
- `applied_action`: 실제 수행한 mutation
- `verification_status`: `success`, `failed`, `not_checked`

기본값:

- `TM_POLICY_OPTIMIZER_WINDOW_SECONDS=600`
- `TM_POLICY_OPTIMIZER_CANARY_RATIO=0.05`
- `TM_POLICY_OPTIMIZER_MIN_APPLY_COOLDOWN_SECONDS=300`
- `TM_POLICY_OPTIMIZER_ROLLOUT_ID=offline-optimizer-default`
- `TM_POLICY_OPTIMIZER_LOCK_TTL_SECONDS=300`

### 8.3 Helm에 전달할 최소 env 목록

ai-defense Deployment:

- `TM_ENV`
- `TM_REDIS_URL`
- `TM_ROLLOUT_SALT`
- `TM_POLICY_ALLOW_LOCAL_FALLBACK=false`
- `TM_ALLOW_IN_MEMORY_REDIS=false`
- `TM_POLICY_PROJECTION_MAX_STALENESS_MS`
- `TM_PG_URL`
- `TM_PROJECTION_RETRY_MAX_ATTEMPTS`
- `TM_PROJECTION_RETRY_BACKOFF_MS`

ai-policy-optimizer CronJob:

- `TM_POLICY_OPTIMIZER_ENABLED=true`
- `TM_POLICY_OPTIMIZER_DRY_RUN`
- `TM_POLICY_OPTIMIZER_APPLY_ENABLED`
- `TM_PG_URL`
- `TM_REDIS_URL`
- `TM_CLICKHOUSE_URL`
- `TM_ROLLOUT_SALT`
- `TM_POLICY_ALLOW_LOCAL_FALLBACK=false`
- `TM_ALLOW_IN_MEMORY_REDIS=false`

선택 env:

- `TM_POLICY_OPTIMIZER_BOOTSTRAP_BASELINE`
- `TM_POLICY_OPTIMIZER_WINDOW_SECONDS`
- `TM_POLICY_OPTIMIZER_CANARY_RATIO`
- `TM_POLICY_OPTIMIZER_MIN_APPLY_COOLDOWN_SECONDS`
- `TM_POLICY_OPTIMIZER_ROLLOUT_ID`
- `TM_POLICY_OPTIMIZER_LOCK_TTL_SECONDS`
- `TM_CLICKHOUSE_AUDIT_TABLE`
- `TM_CLICKHOUSE_INGEST_TIMEOUT_MS`
- `TM_PROJECTION_RETRY_MAX_ATTEMPTS`
- `TM_PROJECTION_RETRY_BACKOFF_MS`

tm-ai-post-review CronJob:

- `TM_CLICKHOUSE_URL`
- `TM_PG_URL`

선택 env:

- `TM_OFFLINE_LLM_API_KEY`
- `OPENAI_API_KEY`
- `TM_OFFLINE_LLM_MODEL`
- `TM_OFFLINE_LLM_ENDPOINT` 또는 `OPENAI_BASE_URL`
- `TM_OFFLINE_LLM_TIMEOUT_MS`

LLM key 조건:

- 기본 CronJob command에는 `--require-llm`을 붙이지 않는다.
- `--require-llm`을 붙이는 운영 모드에서만 `TM_OFFLINE_LLM_API_KEY` 또는 `OPENAI_API_KEY`가 필수다.

기본 schedule 계약:

- `tm-ai-post-review`는 window/match_id 자동 계산이 있으므로 CronJob command에 시간 인자를 넣지 않아도 된다.
- 기본 window는 UTC 10분 bucket 기준 직전 10분이다.
- 같은 bucket 재실행은 같은 `match_id`로 idempotent upsert 된다.

secret key 후보:

- `TM_PG_URL`
- `TM_REDIS_URL`
- `TM_CLICKHOUSE_URL`
- `TM_OFFLINE_LLM_API_KEY`
- `OPENAI_API_KEY`
- `LANGSMITH_API_KEY`

협의 보류:

- OpenAI / LangSmith key를 어느 Secret에 둘지는 인프라/보안 후속 협의에서 결정한다.
- managed Redis TLS URL 형식과 Secret 위치는 303 레포 작업에서 확정한다.

배포 방식 후속안:

- 기본안은 기존 `ai-etl` chart 복제 수준의 `ai-policy-optimizer` chart 추가다.
- generic cronjob chart 설계와 command override 일반화는 기본안이 아니다.

---

## 9. 운영 smoke command

목적:

- 실제 CronJob 등록 전에 command/env/전제조건을 201 코드 기준으로 확인한다.
- 이 절차는 managed PostgreSQL/Redis/ClickHouse 실제 smoke를 대체하지 않는다.

순서:

```bash
tm-ai-storage-migrate --dry-run
tm-ai-policy-bootstrap --dry-run
tm-ai-policy-projection-resync --current
TM_POLICY_OPTIMIZER_ENABLED=true TM_POLICY_OPTIMIZER_DRY_RUN=true tm-ai-policy-optimizer
TM_POLICY_OPTIMIZER_ENABLED=true TM_POLICY_OPTIMIZER_DRY_RUN=false TM_POLICY_OPTIMIZER_APPLY_ENABLED=true tm-ai-policy-optimizer
tm-ai-post-review --dry-run
```

확인 기준:

- 각 command 마지막 stdout 줄이 JSON summary다.
- `tm-ai-storage-migrate --dry-run`은 `status=dry_run`, `target=postgres_ddl`, `output_count=4`다.
- `tm-ai-policy-bootstrap --dry-run`은 `status=dry_run`이고 PostgreSQL write가 없다.
- `tm-ai-policy-projection-resync --current`는 active rollout row가 없으면 `status=failed`로 종료한다.
- optimizer dry-run은 mutation 없이 `status=dry_run` 또는 lock/skip status로 종료한다.
- optimizer apply smoke는 staging/real storage에서만 수행하고 `apply_enabled=true`, `attempted_action`, `applied_action`, `verification_status`를 확인한다.
- `TM_POLICY_OPTIMIZER_DRY_RUN=false`인데 `TM_POLICY_OPTIMIZER_APPLY_ENABLED=true`가 없으면 `status=apply_blocked`, exit `1`이어야 한다.
- `tm-ai-post-review --dry-run`은 window/match_id를 자동 생성한다.
- Post-Review candidate row가 0개면 `status=no_input`, `output_count=0`, exit `0`, PostgreSQL write 없음이 정상이다.

자동 생성 확인:

```bash
tm-ai-post-review --dry-run
```

- `window_end_ms`는 UTC 현재 시각을 10분 단위로 내림한 값이다.
- `window_start_ms = window_end_ms - 600000`이다.
- `match_id = post-review-<window_end_utc_yyyymmddhhmm>`이다.

---

## 10. 현재 남는 운영 gap

1. background worker / scheduler / lag alerting은 아직 없다.
2. real PostgreSQL / Redis / ClickHouse infra-backed integration smoke는 아직 없다.
3. ClickHouse processed-key ledger와 archive mark-processed orchestration은 아직 없다.
4. Discord payload builder, webhook sender, Secret, retry/idempotency는 backlog다.

이 4가지는 운영 안전장치 이후 다음 phase에서 다뤄야 한다.

---

## 11. Post-Review Observability (단계별 로그 가이드)

### 11.1 추가된 structured log 목록

아래 log key는 Grafana/Loki에서 `{app="tm-ai-post-review"}` 필터와 함께 grep 가능하다.

| 단계 | 로그 키 | 수준 | 설명 |
|------|---------|------|------|
| input_load | `post_review_input_load_start` | INFO | ClickHouse/fixture 읽기 시작 |
| input_load | `post_review_input_load_complete` | INFO | 읽기 완료, `event_count` 포함 |
| input_load | `post_review_input_load_failed` | ERROR | 읽기 실패, `exception_type` / `exception_message` 포함 |
| candidate_select | `post_review_candidate_select_start` | INFO | 후보 선정 시작, `event_count` |
| candidate_select | `post_review_candidate_select_complete` | INFO | 선정 완료, `session_count` / `candidate_count` |
| candidate_select | `post_review_candidate_select_failed` | ERROR | 선정 실패 |
| session_review | `post_review_session_review_start` | INFO | 세션 분석 시작, `candidate_count` |
| session_review | `post_review_session_review_complete` | INFO | 분석 완료, `analysis_count` |
| session_review | `post_review_session_review_failed` | ERROR | 분석 실패 |
| llm_review | `post_review_llm_review_start` | INFO | LLM 리뷰 시작, `llm_present` 포함 |
| llm_review | `post_review_llm_adapter_missing` | WARNING | LLM key 없음 → deterministic fallback 예정 |
| llm_review | `post_review_llm_review_complete` | INFO | 리뷰 완료, `fallback_count` |
| llm_review | `post_review_llm_review_failed` | ERROR | 리뷰 예외 발생 |
| llm_review | `post_review_review_fallback_applied` | WARNING | 세션 단위 fallback 적용됨, `fallback_reason` / `degraded=true` |
| summary_generate | `post_review_summary_generate_start` | INFO | 요약 생성 시작 |
| summary_generate | `post_review_summary_generate_complete` | INFO | 요약 완료, `fallback_applied` |
| summary_generate | `post_review_summary_generate_failed` | ERROR | 요약 예외 발생 |
| summary_generate | `post_review_summary_fallback_applied` | WARNING | 템플릿 fallback 적용됨, `degraded=true` |
| output_persist | `post_review_output_build_start` | INFO | 출력 빌드 시작, `candidate_count` / `review_count` |
| output_persist | `post_review_db_persist_start` | INFO | `save_bundle()` 호출 직전 |
| output_persist | `post_review_db_persist_success` | INFO | `save_bundle()` 성공, `session_result_row_count` |
| output_persist | `post_review_db_persist_failed` | ERROR | `save_bundle()` 실패, `exception_type` / `exception_message` |
| output_persist | `post_review_output_persist_failed` | ERROR | output stage 전체 예외 |
| output_persist | `post_review_output_persist_complete` | INFO | 출력 완료, `session_result_row_count` / `final_status` |
| summary | `post_review_summary` | INFO | 파이프라인 최종 요약 (항상 마지막에 출력) |

### 11.2 post_review_summary 필드 해석

`post_review_summary` 로그에서 아래 필드를 확인하면 실패 원인을 바로 좁힐 수 있다.

| 필드 | 의미 |
|------|------|
| `status` | CLI 결과: `completed` / `failed` / `no_input` |
| `failure_stage` | 실패 단계: `input_load` / `candidate_select` / `session_review` / `summary_generate` / `output_persist` / `unknown` |
| `error_code` | 첫 번째 에러 코드 |
| `llm_used` | LLM API key가 존재하고 어댑터가 생성됐는지 여부 |
| `fallback_used` | `llm_review_fallback_applied` 또는 `window_summary_fallback_applied` 경고가 발생했는지 |
| `degraded` | fallback이 적용된 degraded 상태인지 |
| `db_persist_attempted` | `save_bundle()` 호출 시도 여부 |
| `db_persist_succeeded` | `save_bundle()` 성공 여부 |
| `warning_codes` | 전체 경고 코드 목록 |
| `error_codes` | 전체 에러 코드 목록 |

### 11.3 운영자 Grafana/Loki 검색 예시

**실패 원인 파악 (1차 조회):**
```
{app="tm-ai-post-review"} |= "post_review_summary" | logfmt | status="failed"
```
→ `failure_stage`, `error_code`, `db_persist_attempted`, `db_persist_succeeded` 한 줄로 확인 가능.

**DB 저장 실패 확인:**
```
{app="tm-ai-post-review"} |= "post_review_db_persist_failed"
```
→ `exception_type`, `exception_message`로 DB 오류 상세 확인.

**LLM fallback 적용 여부:**
```
{app="tm-ai-post-review"} |= "post_review_review_fallback_applied"
```
→ `fallback_reason`으로 원인 확인 (`adapter_missing` / `adapter_timeout` 등).

**degraded 상태 확인:**
```
{app="tm-ai-post-review"} |= "post_review_summary" | logfmt | degraded="true"
```

### 11.4 fallback vs failed 구분 기준

- **fallback (WARNING, degraded=true)**: 파이프라인이 완료됐지만 LLM 대신 rule-based 판정 또는 템플릿 요약을 사용했음. `status=completed`, DB 저장은 성공.
- **failed (ERROR)**: 파이프라인이 중단됐음. `status=failed`, `db_persist_succeeded=false`.
- **no_input**: candidate row가 0개. DB 저장 없음 (`db_persist_attempted=false`).

### 11.5 표준 error_code / warning_code 목록

**error_code:**
- `clickhouse_read_failed` — ClickHouse 읽기 실패
- `candidate_selection_failed` — 후보 선정 실패
- `llm_review_failed` — LLM 리뷰 예외
- `summary_generation_failed` — 요약 생성 예외
- `output_build_failed` — 출력 빌드 실패
- `db_persistence_failed` — save_bundle 실패
- `run_status_persistence_failed` — 최종 status 저장 실패
- `backend_delivery_failed` — backend 전달 실패
- `validation_failed` — validation 실패
- `workflow_node_failed` — 워크플로우 노드 예외 (context에 `node_name` 포함)
- `unexpected_exception` — 분류되지 않은 예외

**warning_code:**
- `llm_review_fallback_applied` — 세션 단위 LLM → rule-based fallback 적용
- `window_summary_fallback_applied` — 창 요약 LLM → 템플릿 fallback 적용
- `backend_delivery_failed_partial` — 일부 세션 backend 전달 실패

---

## 12. Post-Review Persistence Schema Drift 대응

### 12.1 발생 원인

`CREATE TABLE IF NOT EXISTS`는 테이블이 이미 존재하면 no-op이다.
기존 환경에서 `post_review_runs` 또는 `post_review_session_results` 테이블이 생성된 이후
코드에 새 컬럼이 추가된 경우, 기존 migration SQL만으로는 컬럼이 추가되지 않는다.

확인된 drift 목록:

| 테이블 | 누락 컬럼 | 증상 |
|--------|-----------|------|
| `post_review_runs` | `candidate_count`, `suspicious_count`, `summary_text_json` | `column does not exist` — `save_bundle()` INSERT 실패 |
| `post_review_session_results` | `evidence_summary`, `session_analysis_json`, `backend_delivery_status` | `column does not exist` — `save_bundle()` INSERT 실패 |

### 12.2 수정 파일

| 파일 | 대상 테이블 | 내용 |
|------|-------------|------|
| `005_post_review_runs_schema_drift.sql` | `post_review_runs` | 누락 컬럼 추가 → COALESCE 단일 UPDATE 백필 → NOT NULL 강제 → CHECK 제약 추가 |
| `006_post_review_session_results_schema_drift.sql` | `post_review_session_results` | 누락 컬럼 추가 → COALESCE 단일 UPDATE 백필 → NOT NULL 강제 → CHECK 제약 추가 |

### 12.3 idempotency 보장

- `ADD COLUMN IF NOT EXISTS`: 이미 있으면 no-op
- COALESCE 단일 UPDATE: 이미 NOT NULL 값이 있는 행에는 영향 없음 (`NULL OR NULL OR NULL` 조건이 false)
- `ALTER COLUMN ... SET NOT NULL`: PostgreSQL은 이미 NOT NULL이면 무시
- `DO $$ ... IF NOT EXISTS ... $$` CHECK 제약: 이미 있으면 no-op

COALESCE 단일 UPDATE는 3개 컬럼을 한 번의 테이블 스캔과 하나의 잠금으로 처리한다.
3개 별도 UPDATE 대비 잠금 시간과 I/O가 1/3로 줄어든다.

### 12.4 확인 방법

```bash
# 4개 파일이 dry-run에 포함되어야 한다
tm-ai-storage-migrate --dry-run
# 기대 출력:
# planned 001_post_review_tables.sql
# planned 002_postgresql_policy_control_plane_tables.sql
# planned 005_post_review_runs_schema_drift.sql
# planned 006_post_review_session_results_schema_drift.sql
# ... JSON summary with "output_count": 4, "status": "dry_run"
```

### 12.5 재발 방지

`SaveContractTests` (in `tests/defense/test_backoffice_copilot_storage.py`)가
serializer output key, INSERT SQL column list, UPSERT SQL column list의 3-way 일치를 상시 검증한다.

새 컬럼을 추가할 때:
1. `PostReviewRunRecord` 또는 `PostReviewSessionResultRecord` 모델 필드 추가
2. `serialize_run_record()` 또는 `serialize_session_result_record()` key 추가
3. `_INSERT_*_SQL` 및 `_UPSERT_*_SQL` column list 추가
4. `001_post_review_tables.sql` DDL 컬럼 추가 (신규 환경용)
5. 새 drift migration 파일 추가 (기존 환경용, 파일명은 다음 번호 순서)
6. `_POSTGRES_MIGRATION_FILES`에 새 파일 등록

---

## 13. 확인 파일

- `src/traffic_master_ai/defense/storage_env.py`
- `src/traffic_master_ai/defense/api/etl_worker.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
- `src/traffic_master_ai/defense/d0_mvp/api/runtime.py`
