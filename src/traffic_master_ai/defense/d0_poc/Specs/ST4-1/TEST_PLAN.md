# ST4-1 TEST PLAN

## 1) 사전 조건
- Frontend/Backend/Envoy/Adapter/AI 런타임이 `pilot/istio_adapter_local` 기준으로 실행 중
- Python venv 활성화

## 2) 실행 커맨드
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate

# pass 모드
TM_FRONTEND_URL=http://localhost:3000 \
TM_ATTACK_CHALLENGE_MODE=pass \
python -m traffic_master_ai.attack.a1_mvp.main --mode MAP

# fail 모드
TM_FRONTEND_URL=http://localhost:3000 \
TM_ATTACK_CHALLENGE_MODE=fail \
python -m traffic_master_ai.attack.a1_mvp.main --mode MAP
```

## 3) 기대 결과
- pass 모드: `CHALLENGE_PASSED` 로그 + S3 복귀 후 다음 상태 진행
- fail 모드: `CHALLENGE_FAILED` 로그 누적 + `terminal_reason=BLOCKED`

## 4) 디버그 경로
- 공격 에이전트 로그: `logs/attack_mvp/*.jsonl`
- 백엔드 로그: `platform/backend` 콘솔
- AI runtime 상태: `GET /runtime/{session_id}`
