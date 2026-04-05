# 31/32 문서와 현재 코드의 차이 설명

## 1. 문서 목적

이 문서는 아래 3가지를 한 번에 비교해서 설명한다.

- `31-observability-merge-strategy.md`
- 제안된 `32-storage-architecture` 초안
- 현재 저장소에 들어 있는 실제 코드

목적은 간단하다.

- 무엇이 이미 코드와 맞는 이야기인지 정리하고
- 무엇이 아직 구현되지 않은 목표 설계인지 구분하고
- 앞으로 문서에 어떤 표현을 써야 혼동이 적은지 정리하는 것이다.

이 문서는 노션 공유용 설명 문서다.  
즉, 구현 명세서라기보다 팀이 같은 그림을 보게 만드는 해설 문서에 가깝다.

관련 문서:

- `31-observability-merge-strategy.md`
- `src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_observability_ssot.yaml`
- `src/traffic_master_ai/defense/api/audit.py`
- `src/traffic_master_ai/defense/api/main.py`
- `src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py`
- `src/traffic_master_ai/defense/api/etl_worker.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/sql/001_post_review_tables.sql`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`

---

## 2. 한 줄 요약

현재 코드는 아직 `MVP/과도기 구조`다.  
`31` 문서는 이 과도기 구조 위에서 observability와 post-review 결과를 어떻게 함께 소비할지 정리한 문서다.  
반면 `32` 초안은 우리가 앞으로 가고 싶은 `Prod 목표 아키텍처`를 먼저 그려놓은 문서다.

즉 셋의 관계는 아래처럼 보는 것이 가장 정확하다.

- 현재 코드: 지금 실제로 돌아가는 형태
- 31번 문서: 지금 구조를 어떻게 해석하고 외부 소비 구조로 묶을지에 대한 운영 문서
- 32번 문서: 앞으로 storage를 어떻게 고정할지에 대한 목표 문서

중요한 점은 `31`은 현재 코드와 대체로 호환되지만, `32`는 아직 코드보다 한 단계 앞서 있다는 것이다.

---

## 3. 세 가지를 각각 어떻게 읽어야 하나

## 3.1 현재 코드

현재 코드는 크게 보면 아래 구조다.

- 런타임 상태는 `Redis 우선 + 일부 메모리 fallback`
- canonical audit는 `JSONL 파일`
- near-real-time warehouse는 아직 `로컬 JSONL MVP`
- S3 업로드는 audit log archive 용으로 존재
- ETL worker는 `S3 -> PostgreSQL defense_audit_events` 초안이 존재
- post-review 최종 결과 저장은 `PostgreSQL 2테이블`이 이미 구현되어 있음

즉 현재 코드는 아직 `ClickHouse 중심 Prod 구조`가 아니다.

## 3.2 31번 문서

`31-observability-merge-strategy.md`는 저장소를 새로 정의하는 문서라기보다,
이미 있는 observability 개념과 backoffice 결과를 어떻게 함께 읽을지 정리한 문서다.

핵심 메시지는 이렇다.

- Runtime 관측은 `defense_audit_events`를 본다.
- 사후판단 결과는 `post_review_runs`, `post_review_session_results`를 본다.
- Grafana, Discord, 운영 배치는 이 둘을 역할에 맞게 나눠 읽는다.
- 둘의 기본 병합 기준은 `session_id + 시간 구간`이다.

즉 `31`은 저장소 자체보다 `데이터 소비 방식`을 정의하는 문서다.

## 3.3 32번 문서

제안된 `32` 초안은 소비 전략 문서가 아니라 storage architecture 문서다.

핵심 메시지는 이렇다.

- Redis는 실시간 상태만 맡는다.
- S3는 archive만 맡는다.
- ClickHouse는 observability warehouse를 맡는다.
- PostgreSQL은 backoffice 최종 결과를 맡는다.
- ClickHouse 내부도 raw / session rollup / match rollup / candidate view로 나눈다.

즉 `32`는 `Production에서 저장소를 어떻게 고정할지`를 선언하는 문서다.

---

## 4. 가장 중요한 차이: 31은 소비 전략, 32는 저장소 목표 설계

이 둘은 서로 충돌하는 문서가 아니라 초점이 다르다.

### 31번 문서가 답하는 질문

- Grafana는 어디를 읽어야 하나
- Discord는 무엇을 기준으로 알림을 보내야 하나
- Runtime 관측과 post-review 결과를 어떻게 합쳐서 봐야 하나
- 어떤 문서는 유지하고 어떤 문서는 약화해야 하나

### 32번 문서가 답하는 질문

- Redis/S3/ClickHouse/PostgreSQL의 책임은 어디까지인가
- ClickHouse에 어떤 테이블 계층을 둘 것인가
- raw fact, rollup, candidate selection을 어떻게 나눌 것인가
- Production에서 어떤 저장소를 authoritative하게 볼 것인가

즉 `31`은 “어떻게 함께 쓸 것인가”에 가깝고,  
`32`는 “어디에 무엇을 저장할 것인가”에 가깝다.

---

## 5. 항목별 비교

아래 표가 팀이 가장 많이 헷갈릴 부분을 정리한 핵심 비교다.

| 주제 | 현재 코드 | 31번 문서 | 32번 문서 | 해석 |
| --- | --- | --- | --- | --- |
| canonical evidence | `decision_audit` JSONL 파일 | 그대로 유지 | 그대로 유지 | 이 부분은 셋이 거의 맞다 |
| observability warehouse | 로컬 JSONL MVP, 일부 Postgres ETL 초안 | `defense_audit_events`를 소비 기준으로 둠 | ClickHouse 메인 warehouse로 고정 | `31`은 현재/목표를 모두 포용하지만 `32`는 목표 상태를 확정한다 |
| ClickHouse 사용 | 아직 없음 | 직접 고정하지 않음 | 메인 warehouse로 명시 | `32`가 현재 코드보다 앞서 있다 |
| S3 역할 | rotated audit JSONL 업로드 | 외부 소비 문맥에서는 보조적 | archive / backfill source로 명시 | 방향은 맞지만 현재 구현은 audit log archive 중심이다 |
| PostgreSQL 역할 | post-review 결과 2테이블 구현됨 | 결과 소비 기준으로 명확화 | 최종 결과 저장소로 고정 | 이 부분은 셋이 잘 맞는다 |
| raw telemetry 저장 | 일반 telemetry raw는 durable 저장 안 함 | 직접 다루지 않음 | raw observability fact 확장을 전제 | 현재 코드와 `32` 사이 차이가 큼 |
| session rollup / match rollup | 아직 없음 | 필요 시 조합 조회 관점 | ClickHouse 계층으로 제안 | `32`의 새 설계 요소다 |
| candidate view | 아직 없음 | session_id + 시간 구간 조합 규칙 제시 | `defense_post_review_candidates_v1` 제안 | `32`가 더 구체적이다 |
| 조인 기준 | 현실적으로 `session_id + 시간 구간`이 제일 안전 | 그 기준을 문서화함 | 향후 `match_id`, trace, policy version 강화 가능 | 현재 시점에서는 `31` 쪽 표현이 더 현실적이다 |
| 내부 대시보드 | 없음 | 직접 만들지 않는 방향 | 외부 소비 구조 전제 | 이 부분은 셋의 방향이 대체로 맞다 |

---

## 6. 현재 코드와 31번 문서의 차이

`31`은 현재 코드와 꽤 잘 맞는다.  
다만 완전히 일치한다고 보기는 어렵고, 아래 같은 차이가 있다.

### 6.1 `defense_audit_events`는 문서에서는 중심이지만, 코드에서는 아직 과도기다

문서에서는 `defense_audit_events`를 Runtime 관측의 기본 테이블처럼 말한다.  
하지만 현재 코드에서 실제 구현은 아래 수준이다.

- `d0_mvp/observability/warehouse.py`는 `jsonl_mvp` 백엔드다.
- 메타데이터도 `backend: jsonl_mvp`를 반환한다.
- 즉 지금은 warehouse 개념은 있지만, 실제 운영 DB 테이블로 고정된 상태는 아니다.

쉽게 말하면:

- `31` 문서는 warehouse를 “이미 외부 소비 가능한 공통 소스”처럼 설명한다.
- 현재 코드는 warehouse가 아직 “로컬 JSONL MVP” 단계다.

### 6.2 `31`은 외부 소비 구조를 먼저 정리했고, 코드는 아직 그만큼 풍부한 테이블 계층이 없다

`31` 문서는 Grafana, Discord, batch가 어떻게 읽을지 분명히 말한다.  
하지만 현재 코드는 그 소비자를 위한 read model이 충분히 준비된 상태는 아니다.

예를 들면:

- Grafana가 바로 붙을 만한 ClickHouse rollup table이 없음
- Discord 알림에 필요한 runtime 보강 필드를 뽑는 전용 view가 없음
- join 규칙은 문서에 있지만, 조인을 편하게 해주는 DB 계층은 없음

즉 `31`은 운영 문서로는 맞지만, 구현 보조 구조는 아직 부족하다.

### 6.3 `31`의 조인 기준은 현재 코드 현실을 잘 반영한다

오히려 이 부분은 `31`이 현재 코드에 더 잘 맞는다.

현재 audit log는 모든 row에 `match_id`가 정규화된 최상위 컬럼으로 박혀 있는 구조가 아니다.  
그래서 현재는 `session_id + 시간 구간`으로 보는 것이 더 현실적이다.

이 점에서 `31`은 현재 코드 기준으로 충분히 실무적이다.

---

## 7. 현재 코드와 32번 문서의 차이

여기서 차이가 더 크다.  
`32`는 좋은 방향의 문서지만, 현재 코드보다 한 단계 이상 앞선 설계다.

## 7.1 ClickHouse는 아직 코드에 없다

`32`는 ClickHouse를 observability 메인 warehouse로 고정한다.  
하지만 현재 코드에는 ClickHouse 적재나 ClickHouse schema가 없다.

현재 실제 구현은 이렇다.

- local warehouse MVP: JSONL
- S3 archive: 있음
- ETL worker: PostgreSQL 적재 초안

즉 지금 코드에 있는 것은 `ClickHouse 운영 구조`가 아니라  
`JSONL -> S3 -> Postgres 초안 또는 JSONL 로컬 조회`에 더 가깝다.

따라서 `32` 문서를 그대로 현재 상태처럼 쓰면 안 된다.  
`현재는 아직 미구현이며 목표 구조`라고 분명히 써야 한다.

## 7.2 `32`가 제안한 ClickHouse 계층은 아직 존재하지 않는다

`32`는 아래를 제안한다.

- raw fact table
- session rollup table
- match rollup table
- candidate view

하지만 현재 코드에는 이 중 어느 것도 실제 DB object로 구현되어 있지 않다.

즉 이 부분은 `현재 구조 설명`이 아니라 `새 설계안`이다.

## 7.3 현재 audit row는 32가 원하는 만큼 풍부하지 않다

`32`는 raw fact table에 아래 같은 typed column을 기대한다.

- `match_id`
- `requestFeatures`
- `rolloutStage`
- `basePolicyVersion`
- `candidatePolicyVersion`
- `challenge_result`
- `vqa_attempt_score`
- `vqa_terminal`

하지만 현재 `audit.py`의 decision audit payload는 대략 아래 수준이다.

- `ts_ms`
- `session_id`
- `trace_id`
- `request_id`
- `correlation_id`
- `flow_state`
- `event_type`
- `defense_tier`
- `action`
- `reason_code`
- `policy_version`
- `decision_id`
- `risk_score`
- `rule_hits`
- `path`
- `method`
- `allow`
- `runtime_state`
- `telemetry_features`

즉 `32`의 스키마는 충분히 타당하지만,  
현재 audit row가 그 스키마를 바로 채울 준비가 되어 있는 것은 아니다.

## 7.4 일반 raw telemetry는 현재 durable하게 저장되지 않는다

이 부분은 매우 중요하다.

현재 일반 telemetry raw event는:

1. `/ai/telemetry/ingest`로 들어오고
2. 서버가 summary를 계산한 뒤
3. runtime state의 `latest_*_summary`에 저장하고
4. 이후 evaluate 시 그 summary를 `telemetry_features`로 audit에 남긴다

즉 raw event 배열 자체는 durable storage에 남지 않는다.

그래서 `32`가 말하는 `raw observability fact`를 정말 강하게 운영하려면,
현재 코드보다 더 많은 raw evidence 저장 경로가 필요하다.

쉽게 말하면:

- 지금 코드는 `raw -> summary -> audit`
- `32`는 사실상 `raw/summary/result`를 더 많이 남기는 구조

다만 observability SSOT의 privacy 규칙상 `raw mouse trajectory / raw key events`는 audit에 남기지 않는 것이 원칙이므로,
이 확장은 반드시 privacy 규칙과 함께 다시 설계해야 한다.

## 7.5 `match_id` 중심 설계는 32에서 더 강하지만, 현재 코드는 아직 약하다

`32`는 match-centric storage를 강하게 전제한다.

하지만 현재 코드는:

- telemetry summary에는 `matchId`를 넣고
- state key도 `sid:matchId`로 만들고
- challenge payload에는 `matchId`를 넣기도 하지만
- canonical decision audit top-level typed field로 `match_id`를 일관되게 보장하지는 않는다

그래서 현재 기준 기본 join key는 여전히 `session_id + 시간 구간` 쪽이 더 안전하다.

즉 `32`의 match-centric 구조는 맞는 방향이지만,  
현재 audit schema 보강이 먼저 필요하다.

## 7.6 Backoffice input 경로도 아직 32처럼 정리되어 있지 않다

`32`는 Backoffice Copilot이 ClickHouse session rollup 또는 candidate view를 읽는 구조를 전제한다.  
하지만 현재 Backoffice 쪽의 정식 계약은 여전히 아래에 가깝다.

- 결과 저장은 PostgreSQL 2테이블
- 입력은 `DefenseAuditEventRow` 수준의 row 로딩 계약
- 중간 후보/분석 DTO는 메모리 처리

즉 현재는 `ClickHouse 기반 입력 계층`이 아니라  
`row 기반 입력 -> 메모리 DTO -> PostgreSQL 결과 저장` 관점이 더 강하다.

---

## 8. 31과 32를 함께 놓고 보면 무엇이 좋은가

둘을 같이 보면 오히려 역할 분담이 명확해진다.

### 31번 문서의 좋은 점

- 현재 코드와 가까운 해석이 가능하다.
- 외부 소비 구조를 명확히 설명한다.
- `session_id + 시간 구간` 기준이 현재 코드 현실과 잘 맞는다.
- observability와 post-review 결과를 대체가 아니라 보완 관계로 본다.

### 32번 문서의 좋은 점

- 저장소 책임 분리가 매우 선명하다.
- ClickHouse를 제대로 쓰려면 어떻게 계층을 나눠야 하는지 보여준다.
- VQA, candidate selection, rollup 설계를 더 구체적으로 생각하게 만든다.
- Production 아키텍처의 목표 상태를 명확히 잡아준다.

### 같이 쓸 때의 가장 좋은 해석

- `31`은 현재와 가까운 운영/소비 전략 문서로 둔다.
- `32`는 앞으로 구현해야 할 storage target 문서로 둔다.
- 현재 코드는 둘 사이에 있는 과도기 상태라고 설명한다.

이렇게 두면 문서끼리 충돌하지 않는다.

---

## 9. 현재 문서 체계에서 주의할 점

현재 저장소에는 아직 `최소 구현` 전제를 강하게 가진 문서도 남아 있다.

예를 들어 `21-data-contract.md`에는 아래 원칙이 있다.

- ClickHouse는 최소 구현 결과 저장소로 사용하지 않는다.
- S3는 최소 구현 기본 저장소로 사용하지 않는다.

이 문장은 `post-review 최종 결과 저장소`에 대해서는 여전히 맞다.  
즉 PostgreSQL 2테이블을 authoritative store로 쓰는 원칙은 유지된다.

하지만 이 문장을 observability 전체로 넓게 읽으면 혼동이 생긴다.  
왜냐하면 `32`는 ClickHouse를 `결과 저장소`가 아니라 `observability warehouse`로 쓰자는 문서이기 때문이다.

따라서 앞으로 문서에서는 이 구분을 더 분명히 적는 것이 좋다.

- ClickHouse를 쓰지 않는다고 했던 것은 `최소 구현 결과 저장소` 맥락이다.
- ClickHouse를 쓰자는 것은 `observability warehouse` 맥락이다.

즉 서로 완전한 충돌은 아니지만, 문장만 보면 충돌처럼 읽힐 수 있다.

---

## 10. 팀에 이렇게 설명하면 가장 덜 헷갈린다

실무적으로는 아래처럼 설명하는 것이 가장 쉽다.

### 현재 코드

- audit 원본은 JSONL
- warehouse는 아직 JSONL/Postgres 초안
- post-review 결과는 PostgreSQL 2테이블
- raw telemetry는 summary만 남고 원본은 거의 안 남음

### 31번 문서

- 지금 구조에서 observability와 post-review 결과를 어떻게 함께 소비할지 정리한 문서
- Grafana/Discord/운영 배치 기준의 해석 문서

### 32번 문서

- 앞으로 Prod에서 storage를 어떻게 고정할지 정리한 목표 문서
- ClickHouse 도입 이후의 이상적인 구조

즉:

- `31`은 현재 구조를 운영적으로 묶어주는 문서
- `32`는 목표 저장소 구조를 선언하는 문서
- 현재 코드는 아직 `31`에 더 가깝고, `32`로 가는 중간 단계

---

## 11. 문서 표현을 어떻게 가져가면 좋은가

앞으로는 문서에서 아래 표현을 쓰는 것이 안전하다.

### 31번 문서에는

- “현재 운영/외부 소비 기준”
- “현 코드 및 observability SSOT를 해석하는 문서”
- “warehouse 구현체와 무관하게 적용되는 소비 원칙”

이런 표현이 잘 맞는다.

### 32번 문서에는

- “Production target storage architecture”
- “현재 코드 전부가 아니라 목표 상태를 정의하는 문서”
- “미구현 항목은 backlog/phase 구분이 필요함”

이런 표현이 꼭 들어가는 것이 좋다.

### 현재 코드 설명 문서에는

- “아직 ClickHouse 미구현”
- “warehouse는 과도기 구현”
- “audit schema 보강 전에는 32의 join/key 가정이 전부 성립하지 않음”

이 세 줄이 꼭 들어가야 한다.

---

## 12. 최종 결론

현재 코드, 31번 문서, 32번 문서는 서로 다른 수준의 이야기를 하고 있다.

- 현재 코드는 `실제 구현`
- 31번 문서는 `현재 구조를 외부 소비 관점으로 정리한 운영 문서`
- 32번 문서는 `앞으로의 Production storage 목표 문서`

따라서 지금 가장 올바른 해석은 아래와 같다.

1. `31`은 지금 당장 써도 되는 문서다.
2. `32`는 방향이 좋지만, 아직 구현보다 앞선 목표 설계 문서다.
3. 현재 코드가 `32`와 완전히 같다고 말하면 안 된다.
4. 특히 ClickHouse, rollup table, candidate view, match-centric audit schema는 아직 구현 공백이 있다.
5. PostgreSQL 2테이블 authoritative store 원칙은 현재 코드와 문서에서 가장 안정적으로 맞는 부분이다.
6. 앞으로는 `31 = 소비 전략`, `32 = 목표 저장 구조`, `현재 코드 = 과도기 구현`으로 분리해서 설명하는 것이 가장 정확하다.
