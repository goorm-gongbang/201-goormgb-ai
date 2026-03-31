# ST5-4 Spec Snapshot — Policy Apply Guardrails (Approval/Rollback Gate)

## 0. 목적
- Story: **ST5-4**
- 목적:
  - 오프라인 배치 결과를 정책에 반영하기 전, 승인/롤백 조건을 코드로 고정한다.
  - 자동 반영 대신 `APPLY_READY | HOLD` 결정을 산출한다.

## 1. IN SCOPE
- 가드레일 평가 모듈:
  - `src/traffic_master_ai/defense/offline/guardrails.py`
- 실행 스크립트:
  - `scripts/step5_policy_guardrails.py`
- 입력:
  - `logs/step5_batch_eval_summary.json`
  - `logs/step5_offline_patch_candidates.json`
- 출력:
  - `logs/step5_policy_apply_decision.json`

## 2. OUT OF SCOPE
- 실제 환경변수 자동 반영
- 실서비스 정책 롤백 배포 자동화

## 3. 가드레일 규칙
- 최소 evaluable 세션 수
- 최소 alignment rate
- 최대 unavailable 비율
- 최대 patch delta 비율
- 수동 승인 토큰(옵션/환경변수 기반)

## 4. 변경 금지 규칙
- 가드레일 통과 전 정책 자동 반영 금지
- runtime `/evaluate` 동작 변경 금지

## 5. DoD
- 가드레일 스크립트가 `APPLY_READY` 또는 `HOLD`를 일관적으로 출력
- strict 모드에서 `HOLD`면 비정상 종료 코드 반환
