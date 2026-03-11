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

## 2. 현재 상태 (2026-03-10)
- 완료:
  - Step 2: 런타임 골격 (Defense API + 상태관리 + Audit)
  - Step 3: Istio+Adapter 로컬 파일럿 (`pilot_step3_e2e.sh`)
  - Step 4: VQA 관문 + 품질게이트 (`pilot_step4_all.sh`)
    - ST4-2: 실주행 E2E (`pilot_step4_st2_e2e.sh`)
    - ST4-3: 지표/회귀 검증 (`pilot_step4_st3_metrics.sh`)
    - ST4-4: bypass regression 3케이스 (`step4_bypass_regression.py`)
  - Step 5: LLM 사후분석 트랙
    - ST5-1: runtime LLM 비활성 고정
    - ST5-2: offline batch schema/path + runner + test
    - ST5-3: replay dataset + batch evaluator + alignment metric (`step5_batch_evaluator.py`, `step5_build_replay_dataset.py`)
    - ST5-4: 정책 반영 guardrail (`step5_policy_guardrails.py`) + 승인 토큰 게이트
    - no-key 통합 체인 (`step5_no_key_all.sh`)
    - with-key 통합 체인 (`step5_with_key_all.sh`)
  - Step 7: 비LLM 공격 매트릭스 (`step7_attack_mode_matrix.py`)
    - ui_solver CI 리포트 (`step7_ui_solver_ci_report.py`)
  - Step 8: 통합 E2E 체인
    - no-LLM 통합 (`pilot_step8_no_llm_all.sh`)
    - with-key 통합 (`pilot_step8_with_key.sh`)
  - Cloud 팀 인수인계 문서 작성 (`spec/cloud_team_handover_istio_adapter.md`)
  - 정합 문서 최신화 (`spec/aligned_docs_2026-03-10/`)

- 진행 중:
  - spec/ 폴더 최신화 및 정리
  - Cloud 팀 Istio Adapter 전달 준비

- 진행 전:
  - K8s/Istio 실 환경 배포 (Cloud 팀 담당)
  - 실전형 VQA solver 고도화 (vision + trajectory 정교화)
  - Dev 환경 연결 자동화

## 3. 주요 실행 스크립트 목록

### Pilot 스크립트 (`pilot/istio_adapter_local/`)
| 스크립트 | 용도 |
|---|---|
| `pilot_up.sh` | 전체 스택 기동 (Backend + Docker + Frontend) |
| `pilot_down.sh` | 전체 스택 종료 |
| `pilot_check.sh` | 헬스체크 + ext_authz 경유 검증 |
| `pilot_step3_e2e.sh` | Step3 E2E (유저 성공 + 공격 차단) |
| `pilot_step4_st2_e2e.sh` | Step4-2 실주행 E2E |
| `pilot_step4_st3_metrics.sh` | Step4-3 지표/회귀 strict gate |
| `pilot_step4_all.sh` | Step4 전체 체인 |
| `pilot_step8_no_llm_all.sh` | Step8 no-LLM 통합 체인 |
| `pilot_step8_with_key.sh` | Step8 with-key 통합 체인 |

### 분석/검증 스크립트 (`scripts/`)
| 스크립트 | 용도 |
|---|---|
| `step4_bypass_regression.py` | bypass regression 3케이스 |
| `step4_metrics_report.py` | 지표 리포트 생성 |
| `step5_build_replay_dataset.py` | replay dataset 생성 |
| `step5_batch_evaluator.py` | 배치 평가기 |
| `step5_offline_llm_batch.py` | 오프라인 LLM 배치 |
| `step5_policy_guardrails.py` | 정책 반영 가드레일 |
| `step5_re_evaluate_loop.py` | 재평가 루프 |
| `step5_no_key_all.sh` | Step5 no-key 일괄 |
| `step5_with_key_all.sh` | Step5 with-key 일괄 |
| `step7_attack_mode_matrix.py` | 공격 전략 매트릭스 |
| `step7_ui_solver_ci_report.py` | UI solver CI 리포트 |

## 4. 정합성 체크포인트
- FE/BE/Adapter/AI가 동일 계약(상태/헤더/reasonCode)을 사용해야 함
- VQA는 Queue 직후 1회 고정 관문 정책을 유지
- S6(결제) 신규 마찰 금지 규칙 유지
- OpenAPI 단일 기준: `openapi-defense.v2.yaml`

## 5. 관련 문서
- 정합 문서: `spec/aligned_docs_2026-03-10/`
- Cloud 인수인계: `spec/cloud_team_handover_istio_adapter.md`
- 전달 번들: `spec/delivery_bundle_2026-03-04/`
- 파일럿 아키텍처: `pilot/istio_adapter_local/NOTION_LOCAL_PILOT_ARCHITECTURE.md`
