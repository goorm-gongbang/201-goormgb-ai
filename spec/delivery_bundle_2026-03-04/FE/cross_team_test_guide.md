# Cross-Team Pilot Test Guide (AI/FE/BE/Cloud)

## 0) 목표
- Envoy(ext_authz) -> Adapter -> AI Defense -> Backend 경로 검증
- Queue gate VQA 1회 + mid-session no-challenge 정책 검증

## 1) 기동 순서
1. Backend
```bash
cd /Users/jangjihyeon/201-goormgb-ai/platform/backend
./gradlew bootRun
```

2. Envoy/Adapter/AI
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
docker-compose up -d --build
```

3. Frontend (Envoy 경유)
```bash
cd /Users/jangjihyeon/201-goormgb-ai/platform/frontend
TM_API_PROXY_TARGET=http://localhost:10000 npm run dev
```

## 2) 계약 체크
```bash
curl -sS http://localhost:8000/openapi.json | jq '.info.title,.info.version'
curl -sS http://localhost:9001/healthz
curl -sS http://localhost:9901/server_info
```

## 3) 수동 사용자 테스트
- 브라우저에서 `http://localhost:3000`
- Queue 통과 후 좌석 화면 진입 시 VQA 1회 노출 확인
- VQA 통과 후 좌석 단계 진행 확인

## 4) 공격 에이전트 테스트
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
TM_FRONTEND_URL=http://localhost:3000 python -m traffic_master_ai.attack.a1_mvp.main --mode MAP
```

## 5) 기대 결과
- `x-defense-action` 값은 `none|challenge|throttle|gate|block` 범위
- Queue gate 구간에서만 `challenge` 발생
- mid-session에서는 `throttle/gate/block` 중심

## 6) 종료
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
docker-compose down
```
