# ST4-3 Spec Snapshot — Solver Metrics & Quality Gate

## 0. 목적
- Story: **ST4-3**
- 목적:
  - Step4 실험 결과를 정량화하기 위한 최소 메트릭 파이프라인을 제공한다.
  - pass/fail, latency, 차단율을 동일 포맷으로 기록/집계한다.

## 1. IN SCOPE
- attack audit + decision audit에서 필요한 필드 추출
- 단일 요약 리포트 생성 스크립트
- 품질 게이트 임계값(최소 기준) 정의

## 2. OUT OF SCOPE
- 대시보드 구축
- 운영 데이터 ETL 파이프라인 구축

## 3. 로그 정의(필수 지표)
- solver_success_rate
- solver_fail_rate
- median_solver_latency_ms
- blocked_rate_after_fail
- false-pass suspicion count (rule-based)

## 4. 변경 금지 규칙
- 기존 audit 포맷 파괴 금지 (필드 추가만 허용)

## 5. DoD
- 샘플 실행 결과로 리포트 파일 1개 생성
- 품질 게이트 pass/fail 자동 판정 가능
