# ST5-4 TEST PLAN

## 1) 단위 테스트
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pytest -q tests/defense/test_offline_replay_guardrails.py
```

## 2) 가드레일 실행
```bash
python scripts/step5_policy_guardrails.py \
  --batch-summary logs/step5_batch_eval_summary.json \
  --patches logs/step5_offline_patch_candidates.json
```

## 3) strict 검증(선택)
```bash
python scripts/step5_policy_guardrails.py \
  --batch-summary logs/step5_batch_eval_summary.json \
  --patches logs/step5_offline_patch_candidates.json \
  --strict
```

## 4) 기대 결과
- `logs/step5_policy_apply_decision.json` 생성
- 승인 조건 부족 시 `decision=HOLD`
- 조건 충족 + 승인 토큰 일치 시 `decision=APPLY_READY`
