# ST5-1 TEST PLAN

## 1) 실행 커맨드
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate

pytest -q \
  tests/defense/test_defense_api_policy.py \
  tests/defense/test_defense_api_challenge.py \
  tests/attack_mvp/test_contracts.py \
  tests/attack_mvp/test_smoke.py \
  tests/attack_mvp/test_catch_ball_payloads.py
```

## 2) 기대 결과
- deterministic 런타임 동작만 사용
- 응답 헤더에 `x-defense-llm-*` 없음
- 기존 ST4 회귀 결과 유지

## 3) 파일럿 통합 검증
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
TM_FRONTEND_URL=http://localhost:3000 ./pilot_step4_all.sh
```
