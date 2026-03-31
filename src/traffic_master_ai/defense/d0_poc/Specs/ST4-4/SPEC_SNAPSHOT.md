# ST4-4 Spec Snapshot — Bypass Regression Suite

## 0. 목적
- Story: **ST4-4**
- 목적:
  - 알려진 우회 벡터(DOM 주입, 이벤트 위조, 토큰 재사용)에 대한 회귀 테스트를 문서+코드로 고정한다.

## 1. IN SCOPE
- 우회 시나리오 3종
  1) DOM 기반 강제 성공 시도
  2) 비정상 telemetry 주입(시간 역행/불가능 속도)
  3) challenge token replay
- 기대 결과를 명시한 자동 테스트 스크립트

## 2. OUT OF SCOPE
- 전면 침투 테스트
- 분산 봇넷/프록시 인프라 실험

## 3. API/보안 계약
- token consume-once
- session binding 불일치 차단
- 불가능 물리량 검증 실패

## 4. 로그 정의
- `bypass_case`
- `expected_result`
- `actual_result`
- `pass_fail`

## 5. 변경 금지 규칙
- 테스트를 위해 보안 검증을 완화하지 않는다.

## 6. DoD
- 3개 우회 시나리오 모두 기대 결과 충족
- 회귀 스위트 재실행 시 동일 결론
