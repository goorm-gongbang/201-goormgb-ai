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
- OpenAPI: `/Users/jangjihyeon/201-goormgb-ai/spec/delivery_bundle_2026-03-04/CI/openapi-defense.v2.yaml`
- Mock service code: `/Users/jangjihyeon/201-goormgb-ai/spec/delivery_bundle_2026-03-04/CI/ai_defense_api_main.py`
- Dockerfile: `/Users/jangjihyeon/201-goormgb-ai/spec/delivery_bundle_2026-03-04/CI/Dockerfile.ai-defense`

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

## Local Run
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pip install -e ".[defense_api]"
export TM_AI_DEFENSE_HOST=0.0.0.0
export TM_AI_DEFENSE_PORT=8000
python -m uvicorn traffic_master_ai.defense.api.main:app --host "${TM_AI_DEFENSE_HOST}" --port "${TM_AI_DEFENSE_PORT}"
```

## Quick Verify
```bash
curl "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/healthz"
curl "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/openapi.json"
curl -X POST "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/evaluate" \
  -H "content-type: application/json" \
  -d '{"session_id":"sess-ci","path":"/api/holds","method":"POST","timestamp":1772500000000}'
```

## Policy Lock
- Queue 통과 직후 1회 VQA 필수
- Mid-session step-up challenge 금지
- S6 신규 개입 금지(BLOCK만 허용)
