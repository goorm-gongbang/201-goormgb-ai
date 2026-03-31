# ST4-2 Spec Snapshot — Catch-Ball Solver v1 (Trajectory + Timing)

## 0. 목적
- Story: **ST4-2**
- 목적:
  - Playwright 기반으로 `catch_ball` 상호작용을 실제 UI에서 수행하는 solver v1을 구현한다.
  - 성공/실패 케이스를 확률이 아닌 **제어 가능한 시나리오**로 만든다.
- 비목적:
  - 멀티모달 추론(LLM/VLM)
  - 지능형 궤적 최적화

## 1. IN SCOPE
- 글러브 drag + 타이밍 클릭 자동화 로직
- 최소 2개 전략
  - `humanish_pass`
  - `botlike_fail`
- telemetry 생성/전송 로직 일관성 확인

## 2. OUT OF SCOPE
- 서버-side 챌린지 정책 변경
- 프론트 UI 구조 대개편

## 3. API 정의(참조)
- 기존 `POST /api/security/verify` 사용
- payload는 백엔드 검증 스키마를 만족해야 함

## 4. 로그 정의
- `challenge_solver_strategy`
- `drag_metrics`(경로 길이, curvature, duration)
- `timing_offset_ms`

## 5. 변경 금지 규칙
- 프론트/백엔드 공개 API 계약 변경 금지
- Step3 E2E 경로 손상 금지

## 6. DoD
- `humanish_pass` 성공률 >= 80% (local sample 20회)
- `botlike_fail` 실패/차단 재현률 >= 90% (local sample 20회)
- 평균 solver 지연 측정치 기록
