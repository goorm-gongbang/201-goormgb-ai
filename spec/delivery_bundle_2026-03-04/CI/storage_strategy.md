# Defense Storage Strategy (MVP-1)

## Contract vs Tunable
- Fixed: 저장소 역할 분리(Runtime/Audit/Analytics), 최소 로그 키 집합, Redis key pattern(`tm:sess:{sessionId}`).
- Tunable: TTL, 버킷 경로, ETL 주기, PostgreSQL 인덱스/파티션, fail policy 모드.
- 아래 숫자 값은 baseline이며 운영 데이터 기반으로 조정 가능합니다.

## Decision
- Runtime state: Redis (default), memory fallback
- Audit origin: append-only JSONL
- Analytics: PostgreSQL (JSONB mixed schema)
- MongoDB: not selected as primary store in MVP-1

## Layer mapping

| Layer | Purpose | Store | Notes |
|---|---|---|---|
| Runtime | low-latency policy state (`flow_state`, `tier`, `risk_score`, counters, budgets) | Redis `tm:sess:{sessionId}` | TTL baseline 1800s (`TM_SESSION_STATE_TTL_SECONDS`) |
| Audit origin | immutable decision evidence | JSONL (`logs/defense_decision_audit.jsonl`) | append-only |
| Raw behavior | high-volume raw points | JSONL + object storage | low-frequency read |
| Analytics | tuning, dashboard, A/B, regression | PostgreSQL | fixed columns + JSONB |

## Why PostgreSQL
1. Session/time/policy-version based aggregations are first-class in SQL.
2. JSONB allows schema evolution for telemetry keys (VQA typing etc).
3. Join-friendly for decisions + telemetry + VQA outcomes.

## Runtime key contract (Redis)

Key pattern:
`tm:sess:{sessionId}`

Fields:
- `flowState`
- `defenseTier`
- `riskScore`
- `probationUntilMs`
- `challengeFailCount`
- `seatTakenStreak`
- `holdFailStreak`
- `heavyBudgetLeft`
- `replanBudgetLeft`
- `policyVersion`

TTL:
- `TM_SESSION_STATE_TTL_SECONDS` (baseline 1800, tunable)

## Logging contract (minimum keys)

Every decision audit record should include:
- `session_id`
- `trace_id`
- `request_id`
- `flow_state`
- `event_type`
- `defense_tier`
- `action`
- `reason_code`
- `policy_version`
- `ts_ms`

Variable fields:
- telemetry details and evolving keys go to nested objects (`telemetry_features`, `payload`, `details`)

## Fail policy

Runtime state backend down:
- Redis unavailable -> memory fallback in local/mvp mode
- Production policy can be switched later (`FAIL_OPEN`/`FAIL_CLOSE`) without API contract change

## Cloud handoff sentence

현재는 decision/raw를 JSONL로 수집 중입니다. MVP-1에서는 실시간 판정 상태를 Redis로 분리하고, 감사 원본은 로그+오브젝트 스토리지로 보존, 분석/튜닝 데이터는 PostgreSQL(JSONB)로 적재하는 3계층 구조로 확정합니다. MongoDB는 이번 단계 기본 저장소로 채택하지 않습니다.
