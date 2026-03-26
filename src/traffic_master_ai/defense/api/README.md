# AI Defense Runtime API (v2)

## Scope
- `101-goormgb-frontend`의 AI Telemetry SDK와 직접 맞춘 `/ai/*` 계약 API.
- Runtime 결정 경로는 deterministic 정책 기반이며 online LLM 호출을 하지 않는다.
- VQA 챌린지 계약은 `start/verify` 2개만 사용한다.
- `challengeToken`, `/challenge/event` 경로는 현재 계약 범위에서 사용하지 않는다.

## Run (local)
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pip install -e ".[defense_api]"
python -m uvicorn traffic_master_ai.defense.api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Public API endpoints
- `POST /ai/precheck`
- `POST /ai/telemetry/ingest`
- `POST /ai/challenge/start`
- `POST /ai/challenge/verify`
- `POST /ai/evaluate`
- `GET /healthz`

## Internal routes (Swagger 비노출)
- `GET /readyz`
- `GET /runtime/{state_key}` (`state_key = {sid}:{matchId}`)
- `POST /runtime/vqa/mark`
- `GET /meta/storage`
- `GET /metrics`

## Runtime state key
- 상태 저장 키는 `{sid}:{matchId}`를 사용한다.
- 동일 사용자 다중 경기/탭에서도 telemetry summary가 섞이지 않도록 분리한다.
- `/ai/evaluate`는 `requestPath`에서 `/matches/{matchId}`를 파싱해 동일 키를 조회한다.

## Config
### Runtime store
- `TM_REDIS_URL` (예: `redis://localhost:6379/0`)
- `TM_SESSION_STATE_TTL_SECONDS` (default `1800`)
- Redis 미설정/실패 시 in-memory fallback.

### Precheck
- `TM_TURNSTILE_SECRET_KEY`
- `TM_TURNSTILE_SITEVERIFY_URL` (default Cloudflare siteverify)
- `TM_TURNSTILE_VERIFY_TIMEOUT_MS` (default `500`)
- `TM_PRECHECK_TTL_MS` (default `300000`)

### Challenge
- `TM_CHALLENGE_SECRET` (server-only secret)
- `TM_CHALLENGE_TTL_MS` (default `120000`)
- `TM_CHALLENGE_CATCH_RADIUS_PX` (default `38`)
- `TM_CHALLENGE_TIMING_WINDOW_MS` (default `260`)

### Runtime sanction callback
- `TM_BACKEND_RUNTIME_SANCTIONS_URL` (`TM_BACKEND_SANCTION_URL` fallback)

### Audit / archive
- `TM_DEFENSE_AUDIT_LOG_PATH` (default `logs/defense_decision_audit.jsonl`)
- `TM_S3_BUCKET`
- `TM_S3_PREFIX` (default `ai-defense/audit/`)
- `TM_S3_REGION`
- `TM_S3_ARCHIVE_INTERVAL_SECONDS` (default `3600`)

## Local cURL examples
```bash
curl -X POST http://127.0.0.1:8000/ai/precheck \
  -H 'X-Session-Id: sid_local_dev' \
  -H 'Content-Type: application/json' \
  -d '{"matchId":687,"cfToken":"ok-token"}'
```

```bash
curl -X POST http://127.0.0.1:8000/ai/telemetry/ingest \
  -H 'X-Session-Id: sid_local_dev' \
  -H 'Content-Type: application/json' \
  -d '{"matchId":687,"stage":"QUEUE_ENTER_PRECLICK","events":[{"type":"mousemove","tsMs":1773817200000,"xNorm":0.42,"yNorm":0.77},{"type":"click","tsMs":1773817200200,"xNorm":0.47,"yNorm":0.80,"button":0}]}'
```

```bash
curl -X POST http://127.0.0.1:8000/ai/challenge/start \
  -H 'X-Session-Id: sid_local_dev' \
  -H 'Content-Type: application/json' \
  -d '{"matchId":687}'
```

```bash
curl -X POST http://127.0.0.1:8000/ai/challenge/verify \
  -H 'X-Session-Id: sid_local_dev' \
  -H 'Content-Type: application/json' \
  -d '{"matchId":687,"challengeId":"CH_xxx","caught":true,"catchTsMs":1773817228123,"catchXNorm":0.45,"catchYNorm":0.88}'
```

```bash
curl -X POST http://127.0.0.1:8000/ai/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"event":{"eventType":"QUEUE_ENTER","requestPath":"/queue/matches/687/enter","requestMethod":"POST"},"context":{"sid":"sid_local_dev"}}'
```

## Smoke script
- `/ai` 계약 기준 로컬 점검: `python src/traffic_master_ai/defense/api/examples/local_e2e_check.py`

## OpenAPI
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
