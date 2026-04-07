# PostgreSQL Policy Control-Plane Minimum DDL Draft

## 1. 문서 목적

이 문서는 observability 축이 Task 3에서 이미 잠겼다고 가정하고,
정책변경 control-plane용 PostgreSQL 최소 DDL 초안을 고정한다.

이번 문서는 아래 4개만 다룬다.

- `policy_versions`
- `policy_rollout_state`
- `policy_rollout_events`
- `policy_optimization_runs`

이번 문서는 실제 PostgreSQL 연결, migration 적용, Redis projection 구현 문서가 아니다.

---

## 2. 먼저 드러내는 충돌

현재 기준으로 아래 충돌이 있다.

1. `32`는 PostgreSQL control-plane authoritative store를 전제한다.
2. 현재 코드의 실제 runtime authority는 `RedisPolicyStore + FilePolicyStore fallback`이며, PostgreSQL control-plane은 아직 구현되어 있지 않다.
3. `policy_v1.yaml`의 Redis 예시 키는 `tm:policy:*` 계열이지만, 현재 코드와 `32` 문서는 `tm:decision-policy:*` 계열을 사용한다.
4. optimizer 쪽 traceability는 현재 PostgreSQL이 아니라 offline audit event / JSONL 중심이다.

따라서 이번 DDL 초안은
“현재 코드가 이미 쓰는 PostgreSQL schema”가 아니라
“현재 runtime 흐름과 충돌하지 않는 authoritative control-plane 최소 계약”으로 읽어야 한다.

---

## 3. Authoritative Control-Plane vs Redis Projection 책임 분리

### 3.1 PostgreSQL이 맡는 책임

PostgreSQL은 authoritative control-plane으로 아래만 맡는다.

- policy 문서 버전 원본 저장
- validation / activation 상태 저장
- 현재 활성 rollout control state 저장
- rollout / rollback 이력 저장
- offline optimization 실행 메타데이터 저장

즉 PostgreSQL은 history와 operator-facing control state의 권위 저장소다.

### 3.2 Redis가 맡는 책임

Redis는 runtime projection으로 아래만 맡는다.

- active policy document projection
- current rollout state projection
- version lookup / runtime cache

즉 Redis는 request path에서 빠르게 읽기 위한 projection이다.
authoritative history 저장소가 아니다.

### 3.3 runtime read 원칙

- runtime은 PostgreSQL을 직접 읽지 않는다.
- runtime은 Redis projection을 읽는다.
- PostgreSQL -> Redis projection은 다음 task의 범위다.

---

## 4. 최소 DDL 초안

```sql
CREATE TABLE policy_versions (
    policy_version TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL,
    source_type TEXT NOT NULL,
    parent_policy_version TEXT NULL,
    document_json JSONB NOT NULL,
    validation_result_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validated_at TIMESTAMPTZ NULL,
    activated_at TIMESTAMPTZ NULL
);

CREATE TABLE policy_rollout_state (
    rollout_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    base_policy_version TEXT NOT NULL,
    candidate_policy_version TEXT NULL,
    ratio NUMERIC(6,5) NOT NULL,
    evaluation_window_seconds INTEGER NOT NULL,
    canary_duration_seconds INTEGER NOT NULL,
    expand_step_index INTEGER NULL,
    stage_started_at_ms BIGINT NOT NULL,
    updated_at_ms BIGINT NOT NULL,
    current_status TEXT NOT NULL,
    rollback_reason TEXT NULL
);

CREATE TABLE policy_rollout_events (
    event_id TEXT PRIMARY KEY,
    rollout_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    base_policy_version TEXT NOT NULL,
    candidate_policy_version TEXT NULL,
    stage_before TEXT NULL,
    stage_after TEXT NULL,
    ratio_before NUMERIC(6,5) NULL,
    ratio_after NUMERIC(6,5) NULL,
    reason_json JSONB NULL,
    metrics_snapshot_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE policy_optimization_runs (
    run_id TEXT PRIMARY KEY,
    base_policy_version TEXT NOT NULL,
    proposed_policy_version TEXT NULL,
    trigger_type TEXT NOT NULL,
    metrics_snapshot_id TEXT NULL,
    window_start_ms BIGINT NULL,
    window_end_ms BIGINT NULL,
    metrics_snapshot_json JSONB NULL,
    proposal_json JSONB NULL,
    validation_result_json JSONB NULL,
    result_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL
);
```

DDL 메모:

- 이번 초안은 foreign key, unique partial index, single-active-row enforcement까지는 잠그지 않는다.
- `policy_rollout_state`는 “현재 authoritative state row” 계약을 우선하고, 활성 row enforcement는 후속 task로 둔다.
- JSONB는 document / validation / reason / metrics snapshot처럼 shape가 자주 변할 수 있는 control-plane metadata에만 쓴다.

---

## 5. `policy_versions` 최소 컬럼 목록

### 5.1 역할

- policy 문서 버전의 authoritative store
- runtime projection의 source-of-truth

### 5.2 최소 컬럼 표

| column | type | required | 현재 코드 매핑 여부 또는 gap | 메모 |
| --- | --- | --- | --- | --- |
| `policy_version` | `TEXT` | required | yes | `PolicySnapshot.policy_version`, `policy_v1.meta.policyVersion`과 직접 대응 |
| `schema_version` | `TEXT` | required | yes | `snapshot_to_document()`는 `schemaVersion=policy.v1`를 기록함 |
| `status` | `TEXT` | required | partial gap | `32` 권장 상태값 존재. 현재 코드에는 DB status 구현 없음 |
| `source_type` | `TEXT` | required | partial gap | `MANUAL/RULE_BASED/OFFLINE_LLM/HOTFIX` 방향만 존재 |
| `parent_policy_version` | `TEXT` | nullable | partial gap | optimizer canary/patch 흐름에서 logical parent 개념 존재 |
| `document_json` | `JSONB` | required | yes | current code `snapshot_to_document()` 구조 저장 가능 |
| `validation_result_json` | `JSONB` | nullable | partial gap | validator 결과는 current optimizer에 있으나 DB persistence는 없음 |
| `created_at` | `TIMESTAMPTZ` | required | gap | current Redis/file store에는 created timestamp persistence 없음 |
| `validated_at` | `TIMESTAMPTZ` | nullable | gap | current code에 persistence 없음 |
| `activated_at` | `TIMESTAMPTZ` | nullable | gap | current code에 persistence 없음 |

### 5.3 이번 task에서 넣지 않는 항목

- `patch_summary_json`
- `created_by`

제외 이유:

- `32`에는 권장되지만 runtime projection과 다음 task 입력에 필수는 아니다.
- 현재 코드가 직접 생산하지 않는다.
- 이번 task는 operator audit 완성보다 control-plane 최소 계약 잠금이 우선이다.

---

## 6. `policy_rollout_state` 최소 컬럼 목록

### 6.1 역할

- 현재 활성 rollout control state의 authoritative row
- Redis runtime projection의 source-of-control

### 6.2 최소 컬럼 표

| column | type | required | 현재 코드 매핑 여부 또는 gap | 메모 |
| --- | --- | --- | --- | --- |
| `rollout_id` | `TEXT` | required | gap | current code rollout state dict에는 없음. DB authoritative row 식별자로 새로 필요 |
| `stage` | `TEXT` | required | yes | `policy_v1.rollout_state.schema.stage`, `RolloutState.stage`와 대응 |
| `base_policy_version` | `TEXT` | required | yes | current rollout state dict / `RolloutState`에 존재 |
| `candidate_policy_version` | `TEXT` | nullable | yes | current rollout state dict / `RolloutState`에 존재 |
| `ratio` | `NUMERIC(6,5)` | required | yes | current rollout state dict / `resolve_policy_version()`에 존재 |
| `evaluation_window_seconds` | `INTEGER` | required | partial yes | `RolloutState`에 존재, bootstrap default에는 없음 |
| `canary_duration_seconds` | `INTEGER` | required | partial yes | `RolloutState`에 존재, bootstrap default에는 없음 |
| `expand_step_index` | `INTEGER` | nullable | yes | `RolloutState.expand_step_index`에 존재 |
| `stage_started_at_ms` | `BIGINT` | required | partial yes | `RolloutState.stage_started_at_ms`에 존재, bootstrap default에는 없음 |
| `updated_at_ms` | `BIGINT` | required | yes | current rollout state dict required field |
| `current_status` | `TEXT` | required | gap | `32` operator-facing field. current code는 `stage`만 쓰고 별도 status는 없음 |
| `rollback_reason` | `TEXT` | nullable | partial yes | rollback/guardrail 흐름에는 reason이 있으나 current rollout state dict에는 안정 저장 안 됨 |

### 6.3 current-state row 메모

이번 최소 계약에서는 `policy_rollout_state`를
"현재 authoritative control state row"로 읽는다.

즉:

- history는 `policy_rollout_events`가 맡는다.
- runtime projection은 이 row를 Redis로 복사해 사용한다.

---

## 7. `policy_rollout_events` 최소 컬럼 목록

### 7.1 역할

- rollout / rollback / 확장 / 취소 이력의 append-only 로그

### 7.2 최소 컬럼 표

| column | type | required | 현재 코드 매핑 여부 또는 gap | 메모 |
| --- | --- | --- | --- | --- |
| `event_id` | `TEXT` | required | gap | current code에 별도 persistent event id 없음 |
| `rollout_id` | `TEXT` | required | gap | current code rollout state에는 rollout id 없음 |
| `event_type` | `TEXT` | required | partial yes | optimizer pipeline의 `OFFLINE_OPT_CANARY_STARTED`, `OFFLINE_OPT_ROLLOUT_EXPANDED`, `OFFLINE_OPT_ROLLBACK_TRIGGERED` 등과 대응 가능 |
| `base_policy_version` | `TEXT` | required | yes | optimizer pipeline audit payload에 존재 |
| `candidate_policy_version` | `TEXT` | nullable | yes | optimizer pipeline `new_policy_version` 또는 rollout state에서 대응 가능 |
| `stage_before` | `TEXT` | nullable | partial gap | current code는 audit event마다 별도 persistence 안 함 |
| `stage_after` | `TEXT` | nullable | partial yes | rollout state payload로 유도 가능 |
| `ratio_before` | `NUMERIC(6,5)` | nullable | gap | 현재 audit event에 직접 persistence 없음 |
| `ratio_after` | `NUMERIC(6,5)` | nullable | partial yes | rollout state payload로 유도 가능 |
| `reason_json` | `JSONB` | nullable | partial yes | rollback_reason / validation reason / guardrail reasons 보존 용도 |
| `metrics_snapshot_json` | `JSONB` | nullable | partial yes | optimizer pipeline 및 SSOT metrics snapshot 개념과 대응 |
| `created_at` | `TIMESTAMPTZ` | required | gap | current code는 JSONL ts 위주, DB timestamp persistence 없음 |

### 7.3 이번 task에서 넣지 않는 항목

- `created_by`

제외 이유:

- operator provenance로는 유용하지만, runtime projection과 다음 task 입력에 필수는 아니다.
- current code에서 직접 생산하지 않는다.

---

## 8. `policy_optimization_runs` 최소 컬럼 목록

### 8.1 역할

- offline optimization 실행 단위 메타데이터 저장
- proposal / validation / canary 시작 여부를 실행 단위로 재구성

### 8.2 최소 컬럼 표

| column | type | required | 현재 코드 매핑 여부 또는 gap | 메모 |
| --- | --- | --- | --- | --- |
| `run_id` | `TEXT` | required | gap | current optimizer pipeline은 별도 DB run id 없음 |
| `base_policy_version` | `TEXT` | required | yes | optimizer pipeline audit payload에 존재 |
| `proposed_policy_version` | `TEXT` | nullable | partial yes | `new_policy_version` / candidate version과 대응 가능 |
| `trigger_type` | `TEXT` | required | gap | SSOT에는 log-count based trigger가 있으나 DB persistence는 아직 없음 |
| `metrics_snapshot_id` | `TEXT` | nullable | yes | optimizer pipeline에서 직접 생성 |
| `window_start_ms` | `BIGINT` | nullable | partial yes | metrics snapshot에 들어갈 수 있음 |
| `window_end_ms` | `BIGINT` | nullable | partial yes | metrics snapshot에 들어갈 수 있음 |
| `metrics_snapshot_json` | `JSONB` | nullable | yes | optimizer pipeline / SSOT와 직접 대응 |
| `proposal_json` | `JSONB` | nullable | yes | proposal / patches payload 저장 가능 |
| `validation_result_json` | `JSONB` | nullable | partial yes | validator errors / sanitized proposal 결과 저장 가능 |
| `result_status` | `TEXT` | required | yes | SSOT `APPLIED/REJECTED/ROLLED_BACK/NO_CHANGE`, pipeline result와 대응 |
| `created_at` | `TIMESTAMPTZ` | required | gap | current code는 JSONL ts만 있음 |
| `finished_at` | `TIMESTAMPTZ` | nullable | gap | current code는 DB persistence 없음 |

### 8.3 이번 task에서 넣지 않는 항목

- `summary_report_id`

제외 이유:

- current pipeline에는 존재하지만 control-plane 최소 DDL과 Redis projection 경계에는 필수가 아니다.
- 후속 operator UX / audit refinement에서 추가해도 된다.

---

## 9. 현재 코드와의 gap 메모

### 9.1 구현 공백

- PostgreSQL control-plane 4테이블은 현재 코드에 구현되어 있지 않다.
- current runtime은 `RedisPolicyStore`와 `FilePolicyStore`를 사용한다.
- current optimizer traceability도 PostgreSQL이 아니라 JSONL audit event 기반이다.

### 9.2 naming gap

- `policy_v1.yaml`는 Redis 예시로 `tm:policy:*`를 제시한다.
- current code와 `32`는 `tm:decision-policy:*`를 사용한다.
- 이번 문서는 current code와 `32`를 우선 기준으로 본다.

### 9.3 rollout-state shape gap

- bootstrap rollout state는 `stage`, `base_policy_version`, `candidate_policy_version`, `ratio`, `updated_at_ms`까지만 바로 채운다.
- `evaluation_window_seconds`, `canary_duration_seconds`, `stage_started_at_ms`, `current_status` 같은 operator-facing 필드는 DB authoritative row에서 더 분명히 잠가야 한다.

### 9.4 event/run identity gap

- current optimizer pipeline에는 DB용 `run_id`, `rollout_id`, `event_id`가 없다.
- 이번 DDL 초안은 PostgreSQL persistence를 위해 이 식별자를 새로 요구한다.

---

## 10. Redis Runtime Projection 메모

다음 task의 입력 기준으로,
Redis projection은 최소 아래만 필요하다.

- policy document by version
- current rollout state
- version index

현재 코드 기준 관련 키는 아래다.

- `tm:decision-policy:version:{policyVersion}`
- `tm:decision-policy:rollout-state`
- `tm:decision-policy:version-index`

Projection 규칙:

- PostgreSQL `policy_versions`에서 active/candidate 문서를 읽어 Redis version key로 projection
- PostgreSQL `policy_rollout_state`의 현재 authoritative row를 Redis rollout-state key로 projection
- Runtime은 Redis만 읽고 deterministic assignment를 수행

---

## 11. Task 5에 바로 넘길 입력

Task 5가 PostgreSQL -> Redis projection 계약을 정의할 때 바로 사용할 입력은 아래다.

1. authoritative source
   - policy document source: `policy_versions`
   - current rollout source: `policy_rollout_state`
   - history source: `policy_rollout_events`
   - optimizer run metadata: `policy_optimization_runs`
2. Redis projection target
   - `tm:decision-policy:version:{policyVersion}`
   - `tm:decision-policy:rollout-state`
   - `tm:decision-policy:version-index`
3. runtime read rule
   - runtime은 PostgreSQL을 직접 읽지 않는다.
   - runtime은 Redis projection만 읽는다.
4. explicit gap
   - `tm:policy:*` vs `tm:decision-policy:*` naming mismatch
   - DB `run_id` / `rollout_id` / `event_id` 신규 도입 필요
   - bootstrap rollout state와 DB authoritative state shape 차이

---

## 12. 검증 메모

수동 검토 기준은 아래였다.

- `32-storage-architecture.md`
  - PostgreSQL authoritative control-plane과 Redis runtime projection 분리 원칙을 유지했다.
- `policy_v1.yaml`
  - rollout state schema, assignment contract, policyVersion 기록 원칙과 크게 모순되지 않게 최소 필드를 골랐다.
- `defense_policy_optimization_ssot.yaml`
  - offline optimization traceability, metrics snapshot, result status 개념과 맞춘다.
- `runtime.py`, `loader.py`, `keyspace.py`, `rollout.py`
  - current runtime authority가 Redis-first라는 점, file fallback이 bootstrap/local dev라는 점, rollout state minimum required field를 확인했다.

테스트 메모:

- policy control-plane PostgreSQL schema를 직접 잠그는 관련 테스트 파일은 찾지 못했다.
- 이번 task에서는 새 테스트를 추가하지 않았다.
