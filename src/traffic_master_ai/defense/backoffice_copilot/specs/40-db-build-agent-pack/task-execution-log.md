# DB Build Task Execution Log

## Task 1

### 1. task 번호와 제목

- Task 1. canonical audit 최소 필드 확정

### 2. 작업 일시

- backfill from user-reported result after Task 1 completion

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/04-canonical-audit-minimum-contract.md`

### 4. 파일별 수정 요약

- `04-canonical-audit-minimum-contract.md`: 현재 코드와 목표 구조의 충돌을 먼저 드러내고, 최소 typed field 목록, JSON 보존 컬럼 후보, 현재 코드와의 gap 메모, 현재 기준 안전한 join 관점, privacy 및 undocumented 금지 필드만 최소 범위로 고정했다.

### 5. 검증에 사용한 명령과 결과 요약

- 수동 문서 대조
  - 기준 문서: `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `31-observability-merge-strategy.md`, `defense_observability_ssot.yaml`, `audit.py`, `main.py`
  - 결과: 문서 간 목표 구조와 현재 코드 공백을 숨기지 않고 정리했으며, Task 2 입력으로 사용할 최소 계약과 모순이 없도록 확인했다.
- 관련 테스트 파일 탐색
  - 결과: canonical audit payload 계약을 직접 잠그는 관련 테스트 파일은 찾지 못했다.

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - `event_type` taxonomy가 SSOT와 현재 코드 사이에서 다르다.
  - `action` enum이 target 의미와 완전히 정렬되지 않았다.
  - `match_id`가 canonical audit top-level typed field로 안정적으로 보장되지 않는다.
- Task 2에 넘길 입력
  - non-null typed field: `ts_ms`, `session_id`, `event_type`
  - nullable typed field: `trace_id`, `challenge_id`, `flow_state`, `risk_tier`, `action`, `reason_code`, `policy_version`
  - JSON preservation: `raw_payload_json`
  - 기본 join guidance: `session_id + ts_ms window`
  - explicit gap: `match_id`, `http_status`, `dedup_is_duplicate`, rollout fields, VQA typed fields

## Task 2

### 1. task 번호와 제목

- Task 2. ClickHouse `defense_audit_events` 최소 DDL 초안 작성

### 2. 작업 일시

- 2026-04-06 02:01:45 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/05-defense-audit-events-minimum-ddl.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `05-defense-audit-events-minimum-ddl.md`: Task 1 최소 계약을 입력으로 받아 `defense_audit_events` 최소 raw fact DDL 초안을 문서화했다. non-null typed column, nullable typed column, `raw_payload_json` 보존 컬럼, partition key, order key, 현재 코드 매핑 여부, explicit gap, 적재 가정, Task 3 입력을 함께 고정했다.
- `task-execution-log.md`: Task 2 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 입력 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `04-canonical-audit-minimum-contract.md`, `31-observability-merge-strategy.md`, `defense_observability_ssot.yaml`, `audit.py`, `main.py`
  - 결과: Task 1 최소 계약과 일관된 최소 DDL만 남기고, `match_id`/dedup/VQA/rollout 계열은 explicit gap으로 분리했다.
- 민감 필드 위치 확인
  - 명령: `rg -n "active_challenge_token|user_id|challenge_token|Authorization|headers" src/traffic_master_ai/defense/api/models.py src/traffic_master_ai/defense/api/main.py src/traffic_master_ai/defense/api/audit.py`
  - 결과: `runtime_state` blind copy는 privacy 규칙과 충돌하므로 `raw_payload_json`은 sanitation 후 보존해야 한다는 메모를 DDL 문서에 반영했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:01:45 KST`

### 6. 남은 리스크 또는 Task 3에 넘길 입력

- 남은 리스크
  - 현재 `event_type` taxonomy가 SSOT authoritative catalog와 다르다.
  - `action` enum 의미가 target semantics와 완전히 정렬되지 않았다.
  - `raw_payload_json`은 blind raw copy가 아니라 sanitation 전제가 필요하다.
  - `match_id`가 top-level typed field로 보장되지 않아 match-centric rollup은 후속 보강이 필요하다.
- Task 3에 넘길 입력
  - raw fact stable columns: `ts_ms`, `session_id`, `event_type`, `trace_id`, `challenge_id`, `flow_state`, `risk_tier`, `action`, `reason_code`, `policy_version`
  - JSON preservation: `raw_payload_json`
  - 기본 join guidance: `session_id + ts_ms window`
  - weak axes kept as gap: `match_id`, dedup, challenge typed result, VQA typed fields, rollout fields

## Task 3

### 1. task 번호와 제목

- Task 3. session rollup / match rollup / candidate view 최소 계약 확정

### 2. 작업 일시

- 2026-04-06 02:06:36 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/06-rollup-candidate-minimum-contract.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `06-rollup-candidate-minimum-contract.md`: Task 1/2 raw fact 계약을 입력으로 받아 `defense_session_rollups`, `defense_match_rollups`, `defense_post_review_candidates_v1`의 최소 컬럼/selection/consumer boundary를 문서로 고정했다. raw fact / session rollup / match rollup / candidate / final result store의 역할 분리, 기본 join 방식, 현재 코드 gap, Task 4 경계를 함께 기록했다.
- `task-execution-log.md`: Task 3 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 문서 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `04-canonical-audit-minimum-contract.md`, `05-defense-audit-events-minimum-ddl.md`, `31-observability-merge-strategy.md`, `defense_observability_ssot.yaml`, `audit.py`, `main.py`
  - 결과: session rollup은 Backoffice 1차 입력, match rollup은 운영 요약, candidate view는 selection layer로만 고정했고 final result 저장 책임과 섞지 않았다.
- 관련 섹션 탐색
  - 명령: `rg -n "Session rollup table|Match rollup table|candidate view|defense_session_rollups|defense_match_rollups|defense_post_review_candidates_v1|session_id \\+ 시간 구간|Backoffice Copilot|Grafana|운영 배치" src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/31-observability-merge-strategy.md`
  - 결과: `32`의 역할 분리와 `31`의 소비자/조인 원칙을 직접 확인해 문서에 반영했다.
- 현재 코드 필드 위치 확인
  - 명령: `rg -n "match_id|matchId|session_id|sessionId|challenge_id|challengeId|reasonCodes|vqaAttemptScore|flow_state|telemetry_features" src/traffic_master_ai/defense/api/main.py src/traffic_master_ai/defense/api/audit.py`
  - 결과: `match_id`는 일부 payload/state key 수준에 머물고, `session_id`도 일부 경로에서 `sid:matchId` alias를 쓰므로 session/window 기준 계약이 더 안전하다는 점을 gap으로 명시했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:06:36 KST`

### 6. 남은 리스크 또는 Task 4에 넘길 입력

- 남은 리스크
  - `match_id`가 raw fact typed column으로 아직 잠기지 않아 `defense_match_rollups`는 target-direction contract에 가깝다.
  - 일부 challenge/VQA row의 `session_id`가 state-key alias를 쓰므로 session identity canonicalization이 후속 과제다.
  - challenge result / VQA result / dedup 집계는 현재 최소 계약에서 제외했다.
- Task 4에 넘길 입력
  - observability read contract boundary: raw fact / session rollup / match rollup / candidate / final result store 역할 분리
  - 기본 join guidance: `session_id + 시간 구간`
  - Backoffice primary input: `defense_session_rollups`, `defense_post_review_candidates_v1`
  - ops summary input: `defense_match_rollups`
  - explicit gap to keep out of control-plane DDL: `match_id`, dedup, challenge/VQA typed aggregation, rollout/policy comparison fields

## Task 4

### 1. task 번호와 제목

- Task 4. PostgreSQL policy control-plane 최소 DDL 초안 작성

### 2. 작업 일시

- 2026-04-06 02:10:10 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/07-policy-control-plane-minimum-ddl.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `07-policy-control-plane-minimum-ddl.md`: `policy_versions`, `policy_rollout_state`, `policy_rollout_events`, `policy_optimization_runs`의 최소 PostgreSQL DDL 초안을 문서화했다. authoritative control-plane과 Redis runtime projection 책임 분리, 현재 코드 매핑 여부, naming mismatch, Task 5 projection 입력을 함께 고정했다.
- `task-execution-log.md`: Task 4 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `06-rollup-candidate-minimum-contract.md`, `policy_v1.yaml`, `defense_policy_optimization_ssot.yaml`, `runtime.py`, `loader.py`, `keyspace.py`, `rollout.py`
  - 결과: observability 축과 섞지 않고 policy control-plane 4테이블 최소 계약만 남겼다.
- 현재 policy/runtime 흐름 확인
  - 명령: `rg -n "policy|rollout|projection|redis|policy_version|candidate|base_policy|rollout_state|tm:decision-policy|assign" src/traffic_master_ai/defense/d0_mvp/api/runtime.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/state/keyspace.py src/traffic_master_ai/defense/d0_mvp/optimizer/rollout.py`
  - 결과: runtime authority는 Redis-first이고 PostgreSQL control-plane은 아직 미구현이라는 점을 gap으로 기록했다.
- 추가 세부 확인
  - 명령: `sed -n '200,240p' src/traffic_master_ai/defense/d0_mvp/api/runtime.py`
  - 결과: bootstrap 시 Redis policy authority와 file fallback만 사용하는 점을 확인했다.
  - 명령: `sed -n '340,430p' src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
  - 결과: policy 문서 직렬화 구조와 rollout state 저장 shape를 확인했다.
  - 명령: `sed -n '90,220p' src/traffic_master_ai/defense/d0_mvp/optimizer/pipeline.py`
  - 결과: optimization run / canary / rollback audit payload에서 `metrics_snapshot_id`, `result`, `new_policy_version` 등의 최소 메타 필드를 확인했다.
- 구현 공백 탐색
  - 명령: `rg -n "policy_versions|policy_rollout_state|policy_rollout_events|policy_optimization_runs" src/traffic_master_ai/defense -g '!**/.venv/**'`
  - 결과: current code에는 PostgreSQL control-plane 4테이블 구현이 없고, 문서/loader 수준 계약만 존재함을 확인했다.
- 테스트 파일 탐색
  - 명령: `rg --files src/traffic_master_ai/defense | rg "test|tests"`
  - 결과: 관련 테스트 파일을 찾지 못했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:10:10 KST`

### 6. 남은 리스크 또는 Task 5에 넘길 입력

- 남은 리스크
  - current runtime은 PostgreSQL control-plane을 전혀 읽지 않고 Redis/file store를 사용한다.
  - `tm:policy:*` vs `tm:decision-policy:*` naming mismatch가 문서와 코드 사이에 남아 있다.
  - DB용 `run_id` / `rollout_id` / `event_id`는 current code에 없어 projection/ingest 설계가 후속 과제다.
- Task 5에 넘길 입력
  - authoritative source tables: `policy_versions`, `policy_rollout_state`, `policy_rollout_events`, `policy_optimization_runs`
  - Redis projection targets: `tm:decision-policy:version:{policyVersion}`, `tm:decision-policy:rollout-state`, `tm:decision-policy:version-index`
  - runtime read rule: PostgreSQL direct read 금지, Redis projection만 사용
  - explicit gap: key naming mismatch, DB identity fields 신규 도입, bootstrap rollout state vs DB authoritative state shape 차이

## Task 5

### 1. task 번호와 제목

- Task 5. PostgreSQL -> Redis projection 계약 문서화

### 2. 작업 일시

- 2026-04-06 02:14:51 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/08-postgresql-to-redis-projection-contract.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `08-postgresql-to-redis-projection-contract.md`: PostgreSQL authoritative control-plane에서 Redis runtime projection으로 내려가는 최소 계약을 문서화했다. projection 대상 key 3종, 각 key의 최소 payload, source mapping, apply ordering, projection failure 규칙, runtime read path와 projection worker 경계를 함께 고정했다.
- `task-execution-log.md`: Task 5 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `07-policy-control-plane-minimum-ddl.md`, `policy_v1.yaml`, `defense_policy_optimization_ssot.yaml`, `runtime.py`, `loader.py`, `keyspace.py`, `rollout.py`
  - 결과: PostgreSQL authoritative source와 Redis projection 책임을 분리하고, request path direct PostgreSQL 금지 원칙을 유지한 최소 계약만 남겼다.
- 현재 Redis keyspace / read path 확인
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/state/keyspace.py | sed -n '1,220p'`
  - 결과: 현재 코드 keyspace가 `tm:decision-policy:version:{policyVersion}`, `tm:decision-policy:rollout-state`, `tm:decision-policy:version-index`임을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/policy/loader.py | sed -n '1,220p'`
  - 결과: Redis policy store가 version doc JSON, rollout state JSON, version index JSON array를 읽고 쓴다는 점을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/policy/loader.py | sed -n '220,360p'`
  - 결과: runtime selection이 `stage`, `base_policy_version`, `candidate_policy_version`, `ratio`에 의존하고 `current_version` 키를 읽지 않는다는 점을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/api/runtime.py | sed -n '200,280p'`
  - 결과: bootstrap이 Redis-first + file fallback이며 PostgreSQL direct read가 없다는 점을 확인했다.
- rollout state shape 확인
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/optimizer/rollout.py | sed -n '1,240p'`
  - 결과: authoritative rollout state에는 더 많은 필드가 있지만 runtime minimum payload는 더 작게 유지할 수 있음을 확인했다.
- SSOT key naming / contract 확인
  - 명령: `rg -n "tm:policy|tm:decision-policy|rollout_state|policyVersion|version-index|projection|baseline|fallback" src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/policy_v1.yaml src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_policy_optimization_ssot.yaml`
  - 결과: `tm:policy:*` vs `tm:decision-policy:*` naming mismatch와 runtime authority/fallback 의미를 명시적 gap으로 기록했다.
- 테스트 파일 탐색
  - 명령: `rg --files src/traffic_master_ai/defense | rg "test|tests"`
  - 결과: 관련 테스트 파일을 찾지 못했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:14:51 KST`

### 6. 남은 리스크 또는 Task 6에 넘길 입력

- 남은 리스크
  - 현재 코드에는 PostgreSQL -> Redis projection worker와 retry/reconcile 구현이 없다.
  - `policy_v1.yaml`의 `tm:policy:*` 예시와 current code `tm:decision-policy:*` keyspace가 아직 다르다.
  - current bootstrap baseline write는 prod projection contract와 다르다.
- Task 6에 넘길 입력
  - authoritative source: `policy_versions.document_json`, `policy_rollout_state` current authoritative row
  - Redis target keys: `tm:decision-policy:version:{policyVersion}`, `tm:decision-policy:rollout-state`, `tm:decision-policy:version-index`
  - minimum payload: version doc `schemaVersion + parameters + flags`, rollout state `stage + base_policy_version + candidate_policy_version + ratio + updated_at_ms`, version index string array
  - apply ordering: PostgreSQL commit -> referenced version docs -> rollout-state -> version-index
  - failure scenarios: PostgreSQL write fail, Redis projection fail after PG success, Redis eviction, runtime direct PostgreSQL read 금지 유지

## Task 6

### 1. task 번호와 제목

- Task 6. env / failure handling / test plan 정리

### 2. 작업 일시

- 2026-04-06 02:20:06 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/09-env-failure-handling-test-plan.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `09-env-failure-handling-test-plan.md`: 최소 env 변수 목록, env 누락 시 계층별 기대 동작, audit/S3/warehouse/control-plane/projection/runtime failure 규칙, replay/retry/backfill 지점, unit/contract/integration/smoke test 최소 계획, Task 7 구현 검증 기준을 문서로 고정했다.
- `task-execution-log.md`: Task 6 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `31-observability-merge-strategy.md`, `task-execution-log.md`, `08-postgresql-to-redis-projection-contract.md`, `defense_observability_ssot.yaml`, `policy_v1.yaml`, `defense_policy_optimization_ssot.yaml`, `audit.py`, `etl_worker.py`, `runtime.py`, `loader.py`, `keyspace.py`
  - 결과: storage/projection 계약과 충돌하지 않도록 운영 준비용 최소 env/failure/test 규칙만 남겼다.
- 현재 env / adapter 의존성 확인
  - 명령: `rg -n "TM_[A-Z0-9_]+|DATABASE_URL|POSTGRES|CLICKHOUSE|REDIS|S3_BUCKET|S3_REGION|boto3|create_engine|redis\\.from_url|from_env\\(" src/traffic_master_ai/defense -g '!**/.venv/**'`
  - 결과: 현재 코드에 존재하는 `TM_PG_URL`, `TM_REDIS_URL`, `TM_S3_*`, `TM_DEFENSE_AUDIT_LOG_PATH`, `TM_ROLLOUT_SALT`, `TM_POLICY_CACHE_SECONDS`와 ClickHouse 미구현 공백을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/api/database.py | sed -n '1,220p'`
  - 결과: current PostgreSQL 연결 관례가 `TM_PG_URL`임을 확인했다.
- failure path 확인
  - 명령: `nl -ba src/traffic_master_ai/defense/api/audit.py | sed -n '1,360p'`
  - 결과: rotate/upload 실패 시 rotated local file이 남고, `TM_DEFENSE_AUDIT_LOG_PATH` default가 존재함을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/api/etl_worker.py | sed -n '1,360p'`
  - 결과: current ETL이 S3 -> PostgreSQL prototype이며 `TM_S3_BUCKET` 없으면 실행하지 않는다는 점을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/api/runtime.py | sed -n '1110,1205p'`
  - 결과: audit append 실패가 request path를 즉시 중단시키지 않고 exception log로만 드러난다는 점을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/api/state.py | sed -n '80,150p'`
  - 결과: non-CI에서 `TM_REDIS_URL` 누락 시 fail-fast, CI에서만 memory fallback이라는 점을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/state/redis_client.py | sed -n '140,210p'`
  - 결과: d0_mvp Redis backend도 같은 fail-fast 정책을 유지함을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/policy/loader.py | sed -n '74,155p'`
  - 결과: policy runtime authority는 Redis-first이고 file fallback이 남아 있음을 확인했다.
- 테스트 파일 탐색
  - 명령: `rg --files src/traffic_master_ai/defense | rg "test|tests"`
  - 결과: 관련 테스트 파일을 찾지 못했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:20:06 KST`

### 6. 남은 리스크 또는 Task 7에 넘길 입력

- 남은 리스크
  - ClickHouse adapter / ETL / rollup 구현이 아직 없어 warehouse env와 retry 정책은 planned contract 상태다.
  - PostgreSQL control-plane과 projection worker가 아직 없어 projection failure handling은 설계 단계다.
  - 현재 audit append failure는 log에만 드러나며 별도 metric/alert contract는 없다.
- Task 7에 넘길 입력
  - minimum env surface: `TM_DEFENSE_AUDIT_LOG_PATH`, `TM_S3_BUCKET`, `TM_S3_REGION`, `TM_S3_PREFIX`, `TM_S3_ARCHIVE_INTERVAL_SECONDS`, `TM_PG_URL`, `TM_REDIS_URL`, `TM_ROLLOUT_SALT`, `TM_POLICY_CACHE_SECONDS`, planned `TM_CLICKHOUSE_*`
  - fail-fast rules: non-CI `TM_REDIS_URL` 누락, PostgreSQL write 실패 시 projection 금지, ClickHouse env 누락 시 ingest worker 시작 금지
  - fail-safe rules: S3 archive 비활성 허용, audit append failure는 request path 지속 + log 노출, Redis stale-read 후 reconcile
  - replay/backfill source: rotated local files / S3 archive / PostgreSQL authoritative tables
  - test slices: unit env parsing, contract schema mapping, integration ingest/projection/runtime read, smoke startup/env enforcement

## Task 7

### 1. task 번호와 제목

- Task 7. repository / adapter 경계 정리

### 2. 작업 일시

- 2026-04-06 02:42:44 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/10-repository-adapter-boundary.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `10-repository-adapter-boundary.md`: ClickHouse raw fact, session rollup/candidate read model, PostgreSQL control-plane, PostgreSQL -> Redis projection, runtime read path, S3 archive/replay source의 repository / adapter 경계를 문서로 고정했다. 각 계층의 책임, 입출력, 금지 책임, 최소 호출 관계, 구현 순서를 함께 정리했다.
- `task-execution-log.md`: Task 7 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/산출물 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `05-defense-audit-events-minimum-ddl.md`, `06-rollup-candidate-minimum-contract.md`, `07-policy-control-plane-minimum-ddl.md`, `08-postgresql-to-redis-projection-contract.md`, `09-env-failure-handling-test-plan.md`
  - 결과: raw fact / read model / control-plane / projection / runtime read 경계가 앞선 계약과 모순되지 않도록 정리했다.
- 현재 코드 흐름 확인
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py | sed -n '1,360p'`
  - 결과: `AuditWarehouse`가 ClickHouse repository가 아니라 local JSONL warehouse adapter임을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/api/etl_worker.py | sed -n '1,360p'`
  - 결과: current ETL이 S3 -> PostgreSQL prototype insert를 직접 수행하고 있음을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/policy/loader.py | sed -n '74,155p'`
  - 결과: Redis key read/write, version index 관리, file fallback이 loader에 섞여 있음을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/state/keyspace.py | sed -n '1,220p'`
  - 결과: Redis projection keyspace가 `tm:decision-policy:*`로 고정돼 있음을 확인했다.
- 테스트 파일 탐색
  - 명령: `rg --files src/traffic_master_ai/defense | rg "test|tests"`
  - 결과: 관련 테스트 파일을 찾지 못했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:42:44 KST`

### 6. 남은 리스크 또는 구현 단계(Task 8+)에 넘길 입력

- 남은 리스크
  - current code에는 ClickHouse repository, PostgreSQL control-plane repository, Redis projection repository가 전혀 구현돼 있지 않다.
  - `PolicyLoader`와 `AuditWarehouse`가 아직 storage concern과 adapter concern을 함께 가진다.
  - S3 -> ClickHouse ingest와 projection worker 호출 경계는 문서 계약만 있고 실행 코드는 없다.
- Task 8+에 넘길 입력
  - ClickHouse raw fact writer/reader repo 분리
  - session rollup / candidate read repository 분리
  - PostgreSQL control-plane repository 4종
  - Redis projection repository + projection adapter
  - runtime read adapter에서 PostgreSQL direct read 금지 유지
  - S3 archive repo + replay source adapter 분리
