# ST5-2 Spec Snapshot — Offline LLM Analysis Schema & Batch Path

## 0. 목적
- Story: **ST5-2**
- 목적:
  - 런타임(`/evaluate`)과 분리된 **오프라인 LLM 분석 배치 경로**를 고정한다.
  - 입력(`decision_audit`) → 세션 집계 → 후보 추출 → 오프라인 판정 → 정책 보정 후보 출력까지 스키마를 확정한다.
  - 트리거는 시간 주기가 아니라 **로그 건수 기반**으로 동작하게 한다.

## 1. IN SCOPE
- 입력 소스: `logs/defense_decision_audit.jsonl`
- 세션 집계 스키마(`SessionAggregate`)
- 오프라인 판정 결과 스키마(`OfflineJudgeResult`)
- 정책 패치 후보 스키마(`offline_policy_patch_candidates.json`)
- 배치 실행 스크립트:
  - `scripts/step5_offline_llm_batch.py`

## 2. OUT OF SCOPE
- 런타임 정책 엔진(`/evaluate`) 변경
- 정책 자동 적용(auto-apply)
- 결제/환불/제재 집행 워크플로우

## 3. 입력/출력 계약
### 입력(JSONL)
- `event_type`: `EVALUATE | CHALLENGE_VERIFIED`
- `session_id`
- `allow`, `action`, `risk_score`, `rule_hits`, `method`, `path` (EVALUATE 시)
- `payload.result` (CHALLENGE_VERIFIED 시)

### 출력 1(JSONL)
- 파일: `logs/offline_judge_results.jsonl`
- 필드:
  - `session_id`
  - `verdict`: `TRUE_BOT | HUMAN | UNCERTAIN | UNAVAILABLE`
  - `confidence`
  - `reasoning_key`
  - `anomalous_features[]`

### 출력 2(JSON)
- 파일: `logs/offline_policy_patch_candidates.json`
- 필드:
  - `id`
  - `target`
  - `current`
  - `proposed`
  - `reason`
  - `manual_review_required=true`

## 4. 트리거 규칙
- `TM_OFFLINE_TRIGGER_MIN_LOGS` 또는 `--min-log-count` 기준으로 실행.
- 로그 건수가 임계치 미만이면 `SKIPPED (NOT_ENOUGH_LOGS)`로 종료.

## 5. 아키텍처 정합성 규칙
- 런타임 경로: `Envoy -> Adapter -> /evaluate` (결정적 정책만)
- 오프라인 경로: `decision_audit -> offline batch -> patch candidates`
- 오프라인 판정 결과는 **참고/승인 대상**이며 런타임에 즉시 반영하지 않는다.

## 6. 변경 금지 규칙
- ST5-2 구현이 `/evaluate` 응답/헤더/지연에 영향 주면 안 됨.
- auto-apply 금지(사람 승인 전 정책 변경 금지).

## 7. DoD
- `tests/defense/test_offline_pipeline.py` 통과
- `scripts/step5_offline_llm_batch.py` 실행 시 summary/results/patches 파일 생성
- 로그 건수 미달 시 SKIPPED 경로 검증
