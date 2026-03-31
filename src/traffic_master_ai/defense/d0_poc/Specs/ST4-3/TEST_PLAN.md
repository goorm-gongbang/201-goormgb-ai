# ST4-3 TEST PLAN

## 실행 커맨드
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
python scripts/step4_metrics_report.py \
  --attack-log-dir logs/attack_mvp \
  --decision-log logs/defense_decision_audit.jsonl \
  --latest-n 30 \
  --strict \
  --output logs/step4/st4_3_metrics_report.json
```

## 기대 결과
- 표준 출력에 핵심 KPI 출력
- 리포트 파일 생성: `logs/step4/st4_3_metrics_report.json`
- 임계값 미달 시 non-zero exit 또는 FAIL 상태 출력

## 디버그
- 로그 누락 필드 목록 출력
- 파싱 실패 라인 번호 출력
