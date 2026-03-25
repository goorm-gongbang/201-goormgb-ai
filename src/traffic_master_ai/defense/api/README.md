# AI Defense Runtime API (v2)

## Scope
- Deterministic runtime decision API for `ext_authz` adapter.
- ACT v2 action model: `NONE | CHALLENGE | THROTTLE | GATE | BLOCK`.
- Queue-exit mandatory VQA gate (one-time per session).
- Challenge protocol includes signed token, one-time consume semantics, raw-event ingestion, and server-side verdict.
- Runtime decision path does **not** use LLM (offline/post-analysis only).

## Run (local)
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pip install -e ".[defense_api]"
python -m uvicorn traffic_master_ai.defense.api.main:app --host 0.0.0.0 --port 8000 --reload
```

## API endpoints
- `POST /ai/precheck/queue-enter`
- `POST /ai/telemetry/ingest`
- `POST /ai/challenge/start`
- `POST /ai/challenge/verify`
- `POST /ai/evaluate`
- `GET /healthz`

## Internal-only routes (Swagger 비노출)
- `GET /readyz`
- `GET /runtime/{session_id}`
- `POST /runtime/vqa/mark`
- `GET /meta/storage`
- `GET /metrics`

## Header vocabulary
- `x-defense-action: none|challenge|throttle|gate|block`
- `x-defense-actions: comma-separated action list`
- `x-defense-tier: T0|T1|T2|T3`
- `x-defense-policy-version: string`
- `x-throttle-ms: int` (when throttled)
- `x-challenge-type: queue_gate` (when challenged)
- `x-gate-mode: high-value-write` (when gated)
- `x-block-reason: string` (when blocked)

## Runtime store config
- `TM_REDIS_URL`: Redis URL (`redis://localhost:6379/0`)
- `TM_SESSION_STATE_TTL_SECONDS`: session state TTL (default `1800`)
- Redis not configured/fails -> in-memory fallback.

## Target route config
- `TM_TURNSTILE_SECRET_KEY`: Cloudflare Turnstile secret key
- `TM_TURNSTILE_SITEVERIFY_URL`: Turnstile verify URL (default Cloudflare `siteverify`)
- `TM_PRECHECK_TTL_MS`: queue-enter precheck TTL in milliseconds (default `300000`)
- `TM_BACKEND_RUNTIME_SANCTIONS_URL`: backend runtime-sanctions endpoint

## Challenge config
- `TM_CHALLENGE_SECRET` (server-only secret)
- `TM_CHALLENGE_TTL_MS` (default `120000`)
- `TM_CHALLENGE_RETRY_LIMIT` (default `2`)
- `TM_CHALLENGE_MAX_EVENTS` (default `6000`)
- `TM_CHALLENGE_MIN_EVENTS` (default `25`)
- `TM_CHALLENGE_MIN_DURATION_MS` (default `400`)
- `TM_CHALLENGE_MAX_DURATION_MS` (default `7000`)
- `TM_CHALLENGE_MAX_SPEED_PX_PER_MS` (default `3.8`)
- `TM_CHALLENGE_MAX_JUMP_PX` (default `220`)
- `TM_CHALLENGE_CATCH_RADIUS_PX` (default `38`)
- `TM_CHALLENGE_TIMING_WINDOW_MS` (default `260`)

## Policy config
- `TM_DEFENSE_POLICY_VERSION` (default `def-pol-2.0.0`)
- `TM_REPETITIVE_PATTERN_T1_THRESHOLD` (default `1`)
- `TM_REPETITIVE_PATTERN_T2_THRESHOLD` (default `3`)
- `TM_CHALLENGE_FAIL_THRESHOLD` (default `3`)
- `TM_T1_THROTTLE_MS` (default `200`)
- `TM_T2_THROTTLE_MS` (default `1800`)
- `TM_VQA_GATE_PATH_PREFIXES` (default `/api/queue/complete,/api/holds,/api/payments,/api/seats/select`)
- `TM_HIGH_VALUE_PATH_PREFIXES` (default `/api/holds,/api/payments,/api/seats/select`)

## Audit log
- `TM_DEFENSE_AUDIT_LOG_PATH` (default `logs/defense_decision_audit.jsonl`)
- `evaluate` decisions and challenge lifecycle events are append-only JSONL.

## Target route local examples
```bash
curl -X POST http://127.0.0.1:8010/ai/precheck/queue-enter \
  -H 'X-Auth-Sid: sid_local_dev' \
  -H 'Content-Type: application/json' \
  -d '{"matchId":687,"turnstileToken":"ok-token"}'
```

```bash
curl -X POST http://127.0.0.1:8010/ai/telemetry/ingest \
  -H 'X-Auth-Sid: sid_local_dev' \
  -H 'Content-Type: application/json' \
  -d '{"stage":"QUEUE_ENTER_PRECLICK","summary":{"tremorStdDev":1.0,"linearityRatio":0.8,"avgVelocity":10.0,"dwellTime":20.0,"pathRatio":1.1}}'
```

```bash
curl -X POST http://127.0.0.1:8010/ai/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"event":{"eventType":"QUEUE_ENTER","requestPath":"/queue/matches/687/enter","requestMethod":"POST"},"context":{"sid":"sid_local_dev"}}'
```

## Offline LLM batch (post-analysis only)
- Runtime path does not call LLM.
- Batch runner consumes decision logs and emits review artifacts:
```bash
cd /Users/jangjihyeon/201-goormgb-ai
python scripts/step5_offline_llm_batch.py --min-log-count 1 --mode mock
```
- Outputs:
  - `logs/offline_judge_results.jsonl`
  - `logs/offline_policy_patch_candidates.json`
  - `logs/offline_batch_summary.json`

## OpenAPI
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Handover snapshot: `/Users/jangjihyeon/201-goormgb-ai/.handover/specs/defense_api/openapi-defense.v2.yaml`
