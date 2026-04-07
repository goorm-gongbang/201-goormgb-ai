# Final Drift Review and Handoff

## 1. 문서 목적

이 문서는 Task 8~17에서 반영한 SQL, code, test 결과를
`32-storage-architecture.md`와 `33-docs-vs-current-code-gap-analysis.md` 기준으로 최종 대조한다.

이번 문서의 목적은 5가지다.

- 현재 완료된 구현 범위를 축별로 고정
- 아직 미구현인 범위를 축별로 고정
- 문서와 코드 사이 잔여 drift를 명시
- 다음 phase backlog 입력을 정리
- handoff 시 잘못 해석하기 쉬운 주의사항을 남김

이번 문서는 신규 기능 설계 문서가 아니다.
현재 저장소 상태를 마감 기준으로 정리하는 문서다.

---

## 2. 먼저 드러내는 핵심 결론

Task 8~17 + Task A/B/C 기준으로 아래는 완료됐다.

1. 최소 SQL contract는 저장소 SQL 파일로 반영됐다.
2. ClickHouse raw fact writer와 S3 archive -> ClickHouse ingest 최소 경로가 생겼고, session rollup/candidate reader skeleton도 생겼다.
3. PostgreSQL control-plane repository, strict authoritative service, PostgreSQL -> Redis projection sync/resync 경로가 생겼다.
4. runtime read adapter는 PostgreSQL direct read 없이 Redis projection만 읽고, prod에서는 local/file/in-memory fallback과 implicit bootstrap이 차단된다.
5. env/config, failure handling, unit/contract/smoke test가 최소 범위로 반영됐다.
6. prod required env validator, retry/replay/resync 운영 surface, migration/cutover/rollback runbook이 생겼다.

하지만 아래는 아직 목표 아키텍처까지 도달하지 않았다.

1. `etl_worker.py`는 ClickHouse ingest로 전환됐지만 processed-key ledger, async insert, scheduler 같은 운영 hardening은 아직 없다.
2. `AuditWarehouse`는 여전히 JSONL local adapter다.
3. managed PostgreSQL / Redis / ClickHouse auth/TLS/network policy와 actual object store replay smoke는 아직 없다.

즉 현재 상태는
"목표 구조에 맞는 최소 경계를 코드와 테스트로 고정한 단계"이지,
"production architecture가 전부 실제 infra-backed로 연결된 단계"는 아니다.

---

## 3. 축별 최종 상태

| 축 | 상태 | 현재 완료 범위 | 아직 미구현 범위 |
| --- | --- | --- | --- |
| SQL / schema | partial complete | `001_post_review_tables.sql`, `002_postgresql_policy_control_plane_tables.sql`, `003_clickhouse_defense_audit_events.sql`, `004_clickhouse_read_models.sql` 존재 | richer typed field / stricter apply orchestration 없음 |
| ClickHouse raw fact write | minimal complete | writer repository, canonical audit mapping, HTTP batch client, S3 archive -> ClickHouse ETL worker, env/config, failure handling, local container ClickHouse integration smoke 존재 | auth/pool/async insert hardening, persistent processed-key ledger, managed/service-level integration smoke 없음 |
| session / match / candidate read models | minimal complete | actual ClickHouse view objects, query DTO, row DTO, HTTP select client, reader repository, Backoffice input bundle, tests/smoke 존재 | stronger match_id authority, MV/backfill hardening, workflow-level full adoption 없음 |
| PostgreSQL control-plane repository | minimal complete | 4개 authoritative repository, DTO, conflict policy, failure handling, strict authority service, optimizer/admin official write path, local container PostgreSQL write/read smoke 존재 | managed/service-level integration smoke 부족 |
| PostgreSQL -> Redis projection | minimal complete | projection payload model, Redis projection repository, sync/resync helper, strict overwrite flow, local container Redis projection/runtime smoke 존재 | background projection worker / scheduler / managed Redis integration 없음 |
| runtime read adapter | minimal complete | Redis projection decode, strict-authority loader integration, prod fallback 차단, tests/smoke 존재 | production stale threshold tuning, projection repair orchestration 정책 부족 |
| env / config | minimal complete | shared config loader, ClickHouse/PostgreSQL/Redis/S3 wiring, prod required env validator, env fail-fast/no-op 존재 | secrets/prod deployment wiring, strict rollout salt policy 없음 |
| failure handling | minimal complete | typed error, retry entrypoint, replay/resync hint, operator replay/resync surface, tests 존재 | async retry framework, dead-letter queue, structured alerting 없음 |
| unit / contract tests | complete for current minimum scope | repository / adapter / projection / runtime read / config / failure handling contract test 존재 | long-running workload / failure injection matrix 없음 |
| integration / smoke tests | minimal complete | fake/stub 기반 cross-layer smoke + local container PostgreSQL/Redis/ClickHouse infra-backed smoke 존재 | managed service auth/TLS/network policy 검증, full end-to-end cutover rehearsal 없음 |

---

## 4. 완료된 구현 범위

### 4.1 SQL / schema

완료:

- PostgreSQL final result 2테이블 유지
- PostgreSQL control-plane 4테이블 추가
- ClickHouse `defense_audit_events` 최소 raw fact DDL 추가
- ClickHouse session/match/candidate read-model view 추가

확정 파일:

- [001_post_review_tables.sql](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/sql/001_post_review_tables.sql)
- [002_postgresql_policy_control_plane_tables.sql](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/sql/002_postgresql_policy_control_plane_tables.sql)
- [003_clickhouse_defense_audit_events.sql](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql)
- [004_clickhouse_read_models.sql](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/sql/004_clickhouse_read_models.sql)

### 4.2 ClickHouse raw fact / read model 경계

완료:

- raw fact insert DTO
- raw fact writer repository skeleton
- canonical audit -> raw fact mapping helper
- HTTP batch client
- S3 archive -> ClickHouse ETL worker
- session rollup / match rollup / candidate view SQL object
- session rollup / match rollup / candidate reader repository
- Backoffice input bundle loader
- ClickHouse env/config surface
- ClickHouse write failure typed error / retry entrypoint

확정 파일:

- [clickhouse_validators.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_validators.py)
- [clickhouse_repository.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_repository.py)
- [clickhouse_ingest.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_ingest.py)
- [clickhouse_read_models.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py)
- [clickhouse_read_repository.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_repository.py)
- [clickhouse_connection.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py)
- [004_clickhouse_read_models.sql](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/sql/004_clickhouse_read_models.sql)
- [etl_worker.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/etl_worker.py)

### 4.3 PostgreSQL control-plane / Redis projection / runtime read

완료:

- PostgreSQL control-plane DTO / repository
- Redis projection payload model / projection repository
- strict authoritative service
- runtime Redis read adapter / strict loader integration
- projection retry / sync / reconcile helper
- runtime stale/missing projection fail-fast or explicit degraded surfacing

확정 파일:

- [policy_control_plane_models.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_models.py)
- [policy_control_plane_repository.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py)
- [policy_projection_models.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_models.py)
- [policy_projection_repository.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py)
- [runtime_read_adapter.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py)
- [loader.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/policy/loader.py)
- [runtime.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/api/runtime.py)

### 4.4 env / config / failure / test

완료:

- shared env loader
- runtime/loader/warehouse/etl wiring
- explicit fail-fast/no-op rules
- typed failure surface
- production operations runbook
- real storage smoke guide
- unit / contract / smoke test

확정 파일:

- [storage_env.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/storage_env.py)
- [etl_worker.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/etl_worker.py)
- [runtime.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/api/runtime.py)
- [warehouse.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py)
- [12-production-operations-runbook.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md)
- [13-real-storage-smoke-guide.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md)
- [tests/defense](/Users/shadowmoon/201-goormgb-ai-1/tests/defense)

---

## 5. 아직 미구현인 범위

아래는 목표 구조 문서에는 있으나, 이번 phase에서 구현하지 않은 범위다.

### 5.1 ClickHouse 실제 운영 계층

- ClickHouse auth/pool/async insert wiring hardening
- processed archive key ledger 또는 move/mark-processed orchestration
- stronger match_id authority before reliable match-centric analytics
- raw fact -> session/match rollup MV hardening
- candidate view backfill/recompute orchestration

### 5.2 runtime / projection 운영 계층

- PostgreSQL authoritative write 이후 background projection worker orchestration
- scheduler/background reconcile
- stale projection threshold의 운영 정책 튜닝
- projection lag/repair 운영 관제

### 5.3 실제 infra-backed 통합 잔여 범위

- local container smoke를 넘는 managed PostgreSQL integration
- local container smoke를 넘는 managed Redis integration
- local container smoke를 넘는 managed ClickHouse integration
- full end-to-end cutover rehearsal

### 5.4 observability 과도기 제거

- JSONL MVP `AuditWarehouse` 제거 또는 축소
- `TM_WAREHOUSE_FILENAME` current-code-only env 정리
- ClickHouse ETL worker에 scheduler/replay orchestration 추가

---

## 6. 문서-코드 drift 또는 잔여 리스크

### 6.1 `32-storage-architecture.md`와의 주요 drift

1. `32`는 ClickHouse를 observability main warehouse로 고정하지만,
   현재 코드는 [warehouse.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py)에 JSONL MVP를 여전히 유지한다.
2. `32`는 S3 -> ClickHouse ingest와 replay-aware 운영 흐름을 전제하지만,
   현재 [etl_worker.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/etl_worker.py#L1)은 prefix scan + per-run local dedupe 기반의 최소 ETL만 구현한다.
3. `32`는 `match_id`, `http_status`, dedup flag, rollout stage 등 richer typed field를 raw fact에 기대하지만,
   현재 Task 2/8 구현은 [003_clickhouse_defense_audit_events.sql](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql)에 최소 field만 잠갔다.
4. `32`는 session rollup / match rollup / candidate view를 실제 ClickHouse object로 기대하는데,
   현재 코드는 최소 VIEW object까지는 반영됐지만 MV/backfill/ops orchestration까지는 아직 없다.

### 6.2 `33-docs-vs-current-code-gap-analysis.md`와 비교한 진척

`33`에서 “아직 없다”고 했던 아래는 이번 phase에서 일부 해소됐다.

- ClickHouse raw fact writer skeleton
- ClickHouse actual ingest minimum path
- PostgreSQL control-plane repository
- PostgreSQL -> Redis projection
- runtime Redis projection read adapter + strict authority
- env/failure/test 최소 골격

하지만 아래는 여전히 `33`의 과도기 설명이 그대로 유효하다.

- ClickHouse read-model hardening 미구현
- JSONL MVP warehouse 잔존
- ETL 운영 hardening 부재
- local container 기준 infra-backed smoke는 생겼지만 managed/service-level integration은 아직 없다

### 6.3 운영 리스크

- retry는 synchronous entrypoint만 있고 background worker가 없다.
- `TM_ROLLOUT_SALT`는 local 호환을 위해 weak default를 아직 허용한다.
- engine별 SQL이 `storage/sql` 아래 한 디렉터리에 공존하므로 apply orchestration이 필요하다.

---

## 7. 후속 backlog 또는 다음 phase 입력

다음 phase는 아래 순서가 가장 자연스럽다.

1. ClickHouse ingest hardening
   - processed-key ledger 또는 archive move/mark-processed
   - auth/pool/async insert
   - replay / scheduler orchestration
2. ClickHouse read-model hardening
   - VIEW -> MV/table 승격 여부 결정
   - match_id authority 강화
   - recompute/backfill 절차 고정
3. control-plane strict authority hardening
   - projection lag/repair 운영 정책
   - managed operator workflow dry-run
4. actual repository based verification / cutover drill
   - prod env matrix check
   - replay / resync / rollback rehearsal
   - runbook dry-run
5. infra-backed integration test
   - PostgreSQL
   - Redis
   - ClickHouse

핵심 handoff 입력 파일:

- [11-final-drift-review-and-handoff.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md)
- [12-production-operations-runbook.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md)
- [14-release-gate-prod-v1.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/14-release-gate-prod-v1.md)
- [task-execution-log.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md)
- [32-storage-architecture.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md)
- [33-docs-vs-current-code-gap-analysis.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/33-docs-vs-current-code-gap-analysis.md)

---

## 8. handoff 시 주의사항

1. 현재 구현을 `ClickHouse production ready`로 읽으면 안 된다.
   raw fact ingest minimum path와 read-model VIEW는 생겼지만, 운영 hardening과 stricter authority까지 끝난 상태는 아니다.
2. `etl_worker.py`를 target architecture의 최종 구현으로 읽으면 안 된다.
   현재는 ClickHouse raw-fact ETL까지 구현됐지만, scheduler/processed-key ledger/infra-backed retry는 아직 없다.
3. `AuditWarehouse` JSONL MVP를 production source로 고정하면 안 된다.
   과도기 adapter로만 취급해야 한다.
4. Task 2/8 최소 raw fact contract 밖의 field를 임의 확장하면 안 된다.
   `match_id`, `http_status`, rollout metadata 등은 후속 phase에서 문서 갱신 후 넣어야 한다.
5. next phase는 `task-execution-log.md`를 우선 읽고 이어야 한다.
   Task 8~17의 의도와 미완료 지점이 모두 누적돼 있다.
6. 운영 절차는 코드만 보고 추정하지 말고 runbook을 기준으로 실행해야 한다.
   retry / replay / resync / cutover / rollback 순서는 [12-production-operations-runbook.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md)에 고정돼 있다.
