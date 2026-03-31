# ST5-1 Spec Snapshot — Runtime LLM Disabled Lock

## 0. 목적
- Story: **ST5-1**
- 목적:
  - 최신 운영안(ACT v2.0)을 코드/문서에 강제한다.
  - **런타임 LLM 미사용** 원칙을 명시적으로 고정한다.
  - LLM은 사후/오프라인 분석 경로에서만 사용한다.

## 1. IN SCOPE
- `/evaluate` 런타임 경로에서 LLM 호출 로직 제거
- 응답/헤더/audit에서 LLM 관련 필드 제거
- API 문서/가이드에서 runtime LLM 항목 제거
- 테스트로 기존 deterministic 동작 유지 확인

## 2. OUT OF SCOPE
- 오프라인 LLM 배치 파이프라인 구현
- 정책 자동 보정(optimizer) 구현

## 3. 정책 계약
- 런타임 정책:
  - `NONE | CHALLENGE | THROTTLE | GATE | BLOCK`
  - S3 고정 챌린지
  - S6 신규 마찰 금지
  - BLOCK 남발 금지
- LLM:
  - runtime decision path 미사용
  - post-analysis 전용

## 4. 로그 정의
- decision audit는 deterministic 결과만 기록
- LLM 관련 runtime 필드 없음

## 5. 변경 금지 규칙
- `TM_LLM_*` 환경변수로 런타임 판단이 바뀌면 안 됨
- ST4 회귀 결과가 변하면 안 됨

## 6. DoD
- 기존 defense/attack 테스트 통과
- Step4 파일럿 체인 통과
- 문서에서 runtime LLM 참조 제거
