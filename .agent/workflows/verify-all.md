---
description: 공격 시나리오와 방어 단위 테스트를 모두 실행하여 시스템 정합성을 전수 검증합니다.
---

다음 명령어를 실행하여 통합 검증을 수행합니다:

// turbo
1. 공격 시나리오 및 방어 단위 테스트 통합 실행
```bash
pytest tests/defense/test_brain_logic.py tests/defense/test_verifier.py && PYTHONPATH=src python src/traffic_master_ai/attack/a0_poc/run_scenarios.py
```
