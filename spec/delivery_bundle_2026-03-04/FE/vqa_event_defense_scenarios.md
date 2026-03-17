# VQA Event and Defense Scenario Guide (Queue Gate v1)

## 0) 고정 정책
- Queue 통과 직후 1회 VQA 필수
- Mid-session tier 상승만으로 추가 VQA 금지
- Runtime action: `none|challenge|throttle|gate|block`
- S6 신규 개입 금지(BLOCK만 허용)

## 1) 상태/화면 기준
- S2 Queue: `/queue/*`
- S3 Security(VQA): 현재 화면 위 overlay
- S4 Seat MAP: `/seats?mode=MAP`
- S4R/S5R Recommend: `/seats?mode=RECOMMEND`
- S6 Payment: `/payment?orderId=*`

## 2) VQA 라이프사이클
1. Queue 통과
2. `VQA_CHALLENGE_ISSUED` (S3)
3. FE가 challenge 수행
4. `VQA_CHALLENGE_PASSED` 또는 `VQA_CHALLENGE_FAILED`
5. 통과 시 S4/S4R로 복귀

## 3) 이벤트 계약
- `VQA_CHALLENGE_ISSUED`
  - `session_id`, `trace_id`, `challenge_id`, `inserted_at_stage`, `ts_ms`
- `VQA_CHALLENGE_SUBMITTED`
  - `session_id`, `challenge_id`, `attempt`, `ts_ms`
- `VQA_CHALLENGE_PASSED`
  - `session_id`, `challenge_id`, `attempt`, `ts_ms`
- `VQA_CHALLENGE_FAILED`
  - `session_id`, `challenge_id`, `attempt`, `reason_code`, `ts_ms`

## 4) 방어 액션 매핑
- `challenge` -> `403` + `x-defense-action: challenge`
- challenge active 중 high-value 재요청 -> `428 CHALLENGE_REQUIRED`
- `throttle` -> `200` + `x-defense-action: throttle`
- `gate` -> `428` 또는 정책상 deny + `x-defense-action: gate`
- `block` -> `403` + `x-defense-action: block`

## 5) 예시 시나리오
### A. 정상 사용자
- Queue 통과 -> VQA 1회 통과 -> 좌석 단계 진입

### B. 의심 사용자(T2)
- 좌석 탐색 중 반복 패턴 증가
- 추가 VQA 없이 throttle/gate 강화

### C. 실패 누적
- VQA fail 누적 임계치 도달
- `T3 + block`, flow -> SX
