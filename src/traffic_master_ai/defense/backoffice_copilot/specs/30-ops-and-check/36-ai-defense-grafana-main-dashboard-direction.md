# AI Defense Grafana Main Dashboard Direction

## 1. 문서 목적

이 문서는 `AI 텔레메트리 & 봇 탐지 현황` 보드를
AI Defense 메인 대시보드로 발전시키기 위한 방향성을 정리한다.

이번 문서의 범위는 Grafana 메인 보드다.

- Discord 알림 설계는 별도 최소안으로 거의 정리된 상태로 본다.
- 실시간 폴링 모니터링은 Queue/Backend 대시보드 범위로 두고,
  AI 메인 대시보드 범위에 넣지 않는다.

한 줄 요약:

- 메인 AI 모니터링은 `Telemetry -> Evaluate -> Challenge -> Authz -> Fail-open -> BE block sync` 파이프라인 중심으로 재구성한다.
- `Precheck`는 당분간 접이식 보조 섹션으로만 둔다.

---

## 2. 이 보드로 얻고자 하는 것

이 보드의 목적은 단순 서비스 헬스 확인이 아니다.

운영자가 이 보드로 1분 안에 답해야 하는 질문은 아래다.

1. 지금 AI Defense 파이프라인이 각 단계에서 정상적으로 흘러가고 있는가
2. 지금 어떤 단계에서 병목, 실패, fail-open, block sync 누락이 생기고 있는가
3. 지금 차단/챌린지/허용 분포가 어디에서 달라지고 있는가

즉 이 보드는
`실시간 폴링 수요를 보는 보드`가 아니라
`AI Defense 파이프라인의 단계별 상태와 결과를 추적하는 보드`여야 한다.

---

## 3. 범위와 비범위

### 3.1 범위

- AI 서버 custom metric
- Authz Adapter metric
- `/ai/evaluate` 중심 판정 흐름
- challenge 발동과 verify 결과
- authz -> AI 호출 상태와 지연
- fail-open 발생 여부
- backend block sync 결과와 지연

### 3.2 비범위

- 실시간 폴링량/좌석 대기열 상태
- Queue/Backend 자체 서비스 운영 보드
- Precision, FPR, 혼합 트래픽 비율별 정확도
- attack agent 로그 + audit 로그를 결합해야만 계산 가능한 offline 품질 지표

메모:

- `실시간 폴링 모니터링`은 Queue/Backend 중심 보드로 본다.
- `AI 텔레메트리 & 봇 탐지 현황`은 AI Defense 메인 보드로 본다.

---

## 4. 실제 계측 기준

### 4.1 AI 서버 custom metric

| 메트릭 | 의미 |
| --- | --- |
| `ai_defense_evaluate_total{decision}` | `/ai/evaluate` 최종 action 분포 |
| `ai_defense_precheck_total{result}` | precheck pass/fail |
| `ai_defense_challenge_start_total` | challenge start 요청 수 |
| `ai_defense_challenge_verify_total{result}` | challenge verify 결과 분포 |
| `ai_defense_vqa_telemetry_score_total{decision}` | VQA telemetry score 결과 분포 |
| `ai_defense_telemetry_ingest_total{stage}` | stage별 telemetry ingest 수 |
| `ai_defense_block_sync_total{outcome}` | backend block sync 결과 분포 |
| `ai_defense_block_sync_latency_seconds` | backend block sync 지연시간 |

### 4.2 Authz Adapter metric

| 메트릭 | 의미 |
| --- | --- |
| `authz_adapter_check_requests_total{method,path_prefix,result}` | ext_authz check 요청 결과 |
| `authz_adapter_check_latency_seconds{method}` | ext_authz check 지연 |
| `authz_adapter_ai_defense_calls_total{status}` | authz -> AI 호출 상태 |
| `authz_adapter_ai_defense_latency_seconds` | authz -> AI 호출 지연 |
| `authz_adapter_decisions_total{decision,action}` | authz 단계의 최종 판정 분포 |
| `authz_adapter_fail_open_total` | fail-open 발생 수 |
| `authz_adapter_skipped_checks_total` | 스킵된 check 수 |

주의:

- `authz_adapter_decisions_total`은 현재 코드상 라벨 이름과 실제 값 의미가 어긋나 있다.
- 현재는 `decision=AI action(BLOCK/NONE/THROTTLE/REQUIRE_S3)`, `action=eventType(QUEUE_ENTER/SEAT_ENTRY/...)`로 해석해야 한다.
- Queue/Seat 전용 판정 분포는 이 메트릭을 기준으로 우선 분리 가능하다.

---

## 5. 메인 보드 구조 원칙

메인 보드는 아래 6개 파이프라인 섹션으로 구성한다.

1. `Telemetry`
2. `Evaluate`
3. `Challenge`
4. `Authz`
5. `Fail-open`
6. `BE block sync`

구성 원칙:

- 위에서 아래로 실제 요청 흐름이 읽혀야 한다.
- 각 섹션은 `요청량`, `결과 분포`, `성공/실패`, `지연` 중 필요한 것만 둔다.
- 서비스 헬스 패널은 이 보드의 주인공이 아니다.
- 로그 스트림은 메인 화면이 아니라 triage 보조 화면으로 둔다.

---

## 6. 지금 되어있고 유지할 것

| 항목 | 상태 | 메모 |
| --- | --- | --- |
| AI 서비스 요청률 | 있음 | 기본 서비스 상태 확인 |
| AI 서비스 응답시간 (P95) | 있음 | AI 처리 지연 확인 |
| 실행 인스턴스 | 있음 | 인스턴스 생존 확인 |
| AI 서비스 로그 스트림 | 있음 | 장애 추적용. 메인 핵심 섹션은 아님 |
| 텔레메트리 수집 건수 | 있음 | FE -> AI direct 호출량 확인 |
| AI API 요청 추이 | 있음 | direct API 트래픽 추이 확인 |
| 엔드포인트 분포 | 있음 | `/ai/telemetry/ingest`, `/ai/challenge/*` 분포 확인 |
| ext_authz 판정 추이 | 있음 | 전체 판정 흐름 확인 |
| 판정 결과 비율 | 있음 | 허용/차단/챌린지 분포 확인 |
| 인증 검사 요청량 (req/s) | 있음 | authz 검사량 확인 |
| 인증 검사 지연시간 (ms) | 있음 | authz 처리 지연 확인 |
| gRPC 성공률 | 있음 | ext_authz 경로 안정성 확인 |

메모:

- 위 패널들은 삭제 대상이 아니라 재배치 대상이다.
- 다만 메인 KPI와 보조 패널을 다시 나눌 필요가 있다.

---

## 7. 지금 패널은 있는데 수정이 필요한 것

| 항목 | 왜 필요한지 | 현재 문제 | 수정 방향 |
| --- | --- | --- | --- |
| 스테이지별 수집 | `QUEUE_ENTER_PRECLICK`, `SEAT_STAGE`, `VQA_CHALLENGE`별 수집량 확인 | 현재 집계 기준이 틀렸거나 모호함 | `ai_defense_telemetry_ingest_total{stage}` 기준으로 교체 |
| 챌린지 verify API 호출 성공률 | verify API가 정상 응답하는지 확인 | 현재 패널명이 실제 의미보다 넓음 | 패널명 기준을 `Challenge verify API 호출 성공률`로 명확화 |
| AI Defense API 호출량 | authz -> AI 호출 상태 확인 | 대시보드 메트릭 이름이 코드와 다름 | `authz_adapter_ai_defense_calls_total` 기준으로 교체 |
| AI Defense API 지연시간 | authz -> AI 호출 지연 확인 | 대시보드 메트릭 이름이 코드와 다름 | `authz_adapter_ai_defense_latency_seconds` 기준으로 교체 |
| Queue/Seat 판정 분포 해석 | 단계별 판정 흐름 해석 | `authz_adapter_decisions_total` 라벨명과 실제 값 의미가 어긋남 | 현재는 `decision=AI action`, `action=eventType`으로 해석하고 추후 라벨 정리 검토 |

---

## 8. 지금 안 되어 있는데 필요한 것

| 항목 | 목적 |
| --- | --- |
| Queue Enter 전용 판정 결과 분포 | `Queue 차단율`과 직접 연결. 현재는 `authz_adapter_decisions_total`에서 `action=\"QUEUE_ENTER\"` 기준 분리 가능 |
| Seat Stage 전용 판정 결과 분포 | seat 진입 전 차단, 추천 ON/OFF 차이 설명용 |
| Challenge start 요청량 | 챌린지 발동 빈도 확인 |
| Challenge verify 통과율 | 실제 verify `pass` 비율 확인 |
| Challenge verify 결과 분포 | `pass/fail/invalid/expired/abnormal_terminal` 분포 확인 |
| VQA telemetry score 결과 분포 | `skip/observe/allow/terminal` 분포 확인 |
| Authz -> AI 호출 상태 분포 | `success/error/timeout` 확인 |
| Fail-open 건수 | AI 장애 시 fail-open 발생량 확인 |
| Fail-open 비율 | authz check 대비 fail-open 영향 확인 |
| BE block sync 요청 건수 | AI가 `BLOCK` 판정 후 backend block API를 호출한 횟수 확인 |
| BE block sync 결과 분포 | `blocked`, `already_blocked`, `forbidden`, `not_found`, `unauthorized`, `request_error`, `skipped_missing_user_id`, `disabled`, `unexpected_status` 확인 |
| BE block sync 성공률 | `AI BLOCK 판정` 대비 backend block 성공 비율 확인 |
| BE block sync 지연시간 | backend block 동기화 지연 확인 |

주의:

- `/ai/evaluate`의 `BLOCK` 결과는 BE block sync 대상으로 맞춘다.
- 대시보드는 AI 서버 custom metric `ai_defense_block_sync_total`, `ai_defense_block_sync_latency_seconds`를 읽어야 한다.
- `ai_defense_evaluate_total`에 `event_type` 라벨이 추가되면 AI 서버 관점 분리가 더 쉬워지지만, 현재 필수 선행 조건은 아니다.

---

## 9. 선택 항목

| 항목 | 목적 |
| --- | --- |
| FE browser -> AI 체감 지연 / 오류 | Faro 기준 UX 보조 지표 |

이 항목은 메인 KPI가 아니라 보조 참고 지표로 둔다.

---

## 10. 접이식 보조 섹션으로만 둘 것

| 항목 | 이유 |
| --- | --- |
| Precheck 요청량 | Turnstile 미사용 방향이라 메인 KPI 비중이 낮음 |
| Precheck pass/fail | 운영 핵심 패널 아님 |
| Precheck pass rate | 문제 생겼을 때만 확인하면 충분 |

의미:

- 평소 메인 화면에 두지 않는다.
- 이슈 생겼을 때만 펼쳐서 확인한다.
- 발표용 숫자나 핵심 KPI에는 쓰지 않는다.
- FE/AI 동시 정리 배포 전까지는 코드상 남아 있으므로 완전 삭제 대신 여기만 유지한다.

---

## 11. 모니터링으로 바로 받쳐줄 수 있는 항목

| 항목 | 가능 여부 | 메모 |
| --- | --- | --- |
| telemetry 수집 여부 | 가능 | stage별 유입량 추적 가능 |
| queue enter / seat stage 판정 흐름 | 가능 | `authz_adapter_decisions_total` 기준 |
| challenge 발동 및 verify 결과 | 가능 | start / verify 분리 가능 |
| authz -> AI 지연과 실패 | 가능 | adapter metric으로 확인 가능 |
| fail-open 발생 여부 | 가능 | 전용 metric 존재 |
| block 판정 이후 backend block sync 여부 | 가능 | AI 서버 custom metric으로 추적 가능 |
| Precision | 불가 | attack agent 로그 + audit 로그 필요 |
| FPR | 불가 | attack agent 로그 + audit 로그 필요 |
| 혼합 트래픽 비율별 성능 | 불가 | offline 결과표 필요 |
| 정상/공격 라벨 기준 정확도 | 불가 | offline 결과표 필요 |

즉 모니터링은 파이프라인 상태를 보여주지만,
품질 평가 지표를 완결해주지는 못한다.

---

## 12. 인프라팀에 바로 요청할 항목

### 12.1 즉시 반영 가능

- `authz_adapter_ai_defense_requests_total` 대신 `authz_adapter_ai_defense_calls_total`로 대시보드 쿼리 수정
- `authz_adapter_ai_defense_duration_seconds_bucket` 대신 `authz_adapter_ai_defense_latency_seconds` 기준으로 지연 패널 수정
- `스테이지별 수집` 패널을 `ai_defense_telemetry_ingest_total{stage}` 기준으로 교체
- `Challenge start 요청량` 패널 추가
- `Challenge verify 결과 분포` 패널 추가
- `VQA telemetry score 결과 분포` 패널 추가
- `Fail-open 건수/비율` 패널 추가
- `BE block sync` 관련 패널 추가

### 12.2 개선 사항

- `ai_defense_evaluate_total`에 `event_type` 라벨을 추가하면
  AI 서버 메트릭만으로 Queue/Seat 전용 분포를 직접 볼 수 있다.
- 다만 현재는 `authz_adapter_decisions_total`로 우선 분리 가능하므로
  필수 선행 조건은 아니다.

---

## 13. 권장 패널 구성

### 13.1 1행: 파이프라인 상단 KPI

- Telemetry ingest 수
- `/ai/evaluate` 판정 총량
- Challenge verify pass rate
- Authz -> AI error/timeout 비율
- Fail-open 비율
- BE block sync 성공률

### 13.2 2행: Telemetry / Evaluate

- stage별 telemetry ingest
- 전체 evaluate decision 분포
- Queue Enter 전용 판정 분포
- Seat Stage 전용 판정 분포

### 13.3 3행: Challenge / VQA

- Challenge start 요청량
- Challenge verify 결과 분포
- Challenge verify 통과율
- VQA telemetry score 결과 분포

### 13.4 4행: Authz / Fail-open

- authz check 요청량과 결과
- authz check 지연
- authz -> AI 호출 상태 분포
- authz -> AI 호출 지연
- fail-open 건수와 비율

### 13.5 5행: BE block sync

- BE block sync 요청 건수
- BE block sync 결과 분포
- BE block sync 성공률
- BE block sync 지연시간

### 13.6 접이식 보조 섹션

- Precheck 요청량
- Precheck pass/fail
- Precheck pass rate
- 로그 스트림

---

## 14. 최종 결론

AI 메인 대시보드는
`Telemetry`, `Evaluate`, `Challenge`, `Authz`, `Fail-open`, `BE block sync`
중심으로 재구성하는 것이 맞다.

운영자가 이 보드에서 얻어야 하는 것은
`지금 AI Defense 파이프라인이 어느 단계에서 어떤 결과를 내고 있으며, 어디서 실패하거나 비정상으로 치우치고 있는가`다.

정리하면:

1. 실시간 폴링 모니터링은 Queue/Backend 보드로 분리한다.
2. AI 메인 보드는 파이프라인 중심으로 재구성한다.
3. `Precheck`는 당분간 접이식 보조 섹션으로만 유지한다.
4. Discord는 거의 정리된 상태로 보고, 현재 남은 설계 중심축은 Grafana에 둔다.
