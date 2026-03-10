# ST7-1 TEST PLAN

## 1) Dry-run matrix (API key 불필요)
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
python scripts/step7_attack_mode_matrix.py --frontend-url http://localhost:3000
```

## 2) Execute matrix (Playwright 필요)
```bash
python scripts/step7_attack_mode_matrix.py --frontend-url http://localhost:3000 --execute
```

## 3) 기대 결과
- `logs/step7_attack_matrix_summary.json` 생성
- dry-run 모드에서 모든 케이스 `exit_code=0`
