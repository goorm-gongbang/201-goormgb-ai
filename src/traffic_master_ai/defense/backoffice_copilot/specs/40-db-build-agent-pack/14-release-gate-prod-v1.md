# Prod V1 Release Gate Review

## 1. 문서 목적

이 문서는 Task A~E까지 반영된 code, smoke, runbook, drift 결과를 기준으로
현재 상태가 prod v1 release gate를 통과하는지 최종 판정한다.

이번 문서의 목적은 6가지다.

- prod v1 선언 가능 여부를 명시
- 완료된 범위를 축별로 고정
- 남은 gap과 known issue를 blocker / non-blocker로 분리
- local real-storage smoke와 managed infra 미검증 범위를 구분
- 운영 투입 전 추가 확인 항목을 정리
- 다음 phase handoff 입력을 남김

이번 문서는 신규 기능 설계 문서가 아니다.
현재 구현 상태에 대한 final gate review 문서다.

---

## 2. 최종 판정

### 2.1 prod v1 선언 가능 여부

`제한적 선언 가능`

의미:

- 현재 저장소는 ClickHouse ingest, ClickHouse read model, PostgreSQL control-plane, PostgreSQL -> Redis projection, runtime strict authority, prod env / fail-fast, replay / resync / runbook까지 최소 운영 경계를 갖췄다.
- local container 기준 real PostgreSQL / Redis / ClickHouse smoke도 통과했다.
- admin/operator/optimizer 성격의 policy write 공식 경로도 `PostgreSQL authoritative write -> Redis projection sync`로 통일됐다.
- 하지만 managed infra 검증과 actual object store replay 검증은 아직 없다.

즉 지금 상태는
"제한된 운영 조건과 수동 절차를 전제로 한 prod v1 선언"까지는 가능하지만,
"managed production environment에서 추가 확인 없이 즉시 확장 운영"으로 읽으면 안 된다.

### 2.2 선언 해석 규칙

이번 판정에서 `제한적 선언 가능`은 아래를 뜻한다.

1. authoritative storage 경계와 runtime strict authority는 코드상 고정돼 있다.
2. runbook과 replay / resync surface는 존재한다.
3. local container 기준 실제 저장소 smoke는 통과했다.
4. managed infra 검증과 actual object store replay 검증은 gate 밖에 남아 있다.

---

## 3. 축별 release gate 상태

| 축 | 판정 | 완료 범위 | 남은 gap |
| --- | --- | --- | --- |
| ClickHouse ingest | conditional pass | canonical audit -> raw fact mapping, ETL batch ingest, fail-fast, replay surface, local container ClickHouse smoke 통과 | managed ClickHouse auth/TLS 검증, processed-key ledger, async insert hardening |
| ClickHouse read model | conditional pass | session/match/candidate read model SQL object, reader repository, real ClickHouse read smoke 통과 | MV/backfill/recompute orchestration, stronger match_id authority |
| PostgreSQL control-plane | conditional pass | 4테이블 repository, strict authority service, optimizer/admin official write path, real PostgreSQL write/read smoke 통과 | managed PostgreSQL validation 미완료 |
| PostgreSQL -> Redis projection | conditional pass | sync/resync helper, overwrite projection, real Redis projection smoke 통과 | background worker/scheduler, lag alerting, managed Redis validation 미완료 |
| runtime strict authority | pass for current minimum scope | Redis read only, local/file/in-memory fallback 차단, stale/missing explicit surfacing | stale threshold tuning, repair orchestration policy 보강 |
| prod env / fail-fast | pass | prod required env validator와 금지 fallback가 코드에 존재 | deployment system / secret distribution은 아직 범위 밖 |
| failure handling / replay / resync | pass for current minimum scope | typed error, retry/replay/resync entrypoint, runbook 절차 존재 | async retry framework, DLQ, structured alerting 없음 |
| local real-storage smoke | pass | PostgreSQL/Redis/ClickHouse local container 기반 observability + control-plane/runtime smoke 통과 | real S3 smoke 없음 |
| managed infra 검증 | open blocker | 없음 | managed PostgreSQL / Redis / ClickHouse auth/TLS/network policy 검증 필요 |

---

## 4. 완료된 범위

### 4.1 observability 축

완료:

- S3 archive-shaped input -> ClickHouse `defense_audit_events` batch ingest
- ClickHouse `defense_session_rollups`
- ClickHouse `defense_match_rollups`
- ClickHouse `defense_post_review_candidates_v1`
- ClickHouse read-model repository와 Backoffice input bundle
- local container 기준 real ClickHouse ingest/read smoke

### 4.2 control-plane / runtime authority 축

완료:

- PostgreSQL `policy_versions`
- PostgreSQL `policy_rollout_state`
- PostgreSQL `policy_rollout_events`
- PostgreSQL `policy_optimization_runs`
- PostgreSQL -> Redis projection sync / resync
- runtime strict Redis read-only authority
- local container 기준 real PostgreSQL write/read + Redis projection + strict runtime read smoke

### 4.3 운영 안전장치 축

완료:

- prod required env validator
- fail-fast / explicit degraded surfacing
- ClickHouse replay surface
- projection sync / resync surface
- migration / bootstrap / cutover / rollback runbook
- real storage smoke guide

---

## 5. blocker 와 non-blocker

### 5.1 blocker

아래 2개는 unrestricted prod 선언을 막는 blocker다.

1. managed infra 검증 부재
   - managed PostgreSQL auth / TLS / connection policy 미검증
   - managed Redis auth / TLS / connection policy 미검증
   - managed ClickHouse auth / TLS / HTTP/network policy 미검증
2. actual object store replay smoke 부재
   - observability replay source는 runbook상 S3 authoritative archive인데,
     실제 smoke는 fake S3 body까지만 검증했다.
### 5.2 non-blocker

아래는 prod v1 minimum scope 밖의 non-blocker다.

1. ClickHouse async insert / pool hardening
2. processed-key ledger / scheduler / replay orchestration
3. MV/backfill hardening
4. projection lag alerting / scheduler
5. `AuditWarehouse` JSONL MVP 제거

이 항목들은 중요하지만,
이번 gate에서 prod v1 minimum 여부를 가르는 직접 blocker로 보지는 않는다.

---

## 6. known issue / 운영 투입 전 추가 확인 필요 항목

운영 투입 전 최소 확인 항목:

1. managed PostgreSQL / Redis / ClickHouse에 대해 [13-real-storage-smoke-guide.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md)와 동일한 write/read smoke를 1회 이상 실행
2. `12-production-operations-runbook.md` 기준으로 cutover / rollback dry-run 수행
3. actual object store archive 1개를 기준으로 `ETLWorker.replay_key()` 또는 `run_etl_replay_keys()` smoke 수행
4. initial policy seed / rollout seed를 strict authority service 기준 공식 operator path로 실행할 절차를 확정
5. prod env matrix
   - `TM_PG_URL`
   - `TM_REDIS_URL`
   - `TM_CLICKHOUSE_URL`
   - `TM_S3_BUCKET`
   - `TM_ROLLOUT_SALT`
   - `TM_POLICY_ALLOW_LOCAL_FALLBACK=false`
   - `TM_ALLOW_IN_MEMORY_REDIS=false`
   를 실제 배포 환경에 주입했는지 확인

---

## 7. 후속 backlog

우선순위 순서:

1. managed infra-backed smoke
   - PostgreSQL
   - Redis
   - ClickHouse
   - actual object store replay
2. observability hardening
   - processed-key ledger
   - async insert / scheduler
   - read-model MV/backfill
3. control-plane 운영 hardening
   - projection lag detection
   - resync worker / alerting
4. MVP cleanup
   - `AuditWarehouse` JSONL path 축소 또는 제거

---

## 8. handoff 시 주의사항

1. local container smoke 통과를 managed production validation 완료로 읽으면 안 된다.
2. strict authority와 control-plane official write path는 완성됐지만 managed infra smoke 전에는 확장 운영으로 읽으면 안 된다.
3. observability replay source는 여전히 S3 authoritative archive라는 원칙을 유지해야 한다.
4. release gate를 다시 열 때는 runbook과 smoke guide를 같이 갱신해야 한다.
5. 이 문서의 판정은 "현재 코드와 현재 검증 범위" 기준이다.
   managed infra 검증이 끝나면 판정은 다시 상향 또는 유지 판단을 해야 한다.

---

## 9. 핵심 handoff 입력

- [11-final-drift-review-and-handoff.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md)
- [12-production-operations-runbook.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md)
- [13-real-storage-smoke-guide.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md)
- [task-execution-log.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md)
