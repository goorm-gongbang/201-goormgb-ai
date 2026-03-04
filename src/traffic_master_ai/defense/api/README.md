# AI Defense Mock API (v1)

## Purpose
- Cloud/Authz Adapter integration stub for `POST /evaluate`
- Deterministic rule-based decisions until full defense service is implemented
- Runtime state persistence split: Redis (preferred) or memory fallback
- Audit evidence: append-only JSONL

## Run (local)
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pip install -e ".[defense_api]"
python -m uvicorn traffic_master_ai.defense.api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Runtime store config
- `TM_REDIS_URL`: Redis URL (예: `redis://localhost:6379/0`)
- `TM_SESSION_STATE_TTL_SECONDS`: session TTL (default: `1800`)
- Redis 미설정 또는 연결 실패 시 메모리 저장소로 자동 fallback
- 예시: `/Users/jangjihyeon/201-goormgb-ai/src/traffic_master_ai/defense/api/.env.example`

## Audit log config
- `TM_DEFENSE_AUDIT_LOG_PATH`: defense 의사결정 로그 경로
- default: `logs/defense_decision_audit.jsonl`

## API docs
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Contract file (handover): `/Users/jangjihyeon/201-goormgb-ai/.handover/specs/defense_api/openapi-defense.v1.yaml`

## Docker
```bash
cd /Users/jangjihyeon/201-goormgb-ai
docker build -f src/traffic_master_ai/defense/api/Dockerfile -t ai-defense:local .
docker run --rm -p 8000:8000 ai-defense:local
```

## Sample request
```bash
curl -X POST http://localhost:8000/evaluate \
  -H "content-type: application/json" \
  -d '{
    "session_id": "sess-abc123",
    "trace_id": "trace-001",
    "request_id": "req-001",
    "path": "/api/holds",
    "method": "POST",
    "timestamp": 1772500000000,
    "headers": {"x-forwarded-for": "1.2.3.4"},
    "flow_state": "S5",
    "defense_tier": "T1",
    "repetitive_pattern_count": 3
  }'
```

## Additional endpoints
- `GET /runtime/{session_id}`: 현재 세션 런타임 상태 조회
- `GET /meta/storage`: runtime store backend 확인 (`redis`/`memory`)
