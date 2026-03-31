# ST4-2 TEST PLAN

## 1) 실행 커맨드
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate

# pass 전략 샘플
for i in $(seq 1 20); do
  TM_ATTACK_CHALLENGE_MODE=pass TM_ATTACK_CHALLENGE_STRATEGY=humanish_pass \
  python -m traffic_master_ai.attack.a1_mvp.main --mode MAP --headless || true
done

# fail 전략 샘플
for i in $(seq 1 20); do
  TM_ATTACK_CHALLENGE_MODE=fail TM_ATTACK_CHALLENGE_STRATEGY=botlike_fail \
  python -m traffic_master_ai.attack.a1_mvp.main --mode MAP --headless || true
done
```

## 2) 기대 결과
- 전략별 통계 집계 가능
- pass/fail 목적과 결과가 일치

## 3) 디버그
- UI selector mismatch 시 Playwright trace 캡처
- `logs/attack_mvp/*.jsonl`에서 drag/timing 필드 검사
