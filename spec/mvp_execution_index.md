# Traffic-Master MVP Execution Index (Current)

## 0. 원칙
- 목표는 **실전 MVP(Playwright + LLM 포함)** 이다.
- `d0_poc` 경로명은 레거시이며, 현재 실행 트랙은 MVP 통합 기준으로 관리한다.

## 1. 단계 목차
1. 계약 고정(SSOT/OpenAPI/헤더/상태/이벤트)
2. 로컬 런타임 골격(Defense API + Redis 상태 + Audit)
3. Istio+Adapter 로컬 파일럿(Envoy ext_authz, allow/deny 경로)
4. VQA 고정 관문(Queue 직후 1회) + 서버 최종판정/토큰 소비
5. 공격/우회 회귀 + 품질게이트(ST4-1~4)
6. **LLM 사후분석 트랙 정리(런타임 미사용 고정)**
7. **Playwright 공격 에이전트 고도화(솔버/우회 시도 포함)**
8. 전체 E2E 파일럿(유저/공격/방어 동시 실험) + Dev 배포 연결

## 2. 현재 상태 (2026-03-08)
- 완료:
  - 2, 3, 4, 5의 로컬 파일럿 기준 실행 가능
  - `pilot/istio_adapter_local/pilot_step4_all.sh`로 ST4 체인 일괄 검증 가능
- 진행 중:
  - 6 (LLM 사후분석 트랙)
    - ST5-1 완료: runtime LLM 비활성 고정
    - ST5-2 완료: offline batch schema/path + runner + test 추가
    - ST5-3 구현: replay dataset + batch evaluator + alignment metric
    - ST5-4 구현: 정책 반영 guardrail(`APPLY_READY|HOLD`) + 승인 토큰 게이트
- 진행 전:
  - 7 (Playwright 공격 솔버 고도화)
    - 비LLM 매트릭스 실행기 추가(`scripts/step7_attack_mode_matrix.py`)
  - 8 (실험 자동화 + dev 환경 연결)
    - no-key 통합 체인 추가(`pilot_step8_no_llm_all.sh`)

## 3. Step5 정의 (다음)
- 목적:
  - LLM을 런타임이 아닌 **사후 분석/정책 보정 전용**으로 분리
- 산출물:
  - `ST5-1`: runtime LLM disabled lock
  - `ST5-2`: offline judge input/output schema
  - `ST5-3`: replay dataset + batch evaluator 스크립트
  - `ST5-4`: 정책 반영 가드레일(승인/롤백 조건)
  - 로컬 실행:
    - `python scripts/step5_offline_llm_batch.py --min-log-count 1 --mode mock`
    - `./scripts/step5_no_key_all.sh`

## 4. 정합성 체크포인트
- FE/BE/Adapter/AI가 동일 계약(상태/헤더/reasonCode)을 사용해야 함
- VQA는 Queue 직후 1회 고정 관문 정책을 유지
- S6(결제) 신규 마찰 금지 규칙 유지
