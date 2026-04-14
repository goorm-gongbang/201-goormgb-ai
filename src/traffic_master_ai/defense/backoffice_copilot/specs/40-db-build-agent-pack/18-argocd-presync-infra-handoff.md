# ArgoCD PreSync Infra Handoff

## 목차

1. 최종 자동 배포 순서
2. 공통 원칙
3. PreSync Job 1: storage migrate
4. PreSync Job 2: policy bootstrap
5. PreSync Job 3: policy projection resync
6. ai-defense Deployment
7. optimizer CronJob
8. post-review CronJob
9. 인프라 요청 최소화 원칙
10. 배포 자동화 직전 점검표
11. 303에 넘길 항목
12. 아직 넘기지 않을 항목
13. 인프라팀 전달용 초안

## 1. 최종 자동 배포 순서

| 순서 | 단계 | 실행 주체 | 목적 | 다음 단계 진행 조건 |
|---|---|---|---|---|
| 1 | ArgoCD PreSync Job 1 | `tm-ai-storage-migrate` | PostgreSQL DDL 적용 | exit `0` |
| 2 | ArgoCD PreSync Job 2 | `tm-ai-policy-bootstrap` | baseline policy / rollout seed | exit `0` |
| 3 | ArgoCD PreSync Job 3 | `tm-ai-policy-projection-resync --current` | PostgreSQL current rollout을 Redis runtime projection에 반영 | exit `0` |
| 4 | Deployment rollout | `ai-defense` | runtime API 기동 | readiness / health 통과 |
| 5 | CronJob | `tm-ai-policy-optimizer` | offline policy optimizer 주기 실행 | Deployment env / storage 연결 준비 |
| 6 | CronJob | `tm-ai-post-review` | Backoffice Post-Review 주기 실행 | ClickHouse read model / PostgreSQL 준비 |

최종안:

- 사람이 one-shot Job을 수동으로 치지 않는다.
- ArgoCD sync 시 PreSync Job 3개가 순서대로 실행된다.
- PreSync 실패 시 Deployment와 CronJob rollout은 진행하지 않는다.
- PreSync 성공 뒤 `ai-defense` Deployment와 background CronJob이 붙는다.

## 2. 공통 원칙

공통 command summary:

- 마지막 stdout 줄은 JSON summary다.
- 공통 필드는 `command`, `mode`, `status`, `input_count`, `output_count`, `skipped_count`, `error_count`, `duration_ms`, `dry_run`이다.
- `status=failed`는 exit `1`이다.
- `success`, `skip`, `dry_run`, `no_input`, `disabled`, optimizer skip 계열은 exit `0`이다.

ArgoCD Hook 권장:

- PreSync Job 3개에 `argocd.argoproj.io/hook: PreSync`를 둔다.
- 3개 Job에는 순서 보장을 위해 sync wave를 둔다.
- 권장 wave:
  - storage migrate: `-30`
  - policy bootstrap: `-20`
  - policy projection resync: `-10`
- Hook delete policy는 성공 Job 누적을 피하기 위해 `HookSucceeded`를 기본으로 검토한다.
- 실패 Job 로그 확인이 필요하면 환경별로 `HookFailed` 보존 여부를 선택한다.

Job 공통 권장값:

- `restartPolicy: Never`
- `backoffLimit: 1`
- `activeDeadlineSeconds`: 300 이상
- `ttlSecondsAfterFinished`: 환경 정책에 맞춰 설정

## 3. PreSync Job 1: storage migrate

| 항목 | 계약 |
|---|---|
| command | `tm-ai-storage-migrate` |
| 목적 | PostgreSQL DDL만 적용 |
| 필수 env | `TM_PG_URL` |
| 선택 env | 없음 |
| dry-run | `tm-ai-storage-migrate --dry-run` |
| exit `0` | DDL 적용 성공 또는 dry-run plan 성공 |
| exit `1` | `TM_PG_URL` 누락, SQL file 누락, DDL 실행 실패 |
| summary status | `success`, `dry_run`, `failed` |
| 재실행 가능 여부 | 가능. SQL은 idempotent DDL이어야 한다. |
| 선행 조건 | PostgreSQL 접속 가능 |

적용 범위:

- `001_post_review_tables.sql`
- `002_postgresql_policy_control_plane_tables.sql`

비범위:

- baseline policy seed
- rollout seed
- Redis projection resync
- ClickHouse DDL

다음 단계 진행 조건:

- exit `0`
- summary `status=success`
- dry-run은 실제 배포 PreSync가 아니라 사전 점검에서만 사용한다.

## 4. PreSync Job 2: policy bootstrap

| 항목 | 계약 |
|---|---|
| command | `tm-ai-policy-bootstrap` |
| 목적 | baseline policy와 rollout seed를 PostgreSQL에 생성 |
| 필수 env | `TM_PG_URL` |
| 선택 env | `TM_POLICY_BOOTSTRAP_ROLLOUT_ID`, `TM_POLICY_OPTIMIZER_ROLLOUT_ID` |
| 기본 rollout_id | `offline-optimizer-default` |
| dry-run | `tm-ai-policy-bootstrap --dry-run` |
| exit `0` | 신규 seed 생성 성공, 기존 row skip, dry-run plan 성공 |
| exit `1` | `TM_PG_URL` 누락, table 부재, seed read/write 실패 |
| summary status | `success`, `skip`, `dry_run`, `failed` |
| 재실행 가능 여부 | 가능. 기존 row는 overwrite하지 않고 skip한다. |
| 선행 조건 | PreSync 1 성공 |

정상 skip:

- `policy_versions` baseline row가 이미 있다.
- `policy_rollout_state` 대상 rollout row가 이미 있다.
- 이 경우 summary `status=skip`, exit `0`이다.

다음 단계 진행 조건:

- exit `0`
- `success` 또는 `skip`

## 5. PreSync Job 3: policy projection resync

| 항목 | 계약 |
|---|---|
| command | `tm-ai-policy-projection-resync --current` |
| 목적 | PostgreSQL current rollout을 Redis runtime projection으로 반영 |
| 필수 env | `TM_PG_URL`, `TM_REDIS_URL` |
| 선택 env | `TM_PROJECTION_RETRY_MAX_ATTEMPTS`, `TM_PROJECTION_RETRY_BACKOFF_MS` |
| dry-run | 없음 |
| exit `0` | Redis projection apply 성공 |
| exit `1` | current rollout row 없음, policy row 없음, Redis apply 실패, env 누락 |
| summary status | `success`, `failed` |
| 재실행 가능 여부 | 가능. 같은 current state를 Redis에 overwrite한다. |
| 선행 조건 | PreSync 1, PreSync 2 성공 |

Redis key:

- `tm:decision-policy:version:{policyVersion}`
- `tm:decision-policy:rollout-state`
- `tm:decision-policy:version-index`

다음 단계 진행 조건:

- exit `0`
- summary `status=success`
- 실패하면 `ai-defense` Deployment rollout을 진행하지 않는다.

## 6. ai-defense Deployment

필수 env:

| env | 설명 |
|---|---|
| `TM_ENV` | `prod`, `staging`, `dev` 등 실행 환경 |
| `TM_PG_URL` | PostgreSQL authoritative control plane / post-review output |
| `TM_REDIS_URL` | runtime policy projection / runtime state |
| `TM_ROLLOUT_SALT` | deterministic rollout assignment salt |
| `TM_POLICY_ALLOW_LOCAL_FALLBACK=false` | 운영 local file fallback 금지 |
| `TM_ALLOW_IN_MEMORY_REDIS=false` | 운영 in-memory Redis fallback 금지 |

권장 env:

| env | 설명 |
|---|---|
| `TM_POLICY_PROJECTION_MAX_STALENESS_MS` | Redis projection freshness 제한 |
| `TM_PROJECTION_RETRY_MAX_ATTEMPTS` | projection retry 횟수 |
| `TM_PROJECTION_RETRY_BACKOFF_MS` | projection retry backoff |

선택 env:

| env | 설명 |
|---|---|
| `TM_POLICY_PROJECTION_RECONCILER_INTERVAL_SECONDS` | 내부 projection reconciler interval |
| `TM_POLICY_PROJECTION_RECONCILER_LOCK_TTL_SECONDS` | 내부 reconciler Redis lock TTL |
| `TM_POLICY_PROJECTION_RECONCILER_DISABLED` | 내부 reconciler 비활성화 |

runtime freshness:

- `ai-defense`는 `api/main.py` lifespan에서 `PolicyProjectionReconciler` background task를 띄운다.
- 별도 projection worker Deployment는 기본 요청하지 않는다.
- reconciler는 strict authority, `TM_PG_URL`, `TM_REDIS_URL`, Redis backend 조건이 맞을 때 활성화된다.
- PreSync 3은 최초 projection 준비를 담당하고, Deployment 내부 reconciler는 이후 freshness 유지와 repair를 담당한다.

진행 조건:

- PreSync 3 성공 후 rollout한다.
- runtime startup에서 prod fallback 금지 env가 깨지면 fail-fast 해야 한다.

## 7. optimizer CronJob

| 항목 | 계약 |
|---|---|
| command | `tm-ai-policy-optimizer` |
| 권장 schedule | `*/10 * * * *` |
| 권장 초기 모드 | `TM_POLICY_OPTIMIZER_ENABLED=true`, `TM_POLICY_OPTIMIZER_DRY_RUN=true` |
| apply 전환 | AI팀 승인 후 `TM_POLICY_OPTIMIZER_DRY_RUN=false`, `TM_POLICY_OPTIMIZER_APPLY_ENABLED=true` |
| concurrencyPolicy | `Forbid` |
| restartPolicy | `Never` |
| backoffLimit | `1` |

필수 env:

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

mode 의미:

- `disabled`: env상 비활성, 정상 skip
- `dry_run`: Redis lock과 read/evaluate까지만 수행, mutation 없음
- `apply_blocked`: `DRY_RUN=false`인데 `APPLY_ENABLED=true`가 없어 exit `1`
- `apply`: `APPLY_ENABLED=true`일 때 canary start, rollout expand, rollback 가능

auto-apply gate:

- `TM_POLICY_OPTIMIZER_ENABLED=false`: `disabled`, exit `0`
- `TM_POLICY_OPTIMIZER_ENABLED=true`, `TM_POLICY_OPTIMIZER_DRY_RUN=true`: dry-run, mutation 없음
- `TM_POLICY_OPTIMIZER_ENABLED=true`, `TM_POLICY_OPTIMIZER_DRY_RUN=false`, `TM_POLICY_OPTIMIZER_APPLY_ENABLED=false`: `apply_blocked`, exit `1`
- `TM_POLICY_OPTIMIZER_ENABLED=true`, `TM_POLICY_OPTIMIZER_DRY_RUN=false`, `TM_POLICY_OPTIMIZER_APPLY_ENABLED=true`: apply 가능

자동 허용 mutation:

- canary start
- rollout expand
- rollback

apply post-check:

- mutation 후 PostgreSQL rollout state를 재조회한다.
- Redis rollout projection을 재조회한다.
- stage, base/candidate policy version, ratio, updated_at_ms가 일치해야 한다.
- Redis version index와 policy version key가 필요한 version을 포함해야 한다.
- `projection_refreshed_at_ms`가 존재해야 한다.
- post-check 실패는 `status=failed`, exit `1`이다.

summary 해석:

- 정상 skip: `disabled`, `lock_missed`, `no_change`, `rollout_waiting`, `insufficient_data`, `rollback_cooling_down`, `rollout_cooling_down`, `dry_run`
- 정상 mutation: `proposal_applied`, `rollout_expanded`, `rolled_back`
- 실패: `apply_blocked`, `no_active_rollout`, `no_candidate_or_no_baseline`, `projection_not_ready`, `metrics_read_failed`, `failed`

summary 추가 필드:

- `apply_enabled`
- `guardrail_result`
- `attempted_action`
- `applied_action`
- `verification_status`

주의:

- 초기 배포는 dry-run을 기본으로 둘 수 있다.
- closed-loop 전환은 chart 변경이 아니라 env 조합 변경으로 가능해야 한다.
- apply 전환 시에도 `TM_POLICY_OPTIMIZER_APPLY_ENABLED=true` 없이 mutation은 열리지 않는다.

## 8. post-review CronJob

| 항목 | 계약 |
|---|---|
| command | `tm-ai-post-review` |
| 권장 schedule | `*/10 * * * *` |
| 기본 conflict policy | `upsert` |
| concurrencyPolicy | `Forbid` |
| restartPolicy | `Never` |
| backoffLimit | `1` |
| dry-run | `tm-ai-post-review --dry-run` |

기본 window:

- UTC 기준 현재 시각을 10분 단위로 내림한다.
- 직전 10분 window를 사용한다.
- `window_end_ms = floor(now_ms / 600000) * 600000`
- `window_start_ms = window_end_ms - 600000`

기본 `match_id`:

- `post-review-<window_end_utc_yyyymmddhhmm>`
- 같은 window 재실행은 같은 `match_id`로 upsert된다.

필수 env:

- `TM_CLICKHOUSE_URL`
- `TM_PG_URL`

선택 env:

- `TM_OFFLINE_LLM_API_KEY`
- `OPENAI_API_KEY`
- `TM_OFFLINE_LLM_MODEL`
- `TM_OFFLINE_LLM_ENDPOINT`
- `OPENAI_BASE_URL`
- `TM_OFFLINE_LLM_TIMEOUT_MS`
- `TM_CLICKHOUSE_INGEST_TIMEOUT_MS`

LLM key 조건:

- 기본 CronJob command에는 `--require-llm`을 붙이지 않는다.
- `--require-llm`을 붙이는 운영 모드에서만 `TM_OFFLINE_LLM_API_KEY` 또는 `OPENAI_API_KEY`가 필수다.

no_input:

- candidate row 0개면 `status=no_input`
- exit `0`
- PostgreSQL write 없음
- 정상 no-op이다.

summary 해석:

- `success`/`completed`: workflow 완료
- `no_input`: candidate 없음, 정상 no-op
- `failed`: ClickHouse read 실패, PostgreSQL write 실패, `--require-llm` 상태의 LLM key 누락, workflow failure

## 9. 인프라 요청 최소화 원칙

- 새 generic chart 설계는 요청하지 않는다.
- 기존 `ai-etl` 배포 패턴 재사용을 기본안으로 둔다.
- optimizer와 post-review는 기존 CronJob 패턴을 복제하는 쪽을 기본안으로 둔다.
- 새 Secret 종류는 만들지 않는 방향을 우선 검토한다.
- 기존 secret/config key에 필요한 값만 추가하는 방식을 우선 검토한다.
- SQL은 인프라팀이 수동 적용하지 않는다.
- AI 이미지 command가 migration, bootstrap, resync를 책임진다.
- 사람 수동 one-shot Job은 운영 절차가 아니라 장애 대응 fallback으로만 둔다.

## 10. 배포 자동화 직전 점검표

AI팀 사전 확인:

```bash
tm-ai-storage-migrate --dry-run
tm-ai-policy-bootstrap --dry-run
tm-ai-policy-projection-resync --current
TM_POLICY_OPTIMIZER_ENABLED=true TM_POLICY_OPTIMIZER_DRY_RUN=true tm-ai-policy-optimizer
TM_POLICY_OPTIMIZER_ENABLED=true TM_POLICY_OPTIMIZER_DRY_RUN=false TM_POLICY_OPTIMIZER_APPLY_ENABLED=true tm-ai-policy-optimizer
tm-ai-post-review --dry-run
```

확인 항목:

- 모든 command 마지막 stdout 줄이 JSON summary다.
- migrate dry-run은 `status=dry_run`, `target=postgres_ddl`, `output_count=2`다.
- bootstrap dry-run은 PostgreSQL write 없이 seed plan만 낸다.
- resync current는 seed row가 없으면 실패해야 하고, seed row가 있으면 Redis key 3종을 쓴다.
- optimizer dry-run은 mutation 없이 `status=dry_run` 또는 skip status로 종료한다.
- optimizer apply smoke는 staging/real storage에서만 수행하고 `apply_enabled=true`, `attempted_action`, `applied_action`, `verification_status`를 확인한다.
- `TM_POLICY_OPTIMIZER_DRY_RUN=false`인데 `TM_POLICY_OPTIMIZER_APPLY_ENABLED=true`가 없으면 `status=apply_blocked`, exit `1`이어야 한다.
- post-review dry-run은 window와 `match_id`를 자동 생성한다.
- post-review candidate row 0개는 `status=no_input`, exit `0`, PostgreSQL write 없음이다.

## 11. 303에 넘길 항목

지금 넘길 항목:

- 새 AI image tag 반영
- ArgoCD PreSync 3단계 wiring
- `ai-defense` Deployment env 추가
- `tm-ai-policy-optimizer` CronJob 추가
- `tm-ai-post-review` CronJob 추가

인프라 구현 요청:

- PreSync 3개 Job을 ArgoCD sync 안에 숨긴다.
- 사람이 수동 one-shot Job을 치는 배포 절차로 만들지 않는다.
- PreSync 실패 시 Deployment/CronJob rollout이 멈추게 한다.
- 기존 `ai-etl` chart/pattern 복제를 우선 검토한다.
- Secret은 기존 secret/config에 key 추가가 가능한지 먼저 검토한다.

## 12. 아직 넘기지 않을 항목

아직 넘기지 않을 항목:

- Discord sender
- Discord Secret
- notification retry/idempotency
- generic chart 설계
- Discord payload builder
- Discord webhook sender

이유:

- Discord sender는 아직 runnable contract가 닫히지 않았다.
- notification retry/idempotency는 Post-Review 저장 계약과 별도 설계다.
- generic chart는 인프라 설계 공수를 키울 수 있다.
- optimizer auto-apply는 runnable contract가 닫혔고, 실제 운영 활성화는 AI팀 승인 후 env 변경으로 다룬다.

## 13. 인프라팀 전달용 초안

제목:

```text
AI Defense background components ArgoCD PreSync / CronJob wiring 요청
```

본문:

```text
AI Defense 신규 이미지 기준으로 background 운영 command 계약이 201 레포에서 닫혔습니다.
303 Helm/ArgoCD 쪽에서는 수동 one-shot Job이 아니라 ArgoCD sync 시 자동 선행 작업이 실행되도록 반영 부탁드립니다.

요청 배포 순서:
1. PreSync Job: tm-ai-storage-migrate
2. PreSync Job: tm-ai-policy-bootstrap
3. PreSync Job: tm-ai-policy-projection-resync --current
4. ai-defense Deployment rollout
5. tm-ai-policy-optimizer CronJob
6. tm-ai-post-review CronJob

PreSync 실패 시 이후 Deployment/CronJob rollout은 진행하지 않게 해주세요.
PreSync Job은 사람이 수동 실행하는 운영 절차가 아니라 ArgoCD sync 내부 단계로 숨기는 방향이 최종안입니다.

공통 확인:
- 각 command 마지막 stdout 줄은 JSON summary입니다.
- status=failed는 exit 1입니다.
- success/skip/dry_run/no_input/optimizer skip 계열은 exit 0입니다.

PreSync 필수 env:
- tm-ai-storage-migrate: TM_PG_URL
- tm-ai-policy-bootstrap: TM_PG_URL
- tm-ai-policy-projection-resync --current: TM_PG_URL, TM_REDIS_URL

ai-defense Deployment 필수 env:
- TM_ENV
- TM_PG_URL
- TM_REDIS_URL
- TM_ROLLOUT_SALT
- TM_POLICY_ALLOW_LOCAL_FALLBACK=false
- TM_ALLOW_IN_MEMORY_REDIS=false

optimizer CronJob:
- command: tm-ai-policy-optimizer
- schedule 권장: */10 * * * *
- 초기 모드: TM_POLICY_OPTIMIZER_ENABLED=true, TM_POLICY_OPTIMIZER_DRY_RUN=true
- closed-loop 모드: TM_POLICY_OPTIMIZER_ENABLED=true, TM_POLICY_OPTIMIZER_DRY_RUN=false, TM_POLICY_OPTIMIZER_APPLY_ENABLED=true
- DRY_RUN=false인데 APPLY_ENABLED=true가 없으면 status=apply_blocked, exit 1입니다.
- mutation 후 PG/Redis post-check 실패는 status=failed, exit 1입니다.
- concurrencyPolicy: Forbid
- restartPolicy: Never
- backoffLimit: 1

post-review CronJob:
- command: tm-ai-post-review
- schedule 권장: */10 * * * *
- window/match_id는 command가 자동 생성합니다.
- candidate row가 없으면 status=no_input, exit 0, PostgreSQL write 없음이 정상입니다.
- concurrencyPolicy: Forbid
- restartPolicy: Never
- backoffLimit: 1

최소화 원칙:
- 새 generic chart 설계보다 기존 ai-etl CronJob 패턴 복제를 우선 검토해주세요.
- 새 Secret 종류를 만들기보다 기존 secret/config에 필요한 key 추가가 가능한지 먼저 확인해주세요.
- SQL 수동 적용은 요청하지 않습니다. AI image command가 migration/bootstrap/resync를 책임집니다.

이번 범위에서 제외:
- Discord sender / Discord Secret
- notification retry/idempotency
- generic chart 설계
```
