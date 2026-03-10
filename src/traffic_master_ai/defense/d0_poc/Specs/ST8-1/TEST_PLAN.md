# ST8-1 TEST PLAN

## 1) 전체 no-LLM 체인 실행
```bash
cd /Users/jangjihyeon/201-goormgb-ai/pilot/istio_adapter_local
TM_FRONTEND_URL=http://localhost:3000 ./pilot_step8_no_llm_all.sh
```

## 2) 공격 매트릭스 실제 실행 포함(선택)
```bash
TM_FRONTEND_URL=http://localhost:3000 TM_STEP8_RUN_ATTACK_EXECUTE=1 ./pilot_step8_no_llm_all.sh
```

## 3) 기대 결과
- ST4/5/7 결과 파일이 모두 생성된다.
- 실패 시 어느 단계에서 중단됐는지 로그로 식별 가능하다.
