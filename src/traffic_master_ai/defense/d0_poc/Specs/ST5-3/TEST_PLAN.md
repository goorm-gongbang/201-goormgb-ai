# ST5-3 TEST PLAN

## 1) 단위 테스트
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pytest -q tests/defense/test_offline_replay_guardrails.py
```

## 2) Replay dataset 생성
```bash
python scripts/step5_build_replay_dataset.py \
  --decision-log logs/defense_decision_audit.jsonl
```

## 3) Batch evaluator 실행(mock)
```bash
python scripts/step5_batch_evaluator.py \
  --replay-log logs/step5_replay_dataset.jsonl \
  --manifest logs/step5_replay_manifest.json \
  --mode mock
```

## 4) 기대 결과
- `logs/step5_replay_dataset.jsonl` 생성
- `logs/step5_replay_manifest.json` 생성
- `logs/step5_batch_eval_summary.json`에 정합성 지표 포함
