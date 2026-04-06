# Real Storage Smoke Guide

## 1. 문서 목적

이 문서는 fake/stub 기반 smoke를 넘어서
실제 PostgreSQL / Redis / ClickHouse 저장소에 붙여
현재 저장소 경계가 실제 infra 기준으로 동작하는지 확인하는 최소 절차를 고정한다.

이번 문서는 production 운영 절차 전체 문서가 아니다.
local container 기반 infra-backed smoke를 반복 가능하게 만드는 실행 가이드다.

---

## 2. 검증 대상 흐름

### 2.1 control-plane / runtime

- PostgreSQL `policy_versions` write/read
- PostgreSQL `policy_rollout_state` write/read
- PostgreSQL `policy_rollout_events` append/read
- PostgreSQL `policy_optimization_runs` write/read
- PostgreSQL -> Redis projection sync
- strict runtime `PolicyLoader.from_env()` read

### 2.2 observability

- archive-style JSONL input -> `ETLWorker.replay_key()`
- ClickHouse `defense_audit_events` raw fact insert
- ClickHouse `defense_session_rollups` read
- ClickHouse `defense_match_rollups` read
- ClickHouse `defense_post_review_candidates_v1` read

---

## 3. infra 전제

필수:

- Docker Desktop 또는 Docker daemon
- `python3`
- `pip`
- Python package
  - `sqlalchemy`
  - `redis`

포트:

- PostgreSQL: `127.0.0.1:35432`
- Redis: `127.0.0.1:36379`
- ClickHouse HTTP: `127.0.0.1:38123`

compose 파일:

- [docker-compose.storage-smoke.yml](/Users/shadowmoon/201-goormgb-ai-1/tests/defense/infra/docker-compose.storage-smoke.yml)

---

## 4. 실행 방법

### 4.1 Python package 준비

```bash
python3 -m pip install sqlalchemy redis
```

PEP 668 환경이면 아래처럼 별도 venv를 사용한다.

```bash
python3 -m venv .venv-storage-smoke
./.venv-storage-smoke/bin/python -m pip install sqlalchemy redis 'psycopg[binary]'
```

### 4.2 local infra 기동

```bash
docker compose \
  -f tests/defense/infra/docker-compose.storage-smoke.yml \
  up -d --wait
```

### 4.3 strict prod-like env export

```bash
export TM_REAL_STORAGE_SMOKE=1
export TM_ENV=prod
export TM_PG_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:35432/postgres'
export TM_REDIS_URL='redis://127.0.0.1:36379/0'
export TM_CLICKHOUSE_URL='http://default:clickhouse@127.0.0.1:38123/default'
export TM_S3_BUCKET='storage-smoke-bucket'
export TM_ROLLOUT_SALT='storage-smoke-salt'
export TM_POLICY_ALLOW_LOCAL_FALLBACK=false
export TM_ALLOW_IN_MEMORY_REDIS=false
```

### 4.4 실제 저장소 smoke 실행

```bash
PYTHONPATH=src ./.venv-storage-smoke/bin/python -m unittest tests.defense.test_storage_integration_real
```

성공 기준:

- `Ran 2 tests`
- `OK`

### 4.5 종료

```bash
docker compose \
  -f tests/defense/infra/docker-compose.storage-smoke.yml \
  down -v
```

---

## 5. 실패 해석 가이드

### 5.1 PostgreSQL 단계에서 실패

- `TM_PG_URL` 오타 또는 container readiness 문제를 먼저 본다.
- `002_postgresql_policy_control_plane_tables.sql` apply 실패면 schema drift 가능성이 크다.
- repository write/read 실패면 storage contract 또는 SQLAlchemy dependency 문제로 본다.

### 5.2 Redis projection 단계에서 실패

- `TM_REDIS_URL` 과 prod fallback 차단 env를 먼저 확인한다.
- PostgreSQL write 성공 후 projection apply 실패면 `RedisProjectionApplyError` 또는 authority sync sequencing 문제로 본다.

### 5.3 ClickHouse 단계에서 실패

- `TM_CLICKHOUSE_URL` 과 `003` / `004` SQL apply 여부를 먼저 본다.
- ETL replay는 fake S3 body를 쓰지만 저장 대상은 실제 ClickHouse다.
- raw fact insert는 되는데 read model 조회가 안 되면 `004_clickhouse_read_models.sql` drift를 먼저 의심한다.

---

## 6. 현재 한계

- S3는 실제 object store가 아니라 archive-shaped fake client로 대체한다.
- Docker local container 기준 smoke라서 managed service auth/TLS는 검증하지 않는다.
- scheduler, lag alerting, long-running replay worker는 이 smoke 범위 밖이다.
