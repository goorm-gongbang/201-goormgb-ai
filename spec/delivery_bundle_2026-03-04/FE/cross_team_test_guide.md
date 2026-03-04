# Cross-Team Test Guide (AI/FE/BE/Cloud)

목적: 같은 절차로 누구나 공격->방어 경로를 재현할 수 있게 합니다.

## 0) 환경 변수(포트/호스트 가변)

```bash
export TM_FE_PORT=3000           # baseline
export TM_BE_PORT=8080           # baseline
export TM_AI_DEFENSE_PORT=8000   # baseline
```

포트는 팀 환경에 맞게 변경 가능합니다.

## 1) 사전 준비

1. FE 실행

```bash
cd platform/frontend
npm run dev
```

2. BE 실행

```bash
cd platform/backend
./gradlew bootRun
```

3. AI defense API 실행(Cloud 계약 검증용)

```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pip install -e ".[defense_api]"
python -m uvicorn traffic_master_ai.defense.api.main:app --host 0.0.0.0 --port "${TM_AI_DEFENSE_PORT:-8000}"
```

## 2) 계약 검증(OpenAPI/헬스)

```bash
curl "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/healthz"
curl "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/openapi.json"
curl "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/meta/storage"
```

기준 파일:

- `spec/defense_api/openapi-defense.v1.yaml`

## 3) 공격 에이전트 E2E 실행

MAP 모드:

```bash
python -m traffic_master_ai.attack.a1_mvp.main --mode MAP
```

RECOMMEND 모드:

```bash
python -m traffic_master_ai.attack.a1_mvp.main --mode RECOMMEND
```

정상 종료 기준:

- attack log 마지막이 `terminal_reason=DONE`

로그 위치:

- `logs/attack_mvp/attack_mvp_*.jsonl`

## 4) 텔레메트리 수집 검증

```bash
grep '"stage":"TELEMETRY"' platform/backend/logs/decision_audit.jsonl | tail -n 20
```

Raw trajectory 검증:

```bash
grep -c '"datasetId":"human-01"' platform/backend/logs/trajectory_raw.jsonl
```

## 5) AI defense API 단독 판정 테스트

```bash
curl -X POST "http://localhost:${TM_AI_DEFENSE_PORT:-8000}/evaluate" \
  -H "content-type: application/json" \
  -d '{
    "session_id": "sess-demo-1",
    "trace_id": "trace-demo-1",
    "request_id": "req-demo-1",
    "path": "/api/holds",
    "method": "POST",
    "timestamp": 1772500000000,
    "headers": {"x-forwarded-for": "1.2.3.4"},
    "flow_state": "S5",
    "defense_tier": "T1",
    "repetitive_pattern_count": 3,
    "challenge_fail_count": 0,
    "token_mismatch": false
  }'
```

기대:

- `allow=false`
- `action=DEF_CHALLENGE_FORCED`
- `headers_to_add.x-defense-action=challenge`

## 6) 회귀 체크리스트

1. MAP E2E DONE
2. RECOMMEND E2E DONE
3. telemetry audit row 생성
4. raw trajectory row 생성(옵션)
5. defense API openapi/health 정상
6. 차단/챌린지 헤더 규약 유지

## 7) 실패 시 우선 확인

1. `http://localhost:${TM_FE_PORT:-3000}` / `http://localhost:${TM_BE_PORT:-8080}` 기동 여부
2. Playwright 설치 여부
3. `platform/backend/logs/decision_audit.jsonl` 쓰기 권한
4. defense API 의존성(`pip install -e ".[defense_api]"`) 여부
