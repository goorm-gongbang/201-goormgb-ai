# Defense API Contract Package (v2)

## Scope
- Istio/Adapter가 호출하는 실시간 판정 API 제공
- Queue Gate VQA(1회 고정) 시작/이벤트/검증 API 제공
- Runtime LLM/Honey/Sandbox 없이 deterministic 정책으로 운영

## Contract vs Tunable
- Fixed:
  - OpenAPI 필드명/타입/enum
  - endpoint semantics
  - `x-defense-*` 헤더 키
- Tunable:
  - port/host
  - threshold/TTL/delay
  - challenge difficulty/attempt limit

## Canonical Files
- OpenAPI: `CI/openapi-defense.v2.yaml`
- Dockerfile: `CI/Dockerfile.ai-defense`
- 실제 구현체: `src/traffic_master_ai/defense/api/main.py`

## Runtime Action Vocabulary
- `none`
- `challenge` (queue gate 1회에서만)
- `throttle`
- `gate`
- `block`

## 주요 엔드포인트
- `GET /healthz`
- `GET /readyz`
- `POST /evaluate`
- `POST /challenge/start`
- `POST /challenge/event`
- `POST /challenge/verify`
- `GET /runtime/{session_id}`
- `POST /runtime/vqa/mark`
- `GET /meta/storage`

## Local Run
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pip install -e ".[defense_api]"
export TM_AI_DEFENSE_HOST=0.0.0.0
export TM_AI_DEFENSE_PORT=8000
python -m uvicorn traffic_master_ai.defense.api.main:app --host "${TM_AI_DEFENSE_HOST}" --port "${TM_AI_DEFENSE_PORT}"
```

## Docker Run (via pilot)
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
docker-compose up -d --build
```

## Quick Verify
```bash
curl "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/healthz"
curl "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/openapi.json"
curl -X POST "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/evaluate" \
  -H "content-type: application/json" \
  -H "X-Session-Id: sess-ci" \
  -H "X-Trace-Id: trc-ci-1" \
  -d '{"session_id":"sess-ci","path":"/api/holds","method":"POST","timestamp":1772500000000}'
```

## Policy Lock
- Queue 통과 직후 1회 VQA 필수
- Mid-session step-up challenge 금지
- S6 신규 개입 금지(BLOCK만 허용)
