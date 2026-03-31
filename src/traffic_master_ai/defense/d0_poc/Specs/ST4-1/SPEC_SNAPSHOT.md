# ST4-1 Spec Snapshot — Attack Agent Challenge Bridge (Deterministic Pass/Fail)

## 0. 목적
- Story: **ST4-1**
- 목적:
  - 공격 에이전트가 신규 `catch_ball` 기반 보안 챌린지에 대해 **통과/실패를 의도적으로 재현**할 수 있도록 브리지 계층을 추가한다.
  - Step3 E2E를 깨지 않으면서 Step4 실험 기반(지표/우회 테스트)의 시작점을 만든다.
- 비목적:
  - Vision 모델 연동
  - 외부 LLM 호출
  - 실제 OCR/멀티모달 추론

## 1. IN SCOPE
- `attack/a1_mvp`에 challenge 전략 모드 추가
  - `pass`: 서버 검증 기준을 만족하도록 telemetry 제출
  - `fail`: 의도적으로 실패/차단 경로 유도
- 기존 arithmetic-only 보안 노드와 `catch_ball` 플로우를 공존 처리
- 로그 필드 추가
  - `challenge_mode`, `challenge_type`, `challenge_attempt`, `challenge_result`

## 2. OUT OF SCOPE
- Playwright vision solver 정밀화
- 공격 우회 방어 강화(서버 hardening) 자체 변경
- 운영 환경 배포/Helm 변경

## 3. API 정의(참조)
- 사용 API(기존 유지)
  - `POST /api/security/challenge`
  - `POST /api/security/verify`
- 본 Story는 **엔드포인트 추가/변경 없음**

## 4. 로그 정의
- attack agent audit JSONL에 필수 기록
  - `event=CHALLENGE_MODE_SELECTED`
  - `event=CHALLENGE_ATTEMPT`
  - `event=CHALLENGE_PASSED|CHALLENGE_FAILED`
  - `flow_state=S3` 포함

## 5. 변경 금지 규칙
- L0/L1.5 정책 위배 금지
  - S3 고정 챌린지 정책 유지
  - S6 신규 마찰 금지
- 백엔드 API 계약 스키마 변경 금지

## 6. DoD
- `TM_ATTACK_CHALLENGE_MODE=pass`에서 챌린지 통과 후 플로우 재개
- `TM_ATTACK_CHALLENGE_MODE=fail`에서 실패 누적 후 차단
- 기존 MAP/RECOMMEND 플로우 회귀 없음
- 테스트 문서의 핵심 명령 3개 이상 통과
