# Defense Runtime (Online + VQA Gate + Offline Optimization)

## 1. 문서 목적과 범위
이 문서는 리팩토링 완료 후 기준의 방어 런타임을 정의합니다. 핵심은 실시간 요청 경로에서 결정적(Deterministic) 정책으로 `allow/deny`를 판단하고, VQA 관문과 상태를 일관되게 관리하는 것입니다. LLM은 런타임 경로가 아니라 사후 최적화 경로에서만 사용합니다.

```yaml
document_scope:
  target: "post-refactor defense runtime v1"
  runtime_goal:
    - "deterministic per-request decision"
    - "stable VQA gate orchestration"
    - "strict state/audit contract"
  includes:
    - "online runtime path"
    - "VQA gate maker/verifier"
    - "offline optimization boundary"
  excludes:
    - "temporary compatibility notes"
    - "legacy code-term migration history"
```

## 2. 시스템 경계와 컴포넌트
실시간 경로는 Ingress/Envoy/ext_authz/Adapter/AI Defense API/Backend로 구성됩니다. 상태 저장은 Redis를 사용하고, 로그는 JSONL 원본으로 적재 후 S3와 PostgreSQL 경로로 분리합니다.

```yaml
components:
  online_path:
    - "Client Frontend"
    - "Ingress Gateway"
    - "Envoy + ext_authz"
    - "Authz Adapter"
    - "AI Defense API"
    - "Backend API"
    - "Redis (runtime state)"
  data_path:
    - "Audit Log Stream"
    - "Object Storage (S3, raw JSONL)"
    - "ETL/Batch"
    - "PostgreSQL (analytics/reporting)"
  ai_runtime_modules:
    - "Guard"
    - "Analyzer"
    - "Planner"
    - "Orchestrator"
```

## 3. 전체 워크플로우
온라인 워크플로우는 요청별 판단 경로이고, VQA 워크플로우는 S3 관문의 발급/검증 경로입니다. 오프라인 워크플로우는 로그 기반 정책 튜닝 경로로 런타임과 분리됩니다.

```mermaid
flowchart LR
  subgraph Client["Client"]
    FE["Frontend (Web/App)"]
  end

  subgraph Runtime["Runtime Path (MVP)"]
    IGW["Ingress Gateway"]
    EV["Envoy + ext_authz"]
    AD["Authz Adapter (Go)"]
    AI["AI Defense API (FastAPI)"]
    BE["Backend API (Business)"]
    RS["Redis (Runtime DB)\nsession/tier/risk\n/challenge token\n/dedupe TTL"]
  end

  subgraph Data["Audit / Storage / Analytics"]
    AL["Audit Log Stream (JSONL events)"]
    DA["decision_audit records"]
    TR["trajectory_raw records"]
    S3["Object Storage (S3)\nJSONL objects"]
    ETL["ETL / Batch (Optional)"]
    PG["PostgreSQL (Optional)\nAnalytics / Reporting"]
  end

  FE --> IGW --> EV
  EV --> AD --> AI
  AI <--> RS
  AI --> AD --> EV
  EV -->|"ALLOW only"| BE
  BE --> EV --> FE

  AI --> AL
  BE --> AL
  AL --> DA
  AL --> TR
  DA --> S3
  TR --> S3
  S3 --> ETL --> PG
```

```yaml
workflow_phases:
  online_runtime:
    - "request intercept"
    - "risk/action decision"
    - "allow/deny enforcement"
    - "runtime state commit"
  vqa_gate:
    - "challenge issue"
    - "event ingest"
    - "verify verdict"
    - "state sync and next decision"
  offline_optimization:
    - "log ingestion"
    - "aggregate and evaluate"
    - "patch proposal"
    - "rollout/rollback"
```

## 4. 상태머신
방어 런타임은 `S0~S6,SX` 상태머신을 따릅니다. `SX`는 종단 상태이며 추가 개입을 금지합니다. `S6`에서는 신규 마찰 개입을 금지하고, 차단만 예외로 허용합니다.

```mermaid
stateDiagram-v2
    [*] --> S0
    S0 --> S1: FLOW_START
    S1 --> S2: ENTRY_CLICKED
    S2 --> S3: QUEUE_PASSED
    S3 --> S4: VQA_PASSED
    S4 --> S5: SECTION_SELECTED
    S5 --> S6: HOLD_CONFIRMED
    S6 --> SX: PAYMENT_COMPLETED

    S6 --> S5: TXN_ROLLBACK
    S1 --> SX: ABORT
    S2 --> SX: ABORT
    S3 --> SX: ABORT
    S4 --> SX: ABORT
    S5 --> SX: ABORT
```

```yaml
state_guardrails:
  terminal_rule:
    when: "flowState == SX"
    then: "no replan, no state mutation"
  payment_stage_rule:
    when: "flowState == S6"
    then: "allow NONE or BLOCK only"
  s3_gate_rule:
    when: "request enters S4/S5 and vqa_passed != true"
    then: "REQUIRE_S3"
```

## 5. 의사결정 엔진
방어 엔진은 Guard→Analyzer→Planner→Orchestrator 파이프라인으로 동작합니다. 각 단계는 책임이 분리되어 있어야 하며, 같은 상태 필드에 대한 writer 충돌을 허용하지 않습니다.

```yaml
decision_engine:
  pipeline_order:
    - Guard
    - Analyzer
    - Planner
    - Orchestrator
  modules:
    Guard:
      role: "risk score + tier calculation"
      writes: ["riskScore", "defenseTier"]
    Analyzer:
      role: "evidence and counter update"
      writes: ["challengeFailCount", "holdFailStreak", "seatTakenStreak"]
    Planner:
      role: "action selection"
      outputs: ["NONE", "THROTTLE", "REQUIRE_S3", "BLOCK"]
    Orchestrator:
      role: "transition validation + response shaping"
      writes: ["flowState", "vqaPassed"]
  dedupe:
    key: "traceId|eventType|time_bucket"
    behavior: "duplicate no-op on score/counter updates"
```

## 6. 실행 액션
액션은 런타임에서 결정하고, 집행은 Adapter/Envoy가 수행합니다. THROTTLE은 허용 응답을 유지하면서 지연을 주고, REQUIRE_S3/BLOCK은 deny로 즉시 응답합니다.

```yaml
runtime_actions:
  NONE:
    allow: true
    enforcement: "pass-through"
  THROTTLE:
    allow: true
    enforcement: "adapter delay injection"
    headers:
      - "x-defense-action=throttle"
      - "x-defense-throttle-ms"
  REQUIRE_S3:
    allow: false
    http: 428
    reasonCode: "CHALLENGE_REQUIRED"
  BLOCK:
    allow: false
    http: 403
    reasonCode: "BLOCKED"

enforcement_points:
  adapter:
    - "delay apply"
    - "forward x-defense-* headers"
  envoy:
    - "deny response compose"
```

## 7. 프로토콜/인터페이스 계약
실시간 판단 API와 VQA API는 명확히 분리합니다. 응답 해석은 `HTTP + reasonCode + x-defense-*` 조합으로 고정합니다.

```yaml
api_contract:
  evaluate:
    method: POST
    path: /evaluate
    response_fields:
      - allow
      - action
      - defense_tier
      - headers_to_add
      - reason
  vqa_gate:
    canonical_issue:
      method: POST
      path: /defense/challenge/issue
    canonical_verify:
      method: POST
      path: /defense/challenge/verify
    compatibility_paths:
      - /challenge/start
      - /challenge/event
      - /challenge/verify

header_contract:
  required_response_headers:
    - x-defense-tier
    - x-defense-action
    - x-defense-policy-version
  optional_response_headers:
    - x-defense-throttle-ms
    - x-challenge-type
    - x-block-reason
    - x-correlation-id

reason_http_mapping:
  BLOCKED: 403
  CHALLENGE_REQUIRED: 428
  CHALLENGE_VERIFY_UNAVAILABLE: 503
```

## 8. 데이터/저장소 아키텍처
저장소 책임을 온라인/오프라인으로 분리합니다. Redis는 즉시 판단 상태, S3는 원본 로그, PostgreSQL은 ETL 후 구조화 분석 데이터의 저장소입니다.

```yaml
storage_architecture:
  redis_runtime:
    purpose: "real-time decision state"
    stores:
      - "session/tier/risk"
      - "challenge token/state"
      - "dedupe ttl keys"
  s3_object_storage:
    purpose: "raw immutable audit archive"
    stores:
      - "decision_audit.jsonl"
      - "trajectory_raw.jsonl"
  postgresql_analytics:
    purpose: "query/report/tuning evidence"
    stores:
      - "session-level verdict summary"
      - "aggregated metrics"
      - "policy patch proposal/apply history"
```

## 9. 로그/관측성
런타임은 최소 필수 필드를 가진 감사 로그를 남겨야 하며, 추후 오프라인 분석에서 재현 가능한 형태여야 합니다.

```jsonl
{"ts_ms":1772500000000,"event_type":"EVALUATE","session_id":"sess-001","trace_id":"tr-001","flow_state":"S4","defense_tier":"T2","action":"THROTTLE","allow":true,"reason_code":null,"policy_version":"def-pol-v1","headers_to_add":{"x-defense-action":"throttle","x-defense-throttle-ms":"250"}}
{"ts_ms":1772500000320,"event_type":"S3_CHALLENGE_RESULT","session_id":"sess-001","challenge_id":"CH_abc123","payload":{"result":"FAILED","attempts_used":1,"attempts_left":1}}
{"ts_ms":1772500000800,"event_type":"EVALUATE","session_id":"sess-001","trace_id":"tr-002","flow_state":"S4","defense_tier":"T3","action":"BLOCK","allow":false,"reason_code":"BLOCKED","policy_version":"def-pol-v1"}
```

```yaml
observability_kpis:
  runtime:
    - block_rate
    - require_s3_rate
    - throttle_delay_p50_p90
    - challenge_pass_fail_rate
  integrity:
    - dedup_duplicate_rate
    - missing_feature_rate
```

## 10. 실패 처리와 가드레일
보안과 UX를 같이 만족하려면 장애 경계와 정책 가드레일을 고정해야 합니다. 특히 결제 단계(S6)와 종단 상태(SX) 규칙은 절대 깨지면 안 됩니다.

```yaml
failure_and_guardrails:
  s6_rule:
    constraint: "no new friction except BLOCK"
  terminal_rule:
    constraint: "no mutation after SX"
  challenge_service_failure:
    default: "fail-close"
    http: 503
    reasonCode: CHALLENGE_VERIFY_UNAVAILABLE
    session_semantics:
      - "keep flow at S3"
      - "do not set s3Passed"
      - "do not increment challengeFailCount"
    emergency_override_env: TM_S3_VERIFY_UNAVAILABLE_MODE=fail_open
  adapter_to_ai_timeout:
    behavior: "explicit fallback + audit"
  block_persistence:
    behavior: "terminal-first read before re-evaluation"
```

## 11. 검증 시나리오
검증은 기능 테스트가 아니라 계약 테스트로 정의합니다. 각 케이스는 요청 입력, 기대 응답, 기대 상태, 기대 로그를 동시에 검증해야 합니다.

```yaml
validation_scenarios:
  - id: DR-01
    case: "S4/S5 with vqa_passed=false"
    expect:
      http: 428
      reasonCode: CHALLENGE_REQUIRED
      header_action: REQUIRE_S3
  - id: DR-02
    case: "tier=T2 read request"
    expect:
      allow: true
      header_action: THROTTLE
      throttle_ms: ">=1"
  - id: DR-03
    case: "challenge fail threshold reached"
    expect:
      http: 403
      reasonCode: BLOCKED
      state_flow: SX
  - id: DR-04
    case: "flowState=S6 non-block condition"
    expect:
      action_in: [NONE]
      no_new_challenge: true
  - id: DR-05
    case: "duplicate event"
    expect:
      risk_counter_update: "no-op"
      audit_dedup_flag: true
```

## 12. 운영 체크리스트
운영 시작 전에는 정책/저장소/관측성/가드레일을 함께 점검해야 합니다. 단일 항목만 통과해도 배포 가능한 구조로 보지 않습니다.

```yaml
ops_checklist:
  pre_deploy:
    - "action enum and reasonCode contract locked"
    - "Redis TTL/key schema verified"
    - "S3 raw log path and retention configured"
    - "PostgreSQL ETL job contract validated"
    - "x-defense-* headers verified on Envoy/Adapter path"
    - "S6/SX guardrail tests green"
    - "audit required fields completeness >= 99.9%"
  post_deploy:
    - "block/challenge/throttle KPI dashboard healthy"
    - "offline optimization pipeline isolated from runtime latency"
```

## 13. VQA Gate 상세 원리
현재 VQA는 S3 고정 관문이며, 발급(issue)과 검증(verify) 모두 서버가 주도합니다. 검증은 위치/타이밍 2축으로 판정하고, 실패 누적은 세션 단위 재시도 윈도우로 관리합니다. verify unavailable은 기본적으로 `503 fail-close`로 처리하고, 비상시에만 env override를 허용합니다.

VQA를 단순히 "문제를 맞췄는지"로만 보지 않는 이유는, 공격자가 정답만 계산해서 제출하는 경로를 막아야 하기 때문입니다. 그래서 verify 단계는 `challenge_id`의 유효성(세션 바인딩, 만료, 1회성 사용)과 함께, 실제 플레이 행위가 정상인지(위치/타이밍 일치)를 같이 검사합니다.

실제 동작은 다음 순서입니다.  
issue 단계에서 서버는 `seed`와 목표 좌표/시간(`target_x`, `target_y`, `target_ts_ms`)을 만들고 Redis에 저장합니다. verify 단계에서 클라이언트가 보낸 `catch_ts_ms`, `glove_pos_norm`, `catch_triggered`를 읽어 공간/시간 판정을 수행합니다. PASS면 `s3Passed=true`와 probation을 기록하고, FAIL이면 실패 카운터와 쿨다운/일시정지를 반영합니다.

또한 S3 구간에서는 플레이 텔레메트리 summary(`tremorStdDev`, `linearityRatio`, `avgVelocity`, `dwellTime`, `pathRatio`)를 Guard 입력으로 전달할 수 있습니다. 핵심은 raw 궤적 전체를 저장하는 것이 아니라, 요약 지표만 넘겨 위험 점수에 반영한다는 점입니다.

```yaml
vqa_gate_mechanics:
  stage_constraint: "S3 only"
  issue:
    key: "tm:chal:{challenge_id}"
    stored_fields:
      - session_id
      - seed
      - target_x
      - target_y
      - target_ts_ms
      - expires_at_ms
    ttl_seconds: TM_CHALLENGE_TTL_SECONDS  # default 15
  verify:
    input:
      - catch_ts_ms
      - glove_pos_norm.x
      - glove_pos_norm.y
      - catch_triggered
      - client_viewport.w
      - client_viewport.h
    verdict_formula:
      spatial_ok: "distance(glove,target) <= catch_radius_px / max(viewport.w, viewport.h)"
      temporal_ok: "abs(catch_ts_ms - target_ts_ms) <= timing_window_ms"
    pass_effect:
      - "s3Passed=true"
      - "challengeFailCount=0"
      - "probationUntilMs=now+probation"
    fail_effect:
      - "challengeFailCount += 1"
      - "cooldown/halt 정책 적용"
  unavailable_policy:
    default:
      http: 503
      reasonCode: CHALLENGE_VERIFY_UNAVAILABLE
    emergency_override_env: TM_S3_VERIFY_UNAVAILABLE_MODE
```

## 14. 통합 테스트 실행 방법 (0/1/2)
실행 순서는 반드시 `0 -> 1 -> 2`를 지킵니다. 각 명령은 주석 없이 그대로 실행합니다.

### 0. 전체 켜야하는 서버 명령어
Backend, Envoy/Adapter/AI, Frontend를 모두 기동해야 실제 방어 경로(ext_authz)가 동작합니다.

```bash
# (A) Backend
cd /Users/jangjihyeon/201-goormgb-ai/platform/backend
./gradlew bootRun --console=plain
```

```bash
# (B) Envoy + Adapter + AI Defense
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
docker-compose up -d --build
```

```bash
# (C) Frontend (Envoy 경유)
cd /Users/jangjihyeon/201-goormgb-ai/platform/frontend
TM_API_PROXY_TARGET=http://localhost:10000 npm run dev
```

```bash
# (D) health check
curl -sS http://localhost:8000/healthz
curl -sS http://localhost:9001/healthz
curl -sS http://localhost:9901/server_info
```

### 1. 직접 유저 테스트
브라우저에서 실제 예매 플로우를 수행하고, VQA/차단/지연 반응을 확인합니다.

```yaml
manual_user_test:
  steps:
    - "http://localhost:3000 접속"
    - "게임 선택 -> 대기열 통과"
    - "S3 VQA(보안 퀴즈) 통과 시도"
    - "좌석 선택 -> 홀드 -> 결제"
  expected:
    - "S3 미통과 상태에서 S4/S5 요청 시 428(CHALLENGE_REQUIRED)"
    - "S3 통과 후 다음 단계 진행 가능"
    - "고위험 요청에서 403(BLOCKED) 또는 THROTTLE 헤더 관찰"
  verification:
    - "AI 상태: GET /runtime/{session_id}"
    - "감사 로그: logs/decision_audit.jsonl"
```

### 2. 공격 에이전트 테스트
공격 모드별(pass/fail/solver) 반응을 재현해 방어 계약을 검증합니다.

```bash
# (A) 사전 준비
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pip install -e ".[attack_mvp]"
playwright install chromium
```

```bash
# (B) 드라이런 (실제 동작(브라우저 실행/요청 전송) 없이 설정만 검증하는 모드)
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
python -m traffic_master_ai.attack.a1_mvp.main --dry-run
```

```bash
# (C) PASS 시나리오 (UI solver)
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
TM_FRONTEND_URL=http://localhost:3000 \
python -m traffic_master_ai.attack.a1_mvp.main \
  --mode MAP --challenge-mode pass --challenge-strategy ui_solver
```

```bash
# (D) FAIL/BLOCK 시나리오 (token tamper)
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
TM_FRONTEND_URL=http://localhost:3000 \
python -m traffic_master_ai.attack.a1_mvp.main \
  --mode MAP --challenge-mode fail --challenge-strategy token_tamper
```

```bash
# (E) 전략 매트릭스 실행
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
python scripts/step7_attack_mode_matrix.py --frontend-url http://localhost:3000 --execute
```
