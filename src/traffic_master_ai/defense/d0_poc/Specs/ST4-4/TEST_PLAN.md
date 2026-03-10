# ST4-4 TEST PLAN

## 실행 커맨드
```bash
cd /Users/jangjihyeon/201-goormgb-ai
source .venv/bin/activate
python scripts/step4_bypass_regression.py
```

## 기대 결과
- DOM 주입 우회: 실패 또는 차단
- 이벤트 위조(시간 역행/불가능 속도): 실패
- 토큰 재사용: 실패

## 디버그
- 케이스별 request/response 스냅샷 출력
