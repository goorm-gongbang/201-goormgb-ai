# ST7-1 Spec Snapshot — Playwright Attack Agent Hardening (No-LLM)

## 0. 목적
- Story: **ST7-1**
- 목적:
  - LLM 없이 공격 에이전트 운용 품질을 높인다.
  - 모드/전략 매트릭스 실행 결과를 표준 JSON으로 남긴다.

## 1. IN SCOPE
- `scripts/step7_attack_mode_matrix.py`
  - MAP/RECOMMEND + challenge strategy 조합 실행
  - dry-run 기본, `--execute` 시 실제 Playwright 주행
  - `logs/step7_attack_matrix_summary.json` 출력

## 2. OUT OF SCOPE
- LLM/VLM 기반 solver
- 분산 IP/프록시 봇넷 실험

## 3. DoD
- dry-run 매트릭스 실행 성공
- 결과 JSON에 case별 exit_code 기록
