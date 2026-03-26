# Defense Spec (Current)

이 디렉토리는 2026-03-25 기준 **현재 운영 계약**만 유지한다.  
기존 구버전 handover/bundle 문서는 정리했고, 아래 문서만 최신 소스로 본다.

## Canonical docs
- `spec/_local/istio_ai_adapter_integration_contract.md`
- `spec/_local/ai_defense_inner_architecture.md`
- `spec/_local/ai_defense_inner_architecture_excalidraw.md`

## Runtime source of truth
- API schema/model: `src/traffic_master_ai/defense/api/models.py`
- API handler: `src/traffic_master_ai/defense/api/main.py`
- Challenge issue runtime: `src/traffic_master_ai/defense/api/challenge_runtime.py`
- Policy defaults: `src/traffic_master_ai/defense/api/policy.py`

## OpenAPI (runtime generated)
- `GET /openapi.json` from running server
- Public path set:
  - `POST /ai/precheck`
  - `POST /ai/telemetry/ingest`
  - `POST /ai/evaluate`
  - `POST /ai/challenge/start`
  - `POST /ai/challenge/verify`
  - `GET /healthz`

## Removed from public contract
- `/challenge/start`
- `/challenge/event`
- `/challenge/verify`
- `challengeToken` request parameter in FE->AI verify path
