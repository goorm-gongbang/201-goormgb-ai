# ST5-2 TEST PLAN

## 1) 단위 테스트
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
pytest -q tests/defense/test_offline_pipeline.py
```

## 2) 배치 실행(로컬)
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate

python scripts/step5_offline_llm_batch.py \
  --decision-log logs/defense_decision_audit.jsonl \
  --min-log-count 1 \
  --mode mock
```

## 3) 기대 결과
- `logs/offline_batch_summary.json` 생성
- `status=OK`면 아래 파일 생성:
  - `logs/offline_judge_results.jsonl`
  - `logs/offline_policy_patch_candidates.json`
- 로그 건수가 부족하면 `status=SKIPPED`, `reason=NOT_ENOUGH_LOGS`

## 4) Strict 검증(선택)
```bash
python scripts/step5_offline_llm_batch.py \
  --decision-log logs/defense_decision_audit.jsonl \
  --min-log-count 1 \
  --mode mock \
  --strict
```

## 5) 디버그 경로
- 파싱 오류가 의심되면:
  - `logs/defense_decision_audit.jsonl` 라인 JSON 유효성 확인
- 후보가 0건이면:
  - `--min-decisions-per-session` 완화
  - rule_hits/risk_score/challenge 결과가 집계 조건에 맞는지 확인
