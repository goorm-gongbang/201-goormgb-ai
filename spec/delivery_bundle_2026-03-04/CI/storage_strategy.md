# Defense Storage Strategy (MVP-2)

## 결정 요약
- Runtime state: Redis (`tm:sess:{sessionId}`)
- Audit origin: append-only JSONL + object storage
- Analytics: PostgreSQL(JSONB)
- MongoDB: MVP 기본 저장소로 미채택

## Contract vs Tunable
- Fixed:
  - 저장소 역할 분리(Runtime/Audit/Analytics)
  - 최소 로그 키 집합
  - Redis key pattern
- Tunable:
  - TTL, ETL 주기, object storage 경로, PostgreSQL index/partition
  - 사후 분석 실행 트리거(시간기반/건수기반)

## Layer Mapping

| Layer | Purpose | Store | Notes |
|---|---|---|---|
| Runtime | low-latency policy state | Redis | TTL baseline 1800s |
| Audit origin | immutable decision evidence | JSONL + object storage | append-only |
| Raw challenge telemetry | VQA raw pointer events | JSONL + object storage | 고용량 원본 보존 |
| Analytics | KPI/tuning/reporting | PostgreSQL(JSONB) | ETL 적재 |

## Redis Runtime Contract
Key: `tm:sess:{sessionId}`

필수 필드:
- `flow_state`
- `defense_tier`
- `risk_score`
- `challenge_fail_count`
- `vqa_required`
- `vqa_passed`
- `vqa_attempt_count`
- `active_challenge_id`
- `policy_version`

## Audit Minimum Fields
- `ts_ms`
- `trace_id`
- `session_id`
- `request_id`
- `flow_state`
- `defense_tier`
- `action`
- `reason_code`
- `policy_version`
- `latency_ms`

## Batch Analysis Trigger Policy
- Runtime 차단 판정에는 배치 분석 결과를 직접 사용하지 않음
- 배치(PyOD+LLM 등)는 **로그 건수 기반 트리거**로 실행(시간 고정 주기 아님)
- 배치 결과는 다음 배포 정책/threshold 보정 후보로만 사용

## Backup / Retention
- JSONL: 일 단위 object storage 업로드
- PostgreSQL: 일 백업 + PITR(운영 환경)
- Redis: runtime cache 성격, 장기 백업 대상 아님

## Cloud 전달 문장(요약)
실시간 판정 상태는 Redis, 감사 원본은 JSONL+오브젝트 스토리지, 분석/튜닝 데이터는 PostgreSQL(JSONB)로 분리합니다. 배치 분석은 로그 건수 기반 트리거로 운영하며, 런타임 차단 경로와 분리합니다.
