# Defense API Contract Package

## Contract vs Tunable
- Fixed: OpenAPI schema (field/type/enum), response header keys, endpoint semantics.
- Tunable: runtime port/host, policy version string, threshold values in policy engine.
- Note: 문서의 포트 값(`8000`)은 baseline 예시입니다.

## Files
- OpenAPI contract: `/Users/jangjihyeon/201-goormgb-ai/spec/defense_api/openapi-defense.v1.yaml`
- Mock service code: `/Users/jangjihyeon/201-goormgb-ai/src/traffic_master_ai/defense/api/main.py`
- Dockerfile: `/Users/jangjihyeon/201-goormgb-ai/src/traffic_master_ai/defense/api/Dockerfile`
- Postgres schema (analytics): `/Users/jangjihyeon/201-goormgb-ai/spec/defense_api/postgres_schema.sql`
- Verification SQL: `/Users/jangjihyeon/201-goormgb-ai/spec/defense_api/verification_queries.sql`
- Storage strategy: `/Users/jangjihyeon/201-goormgb-ai/spec/defense_api/storage_strategy.md`

## Run
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pip install -e ".[defense_api]"
export TM_AI_DEFENSE_HOST=0.0.0.0
export TM_AI_DEFENSE_PORT=8000   # baseline; 팀 환경에 맞게 변경 가능
python -m uvicorn traffic_master_ai.defense.api.main:app --host "${TM_AI_DEFENSE_HOST}" --port "${TM_AI_DEFENSE_PORT}"
```

## Verify
```bash
curl "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/healthz"
curl "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/openapi.json"
curl "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/meta/storage"
```
