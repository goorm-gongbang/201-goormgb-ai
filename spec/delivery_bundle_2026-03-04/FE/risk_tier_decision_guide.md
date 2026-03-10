# Risk Tier Decision Guide (Latest)

## 0) 운영 모델
- 실시간 판정: deterministic rule 기반
- 사후 분석: 배치(PyOD+LLM 등)로 정책 보정 후보 생성
- 배치 결과는 다음 정책 버전에 반영, 현재 세션 판정에 직접 개입하지 않음

## 1) Tier 의미
- `T0`: 정상
- `T1`: 약한 의심
- `T2`: 높은 의심(애매 케이스)
- `T3`: 매우 위험

## 2) Action 의미
- `NONE`: 무개입
- `CHALLENGE`: Queue Gate 1회 VQA
- `THROTTLE`: read/탐색 요청 감속
- `GATE`: high-value write 제한
- `BLOCK`: 세션 차단

## 3) 핵심 결정 규칙(기본)
- R0: Queue 통과 후 VQA 미통과면 `challenge`
- R1: repetitive pattern 증가 시 `T1` 또는 `T2` 승격
- R2: challenge fail 누적 임계치 이상이면 `T3 + block`
- F5: `flow_state == S6`이면 신규 마찰 금지(기존 개입 유지, 필요 시 block만)

## 4) Tier -> Action 기본 매핑
- `T0`: `none`
- `T1`: `none | throttle(light)`
- `T2`: `throttle(strong)` + high-value POST에서 `gate`
- `T3`: 결정타 근거가 충분하면 `block`

주의:
- T3라도 근거 약하면 즉시 block 남발 금지
- 우선 throttle/gate로 ROI 붕괴를 유도

## 5) Header 소비 규칙
- `x-defense-action` 값 기반 1차 처리
- `x-defense-actions`가 있으면 보조 액션까지 처리
- `x-defense-tier`는 UI 표시/로그 상관분석에 사용

## 6) LLM 관련
- 런타임 LLM 호출 없음
- 배치 분석 호출 주체/주기는 운영정책(로그 건수 기반 트리거)

## 7) 정합성 체크 포인트
- challenge는 queue gate 1회에만 발생하는지
- mid-session challenge가 발생하지 않는지
- S6에서 challenge/throttle/gate가 새로 삽입되지 않는지
