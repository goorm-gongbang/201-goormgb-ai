# PostgreSQL to Redis Projection Minimum Contract

## 1. 문서 목적

이 문서는 Task 4에서 잠근 PostgreSQL policy control-plane 최소 DDL을 입력으로 받아,
PostgreSQL authoritative control-plane 상태를 Redis runtime authority로 투영하는 최소 projection 계약을 고정한다.

이번 문서는 아래만 다룬다.

- projection 대상 Redis keyspace
- 각 key의 최소 payload 구조
- PostgreSQL authoritative source와 Redis projection source 관계
- projection 갱신 트리거와 반영 단위
- projection failure handling 최소 규칙
- runtime read path와 projection worker 책임 분리

이번 문서는 실제 PostgreSQL query, Redis write, background worker 구현 문서가 아니다.

---

## 2. 먼저 드러내는 충돌

현재 기준으로 아래 충돌이 있다.

1. `32`는 `PostgreSQL(control plane) -> Redis(runtime projection)`을 전제한다.
2. 현재 코드에는 PostgreSQL control-plane reader/writer도, projection worker도 없다.
3. `policy_v1.yaml`는 Redis 예시 키로 `tm:policy:*`와 `tm:policy:current_version`를 제시하지만, 현재 코드와 `32`는 `tm:decision-policy:*`를 사용하고 `current_version` 키도 읽지 않는다.
4. 현재 runtime bootstrap은 PostgreSQL이 아니라 `RedisPolicyStore + FilePolicyStore fallback`으로 Redis를 직접 채운다.

따라서 이번 문서는
"현재 구현된 projection worker 계약"이 아니라
"현재 runtime read path와 충돌하지 않도록 먼저 잠그는 projection 최소 계약"으로 읽어야 한다.

---

## 3. Authority와 책임 분리

### 3.1 PostgreSQL이 authoritative source인 것

PostgreSQL은 아래의 권위 저장소다.

- 어떤 policy document version이 존재하는가
- 어떤 rollout state가 현재 authoritative current state인가
- rollout / rollback 이력이 무엇인가
- optimization run 메타가 무엇인가

즉 policy 문서 lifecycle과 rollout control state의 source-of-truth는 PostgreSQL이다.

### 3.2 Redis가 projection으로만 맡는 것

Redis는 request path에서 즉시 읽어야 하는 최소 정보만 맡는다.

- version별 runtime-readable policy document
- current rollout state
- projected version inventory

즉 Redis는 runtime authority이지만 authoritative history 저장소는 아니다.

### 3.3 runtime read 원칙

- runtime request path는 PostgreSQL을 직접 읽지 않는다.
- runtime request path는 Redis projection만 읽는다.
- projection worker만 PostgreSQL을 읽고 Redis를 쓴다.

---

## 4. Projection 대상 Redis Key 목록

이번 task에서 고정하는 projection 대상 key는 아래 3개뿐이다.

| Redis key | 역할 | PostgreSQL source | runtime 직접 사용 여부 | 메모 |
| --- | --- | --- | --- | --- |
| `tm:decision-policy:version:{policyVersion}` | version별 policy document projection | `policy_versions.document_json` | yes | runtime이 최종 `PolicySnapshot` 로딩에 직접 사용 |
| `tm:decision-policy:rollout-state` | current rollout state projection | `policy_rollout_state` 현재 authoritative row | yes | sessionId 기반 deterministic assignment에 직접 사용 |
| `tm:decision-policy:version-index` | projected version inventory | `policy_versions` + `policy_rollout_state`에서 파생 | no | runtime critical path authority가 아니라 inventory/helper key |

이번 task에서 넣지 않는 key:

- `tm:policy:*`
- `tm:policy:current_version`
- `policy_rollout_events` projection key
- `policy_optimization_runs` projection key

제외 이유:

- 현재 코드 keyspace와 맞지 않거나
- runtime request path가 직접 읽지 않거나
- control-plane 메타데이터를 Redis에 과도하게 복제하게 되기 때문이다.

---

## 5. 각 Key의 최소 Payload 구조

### 5.1 `tm:decision-policy:version:{policyVersion}`

최소 payload 구조:

```json
{
  "schemaVersion": "policy.v1",
  "parameters": {
    "...": "runtime policy parameters"
  },
  "flags": {
    "...": "runtime feature flags"
  }
}
```

필수 원칙:

- payload는 `policy_versions.document_json`에서 projection한다.
- runtime이 즉시 읽는 policy 문서 shape만 남긴다.
- `status`, `source_type`, `validation_result_json`, `created_at` 같은 control-plane 메타는 Redis에 복제하지 않는다.
- `policyVersion`은 key name으로 이미 식별되므로 payload에 중복 강제하지 않는다.

현재 코드 정합성 메모:

- `PolicyLoader.load()`는 key에서 version을 알고 `fetch_policy_by_version(version)` 결과를 `_build_snapshot_from_dict(raw, version)`에 넘긴다.
- 따라서 Redis payload는 `schemaVersion + parameters + flags`면 현재 기준 충분하다.

### 5.2 `tm:decision-policy:rollout-state`

최소 payload 구조:

```json
{
  "stage": "FULL",
  "base_policy_version": "v2.0.0-mvp",
  "candidate_policy_version": null,
  "ratio": 0.0,
  "updated_at_ms": 0
}
```

필수 원칙:

- payload는 `policy_rollout_state`의 current authoritative row에서 projection한다.
- runtime assignment에 직접 필요한 최소 필드만 남긴다.
- `evaluation_window_seconds`, `canary_duration_seconds`, `expand_step_index`, `stage_started_at_ms`, `current_status`, `rollback_reason`는 PostgreSQL authoritative row에는 남기되 Redis minimum payload에는 강제하지 않는다.

현재 코드 정합성 메모:

- `resolve_policy_version()`은 실제로 `stage`, `base_policy_version`, `candidate_policy_version`, `ratio`만 읽는다.
- 현재 bootstrap/default도 `updated_at_ms`를 포함하므로 projection minimum에는 `updated_at_ms`를 유지한다.

### 5.3 `tm:decision-policy:version-index`

최소 payload 구조:

```json
[
  "v2.0.0-mvp",
  "v2.0.1-canary"
]
```

필수 원칙:

- payload는 projected Redis version doc key들의 inventory다.
- runtime selection authority가 아니라 projection inventory/helper key다.
- 최소 집합은 current rollout state가 참조하는 `base_policy_version`, `candidate_policy_version`과 Redis에 실제로 projection된 version key들이다.
- control-plane 전체 catalog를 Redis에 복제하는 용도로 확장하지 않는다.

현재 코드 정합성 메모:

- `RedisPolicyStore`는 JSON array를 기대한다.
- current code는 `current_version` key를 읽지 않으므로 `version-index`가 있어도 runtime current selection authority는 되지 않는다.

---

## 6. PostgreSQL Authoritative Source와 Redis Projection Source 관계

### 6.1 source mapping

| Redis key | authoritative source table | authoritative source field or rule | projection 여부 |
| --- | --- | --- | --- |
| `tm:decision-policy:version:{policyVersion}` | `policy_versions` | `document_json` by `policy_version` | yes |
| `tm:decision-policy:rollout-state` | `policy_rollout_state` | current authoritative row | yes |
| `tm:decision-policy:version-index` | derived | projected `policy_version` set + current rollout references | yes |
| none | `policy_rollout_events` | rollout history / retry audit | no direct projection |
| none | `policy_optimization_runs` | optimizer run metadata | no direct projection |

### 6.2 source-of-current-policy 원칙

현재 어떤 policy가 선택되는지는
`policy_versions.status` 단독이 아니라
`policy_rollout_state`가 결정한다.

즉:

- `policy_versions`는 version document authority다.
- `policy_rollout_state`는 current selection authority다.
- Redis는 이 둘의 runtime-readable projection이다.

### 6.3 projection 범위 경계

Redis에 복제하지 않는 것:

- rollout / rollback append-only history
- validation 상세 결과
- optimization metrics snapshot 전체 메타
- operator provenance
- 사람이 읽는 control-plane 감사 메타데이터

이 정보는 PostgreSQL에 남아야 한다.

---

## 7. Projection 갱신 트리거와 반영 규칙

### 7.1 갱신 트리거

최소 projection trigger는 아래 4개다.

1. `policy_versions`에 runtime에서 읽어야 하는 새 version document가 준비되었을 때
2. `policy_rollout_state` current authoritative row가 변경되었을 때
3. rollback / full promotion처럼 current state가 base/candidate 참조를 바꿀 때
4. Redis eviction / 누락 / 손상 이후 재동기화(reconcile)가 필요할 때

### 7.2 반영 단위

반영 단위는 "runtime이 한 번의 assignment에서 참조하는 key 집합"이다.

최소 집합:

- referenced base version document
- referenced candidate version document if present
- current rollout state
- version index

### 7.3 반영 순서

현재 기준 안전한 apply 순서는 아래다.

1. PostgreSQL authoritative write가 먼저 성공한다.
2. `policy_rollout_state`가 참조할 `base_policy_version` / `candidate_policy_version` 문서를 Redis version key에 먼저 projection한다.
3. `tm:decision-policy:rollout-state`를 갱신한다.
4. `tm:decision-policy:version-index`를 마지막에 갱신한다.

이 순서를 쓰는 이유:

- rollout state가 먼저 바뀌면 runtime이 candidate/base를 선택했는데 해당 version doc key가 없을 수 있다.
- `version-index`는 runtime critical path key가 아니므로 마지막 반영이 더 안전하다.

### 7.4 event table과 run table의 역할

- `policy_rollout_events`와 `policy_optimization_runs`는 Redis projection source가 아니다.
- 다만 projection worker 재시도, partial apply 추적, 운영 디버깅의 근거로는 쓸 수 있다.

---

## 8. Projection 실패 시 동작 규칙

### 8.1 PostgreSQL write 실패

- authoritative source write가 실패하면 Redis projection은 시도하지 않는다.
- runtime은 기존 Redis 마지막 정상 projection을 계속 읽는다.

### 8.2 Redis projection 실패

- PostgreSQL authoritative source는 이미 성공했으므로 truth는 PostgreSQL에 남아 있다.
- runtime은 stale Redis state를 읽을 수 있다.
- 이 상태는 "projection partial apply"로 간주한다.
- projection worker는 재시도 또는 reconcile job으로 Redis를 다시 맞춰야 한다.
- 관련 rollout / projection failure 사실은 운영 이벤트 또는 로그로 남겨야 한다.

### 8.3 Redis eviction / key 누락 / 손상

- runtime은 PostgreSQL direct read로 복구하지 않는다.
- projection worker가 PostgreSQL authoritative source에서 Redis key를 재구성해야 한다.
- `tm:decision-policy:rollout-state`가 비었거나 손상되면 runtime은 current code 기준 baseline default policy로 fail-safe fallback할 수 있다.
- 다만 prod 계약상 정상 복구 경로는 "baseline bootstrap"이 아니라 "PostgreSQL -> Redis 재투영"이다.

### 8.4 rollback 운영 규칙

- rollback은 PostgreSQL `policy_rollout_state` update 성공 후 Redis rollout-state projection update 순서로 반영한다.
- rollback 시 candidate 제거가 반영되지 않은 상태를 오래 방치하면 안 된다.

---

## 9. Runtime Read Path와 Projection Worker 책임 분리

### 9.1 runtime request path

runtime request path는 아래만 한다.

- `tm:decision-policy:rollout-state` 읽기
- `tm:decision-policy:version:{policyVersion}` 읽기
- sessionId 기반 deterministic assignment
- parse 실패 시 default baseline fallback

runtime request path가 하지 않는 것:

- PostgreSQL direct read
- control-plane row 조합
- projection repair
- rollout history 조회

### 9.2 projection worker

projection worker는 아래만 한다.

- PostgreSQL control-plane row 읽기
- Redis key 3종 projection 쓰기
- projection ordering 보장
- projection retry / reconcile 수행

projection worker가 하지 않는 것:

- runtime assignment 결정
- ClickHouse 효과 측정
- optimization proposal 생성

---

## 10. 현재 코드와의 Gap 메모

### 10.1 구현 공백

- PostgreSQL control-plane을 읽어 Redis에 projection하는 worker가 없다.
- PostgreSQL repository / query layer도 없다.
- projection failure를 partial apply로 기록하는 흐름도 없다.

### 10.2 key naming gap

- `policy_v1.yaml`는 `tm:policy:*`와 `tm:policy:current_version`를 예시로 든다.
- current code와 `32`는 `tm:decision-policy:*`만 사용한다.
- 이번 문서는 current code + `32`를 우선 기준으로 삼아 `current_version` 키를 도입하지 않는다.

### 10.3 bootstrap gap

- 현재 runtime bootstrap은 PostgreSQL authoritative source 없이 Redis를 baseline/default policy로 채운다.
- 이 동작은 local dev/bootstrap에는 유용하지만 prod projection contract와는 다르다.

### 10.4 rollout-state shape gap

- PostgreSQL authoritative row는 `evaluation_window_seconds`, `canary_duration_seconds`, `current_status` 등 더 많은 필드를 가진다.
- current runtime read path는 `stage`, `base_policy_version`, `candidate_policy_version`, `ratio`, `updated_at_ms`만 사실상 사용한다.
- 따라서 Redis projection은 current-safe minimum payload만 잠그고, 나머지는 PostgreSQL에 남긴다.

---

## 11. Task 6에 바로 넘길 입력

Task 6이 env / failure handling / test plan을 정리할 때 바로 사용할 입력은 아래다.

1. authoritative source
   - `policy_versions.document_json`
   - `policy_rollout_state` current authoritative row
   - `policy_rollout_events`, `policy_optimization_runs`는 direct projection source가 아니라 audit/reconcile 근거
2. Redis target keys
   - `tm:decision-policy:version:{policyVersion}`
   - `tm:decision-policy:rollout-state`
   - `tm:decision-policy:version-index`
3. minimum payload
   - version doc: `schemaVersion + parameters + flags`
   - rollout state: `stage + base_policy_version + candidate_policy_version + ratio + updated_at_ms`
   - version index: projected version string array
4. apply ordering
   - PostgreSQL commit 성공
   - referenced version doc keys write
   - rollout-state write
   - version-index write
5. failure cases to cover
   - PostgreSQL write fail -> no projection
   - Redis projection fail after PostgreSQL success -> stale read + retry/reconcile
   - Redis eviction -> PostgreSQL source 기반 재투영
   - runtime direct PostgreSQL read 금지 유지
6. explicit gap
   - `tm:policy:*` vs `tm:decision-policy:*`
   - `current_version` key 미사용
   - bootstrap baseline write와 prod projection contract 차이

---

## 12. 검증 메모

수동 검토 기준은 아래였다.

- `32-storage-architecture.md`
  - `PostgreSQL(control plane) -> Redis(runtime projection) -> ClickHouse(effect measurement)` 원칙과 request path direct PostgreSQL 금지 원칙을 유지했다.
- `07-policy-control-plane-minimum-ddl.md`
  - Task 4의 authoritative table 구분과 projection source 관계가 일관되도록 맞췄다.
- `policy_v1.yaml`
  - rollout state 기본 schema와 runtime authority/fallback 의미를 대조했다.
- `defense_policy_optimization_ssot.yaml`
  - optimizer run / rollout history는 Redis direct projection 대상이 아니라는 경계를 유지했다.
- `runtime.py`, `loader.py`, `keyspace.py`, `rollout.py`
  - current code가 실제로 읽는 Redis key와 최소 rollout payload shape를 확인했다.

테스트 메모:

- PostgreSQL -> Redis projection 계약을 직접 잠그는 관련 테스트 파일은 찾지 못했다.
- 이번 task에서는 새 테스트를 추가하지 않았다.
