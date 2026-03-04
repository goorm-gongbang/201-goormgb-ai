# Defense API Contract Package

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
python -m uvicorn traffic_master_ai.defense.api.main:app --host 0.0.0.0 --port 8000
```

## Verify
```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/openapi.json
curl http://localhost:8000/meta/storage
```
