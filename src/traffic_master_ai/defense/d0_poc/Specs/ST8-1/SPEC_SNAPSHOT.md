# ST8-1 Spec Snapshot — Full Local E2E Pilot Chain (No-LLM)

## 0. 목적
- Story: **ST8-1**
- 목적:
  - 로컬 파일럿에서 ST4 + ST5(no-key) + ST7(no-LLM)을 한 번에 실행한다.

## 1. IN SCOPE
- `pilot/istio_adapter_local/pilot_step8_no_llm_all.sh`
  - ST4 체인 실행
  - Step5 오프라인 no-key 체인 실행
  - Step7 공격 매트릭스 실행

## 2. OUT OF SCOPE
- LLM API 실호출(openai_compatible)
- Dev/K8s 자동 배포 파이프라인

## 3. DoD
- 스크립트 1회 실행으로 결과 파일 4종 생성:
  - `logs/step4/st4_3_metrics_report.json`
  - `logs/step5_batch_eval_summary.json`
  - `logs/step5_policy_apply_decision.json`
  - `logs/step7_attack_matrix_summary.json`
