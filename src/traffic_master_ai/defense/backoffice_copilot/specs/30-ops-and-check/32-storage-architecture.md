# Production Storage Architecture

## 1. 문서 목적

이 문서는 31-observability-merge-strategy.md를 기준으로
우리 프로젝트의 production storage architecture를 고정한다.

핵심 목표는:

- Runtime observability는 ClickHouse 중심으로 정리하고
- 정책변경/롤아웃은 PostgreSQL control plane + Redis runtime authority로 정리하고
- Backoffice Copilot 최종 결과는 PostgreSQL 중심으로 정리하며
- Redis, S3, ClickHouse, PostgreSQL의 책임을 섞지 않는 것이다.

## 2. 최상위 결론

Production 구조는 아래 4개 저장소로 나눈다.

1. Redis: 실시간 상태 저장
2. S3: 원본 로그 아카이브
3. ClickHouse: observability 메인 warehouse
4. PostgreSQL: Backoffice post-review 정식 결과 + 정책변경 control plane 저장

이 구조는 현재 Runtime/observability 구현 방향과도 맞고,
31-observability-merge-strategy.md의 데이터 소비 구조와도 맞는다.

## 3. 저장소별 책임

### 3.1 Redis

Redis는 request path 상의 실시간 상태를 담당한다.

저장 대상:

- session state
- dedup state
- challenge active state
- temporary halt / cooldown state
- terminal block state
- rollout runtime authority
- active policy cache
- active rollout state projection

Redis에 맡기지 않을 것:

- 장기 보관 로그
- 운영 분석 질의
- 사후판단 최종 결과
- 정책 변경 이력의 authoritative 보관

즉 Redis는 state store이지 warehouse가 아니다.

Prod 기준 keyspace 예시는 아래처럼 기능별로 분리한다.

- `tm:decision-state:session:*`
- `tm:block-state:session:*`
- `tm:event-dedup:*`
- `tm:scoring-window:*`
- `tm:decision-policy:*`
- `tm:s3-challenge:*`
- `tm:turnstile-verdict:*`
- `tm:turnstile-run:*`

현재 최신 `dev`도 decision state Redis 연결과 keyspace 분리 방향으로 맞춰지고 있다.

### 3.2 S3

S3는 append-only 원본 로그 아카이브를 담당한다.

저장 대상:

- rotated decision_audit.jsonl
- 필요 시 raw challenge / VQA artifact

역할:

- 장기 보관
- backfill source
- incident forensics

즉 S3는 archive layer다.

### 3.3 ClickHouse

ClickHouse는 observability 메인 warehouse다.

저장 대상:

- Runtime raw observability event
- KPI / rollup table
- drill-down 조회용 fact table
- post-review 입력용 candidate view

ClickHouse에 맡기지 않을 것:

- 실시간 mutation state
- TTL/lock 중심 상태 관리
- terminal block authoritative state
- request path 상의 강한 transactional write

즉 ClickHouse는 state DB가 아니라 event warehouse다.

### 3.4 PostgreSQL

PostgreSQL은 Backoffice Copilot의 정식 결과 저장소이자
정책변경 control plane의 authoritative DB다.

정식 저장 대상:

- post_review_runs
- post_review_session_results
- policy_versions
- policy_rollout_state
- policy_rollout_events
- policy_optimization_runs

선택적 부가 저장:

- delivery outbox
- export bookkeeping
- policy proposal / validation artifact bookkeeping

즉 PostgreSQL은 최종 판정, 후속조치 상태, 정책변경 메타데이터를 저장한다.

## 4. ClickHouse 설계 원칙

### 4.1 observability warehouse로 사용한다

ClickHouse는 대용량 이벤트 로그 저장과 분석에 강하다.
따라서 raw observability event, KPI 집계, drill-down 조회를 ClickHouse 중심으로 설계한다.

### 4.2 Raw table과 KPI table을 분리한다

한 raw table에 모든 운영 쿼리를 몰아넣지 않는다.

최소 2계층이 필요하다.

- raw fact table
- KPI / rollup table

우리 프로젝트에서는 실무적으로 3계층이 더 적합하다.

1. raw fact table
2. session rollup table
3. match rollup table

그리고 candidate selection은 view로 두는 것이 자연스럽다.

### 4.3 자주 쓰는 필드는 typed column으로 뽑는다

아래 필드는 JSON blob 안에만 두지 않는다.

- 시간
- session_id
- trace_id
- match_id
- event_type
- risk_tier
- action
- reason_code
- http_status
- dedup flag
- policy_version

VQA 때문에 추가로 자주 쓰게 될 필드:

- challenge_id
- challenge_result
- vqa_attempt_score
- vqa_terminal

그 외는 payload JSON으로 보존한다.

### 4.4 파티션은 일 단위로 끊는다

raw fact table 파티션은 by day 정도로 유지한다.

파티션을 너무 잘게 쪼개지 않는다.

### 4.5 insert는 batch 또는 async insert로 운영한다

권장 흐름:

1. 앱이 로컬 JSONL append
2. JSONL rotate
3. S3 업로드
4. collector / ETL이 batch insert

즉 앱이 ClickHouse에 1 row씩 직접 쓰는 구조는 피한다.

### 4.6 Materialized View를 적극 사용한다

운영 KPI는 raw table에 매번 큰 GROUP BY를 걸지 않는다.

Materialized View로 미리 내려놓는다.

대표 MV 대상:

- 분 단위 요청 수
- tier 분포
- action 분포
- block 비율
- throttle delay percentile
- challenge pass/fail 비율
- reason_code 분포

### 4.7 retention을 분리한다

raw와 KPI의 보존기간을 같게 두지 않는다.

권장 예시:

- raw event: 30~90일
- KPI / rollup: 180~365일

## 5. 전체 데이터 흐름

Production 기본 흐름:

1. Runtime / Backend가 canonical audit JSONL append
2. 파일 rotate
3. S3 업로드
4. collector / ETL이 S3에서 읽음
5. ClickHouse raw fact table에 적재
6. Materialized View가 session / match rollup 생성
7. Grafana / 운영 파이프라인은 ClickHouse 조회
8. Backoffice Copilot은 ClickHouse 입력을 읽어 PostgreSQL에 최종 결과 저장
9. Discord / backend delivery는 PostgreSQL 결과 중심으로 소비

정책변경 기본 흐름:

1. Offline optimizer / 운영자가 ClickHouse 지표와 observability evidence를 읽음
2. 정책 patch proposal을 생성하고 검증함
3. 새 policy document를 PostgreSQL `policy_versions`에 저장함
4. 현재 rollout control state를 PostgreSQL `policy_rollout_state`에 저장함
5. rollout 변경 이벤트를 PostgreSQL `policy_rollout_events`에 append함
6. runtime authority가 사용할 active policy / rollout state를 Redis `tm:decision-policy:*`로 projection함
7. Runtime은 request path에서 Redis를 읽어 session별 policyVersion을 결정함
8. Runtime은 선택된 policyVersion과 rollout context를 canonical audit에 기록함
9. ClickHouse는 policyVersion / rolloutStage 기준 효과를 집계하고 rollback 판단 근거를 제공함

## 6. ClickHouse 테이블 구조

### 6.1 Raw fact table

권장 테이블:

- canonical name: defense_audit_events
- optional internal staging name: defense_audit_events_raw

역할:

- Runtime 관측 원본 저장
- drill-down 근거
- replay / backfill 가능한 보존층

네이밍 원칙:

- 외부 소비 문서와 Grafana 질의 계약에서는 defense_audit_events를 canonical 이름으로 사용한다.
- 내부 migration 또는 적재 단계에서 raw suffix가 필요하면 defense_audit_events_raw를 둘 수 있다.
- 단, 외부 계약 문서에서는 defense_audit_events를 우선 이름으로 고정한다.

핵심 typed column:

- ts_ms
- event_date
- match_id
- session_id
- trace_id
- request_id
- event_type
- flow_state
- risk_tier
- action
- reason_code
- http_status
- dedup_is_duplicate
- policy_version
- requested_policy_version
- rollout_stage
- base_policy_version
- candidate_policy_version

VQA 관련 typed column:

- challenge_id
- challenge_result
- challenge_reason_code
- vqa_attempt_score
- vqa_terminal

payload 보존 컬럼:

- raw_payload_json
- request_meta_json
- guard_json
- analyzer_json
- planner_json
- orchestrator_json
- challenge_json
- vqa_json

권장 정렬 키:

- (match_id, session_id, ts_ms, trace_id, event_type)

권장 파티션:

- toDate(event_date) 또는 toDate(ts_ms)

### 6.2 Session rollup table

권장 테이블:

- defense_session_rollups

역할:

- (match_id, session_id) 기준 사후판단 입력 요약

예상 컬럼:

- match_id
- session_id
- first_ts_ms
- last_ts_ms
- latest_flow_state
- latest_action
- latest_tier
- latest_policy_version
- throttle_event_count
- block_event_count
- challenge_issue_count
- challenge_result_count
- challenge_pass_count
- challenge_fail_count
- challenge_halt_count
- turnstile_seen
- terminal_outcome

VQA 요약 컬럼:

- vqa_attempt_count
- vqa_pass_count
- vqa_fail_count
- vqa_terminal_count
- vqa_passed_eventually
- vqa_last_attempt_score
- vqa_max_attempt_score
- vqa_last_reason_codes
- vqa_union_reason_codes

이 테이블이 Backoffice Copilot의 1차 입력이 된다.

### 6.3 Match rollup table

권장 테이블:

- defense_match_rollups

역할:

- match_id 기준 운영 상황판

예상 컬럼:

- match_id
- window_start_ms
- window_end_ms
- session_count
- trace_count
- candidate_count
- throttle_count
- block_count
- challenge_count
- challenge_fail_count
- vqa_terminal_count
- latest_rollout_stage

Grafana / 운영 요약 / batch orchestration은 주로 이 테이블을 본다.

### 6.4 Candidate view

권장 view:

- defense_post_review_candidates_v1

역할:

- session rollup에서 post-review 대상 세션만 선별

이 view는 정식 결과 저장소가 아니라
Backoffice Copilot의 입력 selection layer다.

## 7. 정책변경 저장 전략

정책변경 축은 Runtime, observability, post-review와 별도로
독립된 control plane으로 본다.

핵심 원칙은 아래와 같다.

1. Runtime request path는 PostgreSQL을 직접 읽지 않는다.
2. Runtime의 policy authority는 Redis `tm:decision-policy:*`다.
3. 정책 문서와 rollout 이력의 authoritative store는 PostgreSQL이다.
4. 정책 효과 측정은 ClickHouse에서 한다.
5. S3는 정책 산출물의 선택적 archive일 뿐, runtime authority가 아니다.

즉 정책변경은
`PostgreSQL(control plane) -> Redis(runtime projection) -> ClickHouse(effect measurement)`
구조로 가는 것이 맞다.

### 7.1 왜 PostgreSQL + Redis로 나누는가

정책변경에는 서로 다른 두 성격의 저장이 있다.

- control plane 저장
  - 정책 문서 버전
  - proposal / validation 결과
  - rollout stage
  - rollback 이력
- runtime authority 저장
  - 현재 session이 어떤 policyVersion을 쓸지 결정하는 기준 상태
  - request path에서 바로 읽혀야 하는 활성 policy document

control plane은 PostgreSQL이 더 적합하다.

- row 단위 정합성
- 승인/검증/이력 관리
- append/update가 섞인 운영 workflow
- 사람이 읽는 backoffice 관리와 잘 맞음

runtime authority는 Redis가 더 적합하다.

- 낮은 지연
- 캐시/프로젝션에 적합
- request path에서 즉시 읽기 쉬움

### 7.2 Runtime authority는 Redis로 유지한다

정책 SSOT와 현재 코드 기준으로 runtime은 Redis-first policy store를 사용한다.

Prod에서 Redis가 맡을 범위:

- `tm:decision-policy:version:{policyVersion}`
- `tm:decision-policy:rollout-state`
- `tm:decision-policy:version-index`
- session assignment에 필요한 rollout state projection
- 활성 정책 문서 cache

이 레이어의 역할은 단순하다.

- 현재 활성 policy document를 빠르게 읽는다.
- 현재 rollout stage와 ratio를 빠르게 읽는다.
- sessionId 기반 deterministic assignment를 수행한다.

중요:

- Redis는 정책 문서의 최종 권위 저장소가 아니다.
- Redis는 운영 중 읽기 위한 runtime projection이다.
- 장애나 eviction을 고려하면 authoritative history는 PostgreSQL에 있어야 한다.

### 7.3 PostgreSQL control-plane 테이블

Prod에서는 정책변경용 PostgreSQL 테이블을 별도 논리 영역으로 둔다.

권장 테이블은 아래 4개다.

#### 7.3.1 `policy_versions`

역할:

- 정책 문서 버전의 authoritative store
- 각 policyVersion의 원문, 부모 버전, 생성 경로, 검증 상태 보관

권장 필드:

- `policy_version`
- `schema_version`
- `parent_policy_version`
- `status`
- `source_type`
- `document_json`
- `patch_summary_json`
- `validation_result_json`
- `created_by`
- `created_at`
- `validated_at`
- `activated_at`

권장 `status`:

- `DRAFT`
- `VALIDATED`
- `ACTIVE`
- `ROLLED_BACK`
- `RETIRED`

권장 `source_type`:

- `MANUAL`
- `RULE_BASED`
- `OFFLINE_LLM`
- `HOTFIX`

핵심 원칙:

- policy 문서 원본은 여기서 보관한다.
- runtime은 이 테이블을 직접 읽지 않고 Redis projection을 읽는다.

#### 7.3.2 `policy_rollout_state`

역할:

- 현재 활성 rollout control state의 authoritative row
- Runtime에 projection될 source-of-control

권장 필드:

- `rollout_id`
- `stage`
- `base_policy_version`
- `candidate_policy_version`
- `ratio`
- `evaluation_window_seconds`
- `canary_duration_seconds`
- `expand_step_index`
- `stage_started_at_ms`
- `updated_at_ms`
- `current_status`
- `rollback_reason`

권장 `stage`:

- `NONE`
- `CANARY`
- `EXPAND`
- `ROLLED_BACK`
- `FULL`

핵심 원칙:

- 현재 어떤 policy가 baseline인지
- 어떤 candidate가 몇 % 비율로 붙는지
- 지금 rollout이 어떤 단계인지

를 한 row에서 알 수 있어야 한다.

#### 7.3.3 `policy_rollout_events`

역할:

- rollout / rollback 이력 append-only 로그

권장 필드:

- `event_id`
- `rollout_id`
- `event_type`
- `base_policy_version`
- `candidate_policy_version`
- `stage_before`
- `stage_after`
- `ratio_before`
- `ratio_after`
- `reason_json`
- `metrics_snapshot_json`
- `created_at`
- `created_by`

권장 `event_type`:

- `CANARY_STARTED`
- `CANARY_FINISHED`
- `ROLLOUT_EXPANDED`
- `ROLLOUT_COMPLETED`
- `ROLLBACK_TRIGGERED`
- `ROLLOUT_CANCELLED`

핵심 원칙:

- 현재 상태만 보면 안 된다.
- 어떤 근거로 rollout/rollback 되었는지 이력을 남겨야 한다.

#### 7.3.4 `policy_optimization_runs`

역할:

- offline optimization 실행 단위 메타데이터 저장

권장 필드:

- `run_id`
- `base_policy_version`
- `proposed_policy_version`
- `trigger_type`
- `window_start_ms`
- `window_end_ms`
- `metrics_snapshot_json`
- `proposal_json`
- `validation_result_json`
- `result_status`
- `created_at`
- `finished_at`

권장 `result_status`:

- `NO_CHANGE`
- `PROPOSED`
- `VALIDATED`
- `REJECTED`
- `CANARY_STARTED`
- `ROLLED_BACK`
- `FULLY_APPLIED`

핵심 원칙:

- offline optimizer의 실행 맥락을 재현 가능하게 남긴다.
- observability evidence는 ClickHouse에 있고, optimization run 메타는 PostgreSQL에 둔다.

### 7.4 ClickHouse는 정책 효과 측정 저장소다

정책변경에서 ClickHouse가 맡는 역할은 매우 분명하다.

- `policy_version`
- `requested_policy_version`
- `rollout_stage`
- `base_policy_version`
- `candidate_policy_version`

같은 rollout context가 포함된 observability event를 저장하고,
그 기준으로 KPI를 비교하는 것이다.

즉 ClickHouse는 아래 질문에 답하는 곳이다.

- candidate policy가 block rate를 얼마나 올렸는가
- throttle delay가 baseline 대비 얼마나 증가했는가
- canary 구간에서 s3 fail rate가 악화됐는가
- dedup_duplicate_rate나 internal_error가 튀었는가

반대로 ClickHouse가 맡지 않는 것은 아래다.

- 어떤 policy를 승인할지
- 어떤 rollout state를 현재값으로 볼지
- rollback을 실행한 후 authoritative 상태를 어디에 남길지

이것은 PostgreSQL control plane 책임이다.

### 7.5 S3는 정책 산출물 archive 용도로만 사용한다

정책변경 축에서 S3는 선택적 부가 계층이다.

저장 가능 대상:

- exported policy document bundle
- optimization report export
- metrics snapshot export
- human review artifact

하지만 S3는 아래 역할을 맡지 않는다.

- active policy authority
- rollout current state
- runtime assignment source

즉 정책변경에서 S3는 archive일 뿐, control plane이 아니다.

### 7.6 정책변경용 canonical read/write 경계

Prod에서 코드 경계는 아래처럼 자르는 것이 안전하다.

- Runtime request path
  - read: Redis
  - write: 없음 또는 최소한의 runtime cache refresh
- Offline optimizer / admin workflow
  - read: ClickHouse + PostgreSQL
  - write: PostgreSQL
- Projection worker
  - read: PostgreSQL
  - write: Redis

이 경계가 중요한 이유는 request path에서 PostgreSQL latency나 lock 영향을 받지 않게 하기 위해서다.

### 7.7 정책변경 장애 처리 원칙

AI팀이 문서/코드 레벨에서 정의해야 할 장애 처리 원칙은 아래다.

1. PostgreSQL control plane이 순간 장애여도 Runtime은 Redis의 마지막 정상 projection으로 계속 읽을 수 있어야 한다.
2. Redis projection이 비었거나 손상되면 baseline policy로 fail-safe fallback 할 수 있어야 한다.
3. rollout 변경은 PostgreSQL 반영 성공 후 Redis projection 순서로 적용해야 한다.
4. projection 실패 시 current rollout state는 partial apply로 간주하고 이벤트를 남겨야 한다.
5. rollback은 PostgreSQL state update + Redis projection update가 하나의 운영 절차로 묶여야 한다.

## 8. PostgreSQL 구조

PostgreSQL은 두 개의 논리 영역으로 본다.

1. post-review result plane
2. policy change control plane

### 8.1 post_review_runs

역할:

- 경기 1건 또는 시간 구간 1건의 post-review 실행 요약

권장 필드:

- match_id
- window_start_ms
- window_end_ms
- candidate_count
- suspicious_count
- summary_text_json
- status
- created_at
- updated_at

### 8.2 post_review_session_results

역할:

- 세션별 최종 판정 저장

권장 필드:

- match_id
- session_id
- review_result
- evidence_summary
- session_analysis_json
- backend_delivery_status
- created_at
- updated_at

이 2테이블은 계속 최종 결과의 authoritative store로 유지한다.

## 9. Runtime observability와 post-review 결과의 관계

둘은 대체 관계가 아니다.

- defense_audit_events_* = Runtime의 사건 기록과 운영 분석
- post_review_* = 사후판단의 최종 결론

이 구분은 바꾸지 않는다.

Grafana, Discord, 운영 배치는 이 두 층을 각자 맞는 용도로 읽는다.

## 10. 정책변경과 observability의 관계

정책변경 축도 Runtime observability와 대체 관계가 아니다.

- Redis `tm:decision-policy:*`
  - Runtime이 지금 어떤 policyVersion을 읽을지 결정하는 active authority
- PostgreSQL `policy_*`
  - 정책 문서, rollout state, rollout history, optimization run의 authoritative store
- ClickHouse `defense_audit_events` / rollups
  - 정책 효과를 측정하는 evidence warehouse

이 세 축은 각각 역할이 다르다.

- Redis는 빠르게 적용한다.
- PostgreSQL은 정확하게 기록한다.
- ClickHouse는 효과를 측정한다.

정책변경은 이 셋을 같이 써야 완성된다.

## 11. VQA 저장 전략

VQA는 단순 pass/fail만 저장하면 부족하다.

사후판단에서 실제로 필요한 것은:

- VQA 시도 횟수
- fail 횟수
- eventual pass 여부
- abnormal pass / abnormal fail 여부
- attempt score
- reason code 조합

권장 전략:

1. VQA attempt 결과를 canonical audit 이벤트로 남긴다.
2. raw fact table에서 attempt 단위 evidence를 보존한다.
3. session rollup에서 VQA 요약 컬럼을 집계한다.
4. Backoffice Copilot은 session rollup을 기본 입력으로 사용한다.
5. 필요 시 raw fact table에서 attempt 상세를 본다.

즉 VQA용 별도 운영 DB를 새로 만들기보다
ClickHouse raw + rollup 체인 안으로 넣는 것이 맞다.

## 12. 지금 반드시 보강해야 할 필드

Production-ready 구조로 가려면 canonical audit row에 아래가 필요하다.

- match_id
- requestFeatures
- rolloutStage
- basePolicyVersion
- candidatePolicyVersion
- requestedPolicyVersion
- challenge_result
- challenge_reason_code
- vqa_attempt_score
- vqa_terminal

이유:

- match_id가 있어야 경기 단위 조회와 post-review run 연결이 쉬워진다.
- requestFeatures가 있어야 Runtime이 실제로 본 telemetry summary를 사후판단에 재사용할 수 있다.
- rollout context가 있어야 실험 정책과 정상 정책의 결과를 구분할 수 있다.
- requestedPolicyVersion이 있어야 클라이언트/실험 요청과 서버가 실제 적용한 버전을 비교할 수 있다.
- VQA verify가 이제 runtime risk/tier 흐름에 반영되므로, 최소한 attempt result와 terminal/abnormal 맥락은 warehouse에서 다시 볼 수 있어야 한다.

## 13. 운영 책임 분리

Runtime 팀:

- canonical audit 품질 보장
- ClickHouse raw 입력 품질 보장
- policy rollout projection contract 보장

Backoffice Copilot 팀:

- session 후보 선택
- post-review 결과 생성
- PostgreSQL 저장 품질 보장

정책변경 / optimizer 담당:

- `policy_versions`, `policy_rollout_state`, `policy_rollout_events`, `policy_optimization_runs` 계약 정의
- ClickHouse 기반 효과 측정 기준 정의
- PostgreSQL -> Redis projection 규칙 정의
- rollout / rollback 절차와 failure handling 정의

인프라 / 운영 팀:

- S3 업로드 파이프라인
- ETL / collector
- ClickHouse 운영
- PostgreSQL 운영
- Redis 운영
- Grafana / Discord 연결

## 14. AI팀 실행 체크리스트

이 문서 기준으로 AI팀이 해야 할 일은
`애플리케이션이 DB를 어떻게 사용할지`를 설계하고 구현 가능한 단위로 고정하는 것이다.

인프라 provisioning, secret 주입, DB 인스턴스 운영은 이 문서 범위 밖이다.

### 14.1 문서 / 계약 고정

- [ ] `32-storage-architecture.md`를 production target 문서로 유지한다.
- [ ] `31-observability-merge-strategy.md`를 외부 소비 전략 문서로 유지한다.
- [ ] `33-docs-vs-current-code-gap-analysis.md`를 현재 코드와 목표 구조 차이 설명 문서로 유지한다.
- [ ] `canonical audit`, `near-real-time warehouse`, `session rollup`, `match rollup`, `candidate view`, `policy control plane` 용어 정의를 문서에서 일관되게 맞춘다.
- [ ] `ClickHouse는 observability warehouse`, `PostgreSQL은 결과 저장 + 정책변경 control plane`이라는 문장을 관련 문서에 일관되게 반영한다.

### 14.2 Redis 사용 계약

- [ ] Runtime state와 decision state를 Redis에서 어떻게 나눌지 문서화한다.
- [ ] Redis keyspace 명칭을 현재 코드 기준으로 고정한다.
- [ ] 어떤 키가 runtime authority인지, 어떤 키가 cache/projection인지 분리해서 적는다.
- [ ] request path에서 PostgreSQL을 직접 읽지 않는다는 원칙을 문서에 고정한다.
- [ ] `/meta/storage` 계열에서 어떤 backend 상태를 노출할지 정리한다.

### 14.3 Canonical audit 스키마 보강

- [ ] 현재 `decision_audit` 실제 payload와 목표 payload 차이를 표로 정리한다.
- [ ] top-level 필수 필드를 확정한다.
- [ ] 최소 필드:
  - [ ] `ts_ms`
  - [ ] `session_id`
  - [ ] `trace_id`
  - [ ] `request_id`
  - [ ] `event_type`
  - [ ] `flow_state`
  - [ ] `action`
  - [ ] `reason_code`
  - [ ] `policy_version`
- [ ] production 보강 필드:
  - [ ] `match_id`
  - [ ] `requested_policy_version`
  - [ ] `rollout_stage`
  - [ ] `base_policy_version`
  - [ ] `candidate_policy_version`
  - [ ] `challenge_result`
  - [ ] `challenge_reason_code`
  - [ ] `vqa_attempt_score`
  - [ ] `vqa_terminal`
- [ ] telemetry 요약값을 `requestFeatures`로 저장할지, 기존 `telemetry_features` 이름을 유지할지 결정한다.
- [ ] privacy 규칙상 남기면 안 되는 raw telemetry 범위를 다시 명시한다.

### 14.4 ClickHouse raw fact 설계

- [ ] `defense_audit_events`를 canonical read name으로 고정한다.
- [ ] raw fact DDL 초안을 만든다.
- [ ] typed column과 JSON 보존 컬럼을 나눈다.
- [ ] 파티션과 정렬 키를 확정한다.
- [ ] dedup 기준을 raw fact에 어떻게 반영할지 정한다.
- [ ] policy/rollout 필드를 fact table에 어떻게 넣을지 확정한다.
- [ ] VQA/challenge 관련 최소 typed column만 남기고 과도한 컬럼 증식을 막는다.

### 14.5 Rollup / candidate 계층 정의

- [ ] `defense_session_rollups` 컬럼을 최소한으로 확정한다.
- [ ] `defense_match_rollups` 컬럼을 최소한으로 확정한다.
- [ ] `defense_post_review_candidates_v1` 선별 규칙을 정의한다.
- [ ] candidate view는 결과 저장소가 아니라 selection layer라는 점을 문서화한다.
- [ ] Backoffice Copilot 입력은 raw fact 직접 조회보다 session rollup / candidate view 우선으로 정리한다.

### 14.6 PostgreSQL post-review 결과 계층

- [ ] `post_review_runs`와 `post_review_session_results`를 authoritative result store로 유지한다.
- [ ] 현재 DDL과 문서 설명이 일치하는지 점검한다.
- [ ] 결과 저장 repository 경계를 정한다.
- [ ] `backend_delivery_status` 상태 전이 규칙을 정한다.
- [ ] export 파일은 DB 이후 파생 산출물이라는 원칙을 유지한다.

### 14.7 PostgreSQL policy control-plane 계층

- [ ] `policy_versions` 컬럼과 상태값을 최소한으로 확정한다.
- [ ] `policy_rollout_state`를 단일 current-state row로 가져갈지, 활성 row 방식으로 가져갈지 정한다.
- [ ] `policy_rollout_events`를 append-only 이력 로그로 설계한다.
- [ ] `policy_optimization_runs`에 어떤 실행 메타를 남길지 확정한다.
- [ ] optimizer / admin workflow가 PostgreSQL에 무엇을 쓰는지 분리한다.
- [ ] PostgreSQL -> Redis projection 규칙을 문서화한다.

### 14.8 ETL / collector / projection worker 계약

- [ ] `decision_audit JSONL -> S3 -> ClickHouse` 적재 계약을 정리한다.
- [ ] 현재 `etl_worker.py`가 PostgreSQL 초안이라는 점을 문서에 명시한다.
- [ ] ClickHouse 적재용 collector / ETL의 입력/출력 계약을 정의한다.
- [ ] PostgreSQL control plane -> Redis projection worker 계약을 정의한다.
- [ ] 중복 적재와 partial apply 처리 원칙을 정한다.
- [ ] backfill 절차를 재현 가능하게 문서화한다.

### 14.9 장애 처리 원칙

- [ ] Redis 장애 시 runtime fallback 정책을 정의한다.
- [ ] canonical audit append 실패 시 동작을 정의한다.
- [ ] S3 upload 실패 시 재시도/로컬 보존 정책을 정의한다.
- [ ] ClickHouse 적재 지연 시 운영 영향 범위를 정의한다.
- [ ] PostgreSQL control plane 저장 실패 시 rollout 적용 순서를 정의한다.
- [ ] projection 실패 시 partial apply 이벤트를 어떻게 남길지 정한다.

### 14.10 환경변수 / 연결 계약

- [ ] 앱이 읽을 env 목록을 확정한다.
- [ ] 최소 예시:
  - [ ] `TM_REDIS_URL`
  - [ ] `TM_S3_BUCKET`
  - [ ] `TM_S3_REGION`
  - [ ] `TM_DEFENSE_AUDIT_LOG_PATH`
  - [ ] `TM_CLICKHOUSE_URL` 또는 host/port/user/password/db 조합
  - [ ] `TM_PG_URL`
  - [ ] `TM_ROLLOUT_SALT`
- [ ] 필수 env와 선택 env를 구분한다.
- [ ] env 누락 시 fail-fast / fail-safe 정책을 정한다.
- [ ] `.env.example`과 운영 문서를 동기화한다.

### 14.11 테스트 전략

- [ ] canonical audit payload 생성 테스트
- [ ] schema validation 테스트
- [ ] JSONL rotate / upload 테스트
- [ ] ClickHouse row mapping 테스트
- [ ] session rollup aggregation 테스트
- [ ] candidate selection 테스트
- [ ] PostgreSQL repository insert / update / select 테스트
- [ ] policy control-plane table write/read 테스트
- [ ] PostgreSQL -> Redis projection 테스트
- [ ] env 누락 / 오설정 테스트
- [ ] privacy 금지 필드 미기록 테스트

### 14.12 Grafana / Discord 관련 AI팀 범위

- [ ] Grafana query contract를 정의한다.
- [ ] 어떤 panel이 어떤 table을 읽는지 정리한다.
- [ ] Discord payload contract를 정의한다.
- [ ] `post_review_*` 본문 + `ClickHouse` 보강 필드 조합 규칙을 정한다.
- [ ] 실제 Grafana 대시보드 생성과 실제 Discord webhook 연결은 인프라/운영 책임임을 문서에 명시한다.

### 14.13 이번 최신 `dev` 변경 기준으로 우선 반영할 것

- [ ] decision state가 실제 Redis를 쓰는 구조를 문서에 반영한다.
- [ ] keyspace 예시를 현재 코드 명칭으로 맞춘다.
- [ ] VQA verify 결과가 runtime risk/tier 누적 상태에 반영된다는 점을 VQA 저장 전략에 반영한다.
- [ ] `SEAT_ENTRY`가 gate-only라는 점을 event 해석 문서에 반영한다.
- [ ] `AiChallengeVerifyResponse.reason` 확장을 API/운영 문서에 반영할지 판단한다.
- [ ] `external_score` generic channel 정리를 observability / runtime feature 문서에 반영할지 판단한다.

## 15. 최종 결론

우리 프로젝트의 Production storage architecture는 아래처럼 고정한다.

1. Redis는 실시간 상태만 맡는다.
2. S3는 원본 로그 아카이브만 맡는다.
3. ClickHouse는 observability 메인 warehouse로 사용한다.
4. PostgreSQL은 Backoffice Copilot 최종 결과와 정책변경 control plane 저장소로 사용한다.
5. 정책변경은 PostgreSQL control plane -> Redis runtime projection -> ClickHouse effect measurement 구조로 운영한다.
6. Runtime 관측과 post-review 결과는 분리 저장하되, 외부 소비자는 둘을 함께 읽는다.
7. 병합 기준은 session_id + 시간 구간이며, 정책 효과 비교는 policy_version + rollout_stage를 함께 본다.

이 구조가 현재 프로젝트의 책임 분리, 운영성, ClickHouse 사용 원칙에 가장 잘 맞는다.
