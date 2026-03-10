# ST5-3 Spec Snapshot — Replay Dataset + Batch Evaluator

## 0. 목적
- Story: **ST5-3**
- 목적:
  - `decision_audit` 로그에서 재현 가능한 replay dataset을 만든다.
  - replay dataset에 오프라인 판정 배치를 실행하고 정합성 지표를 계산한다.

## 1. IN SCOPE
- replay dataset 생성 스크립트:
  - `scripts/step5_build_replay_dataset.py`
- batch evaluator 스크립트:
  - `scripts/step5_batch_evaluator.py`
- 산출물:
  - `logs/step5_replay_dataset.jsonl`
  - `logs/step5_replay_manifest.json`
  - `logs/step5_batch_eval_summary.json`

## 2. OUT OF SCOPE
- 정책 자동 반영
- 런타임 `/evaluate` 변경

## 3. 계약
- replay manifest는 세션별 `expected_label` 포함:
  - `SUSPICIOUS | HUMAN | UNCERTAIN`
- evaluator는 오프라인 결과(`TRUE_BOT/HUMAN/...`)와 manifest 라벨의 정합성을 계산:
  - `coverage`
  - `alignment_rate`
  - `unavailable_ratio`

## 4. 변경 금지 규칙
- replay/evaluator는 로그 재가공 전용이어야 하며 런타임 경로에 영향 주면 안 됨.

## 5. DoD
- replay dataset 생성 성공
- batch evaluator 실행 성공(mock 모드)
- 정합성 지표 출력 확인
