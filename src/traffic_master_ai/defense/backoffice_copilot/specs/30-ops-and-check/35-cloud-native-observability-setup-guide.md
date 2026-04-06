# Traffic Master AI Defense - 운영 최소 관측/알림 가이드 (Infra 팀 전달용)

## 1. 문서 목적

이 문서는 Infra 팀이 운영용 관측 화면과 운영 알림 채널을
최소 복잡도로 구성할 수 있도록
Grafana와 Discord의 역할, 데이터 소스, 필수 항목만 고정한다.

한 줄 요약:

- Grafana = 운영 상태를 보는 read-only 화면
- Discord = 후속조치가 필요한 결과만 받는 알림 채널

이번 문서는 "많이 보여주는 관측 시스템"이 아니라
"운영자가 지금 무엇을 봐야 하고 무엇만 알림 받아야 하는가"를 최소 범위로 정리한 문서다.

---

## 2. 먼저 고정할 질문

Grafana 방향이 흔들리는 가장 큰 이유는
"이 보드로 운영자가 결국 무엇을 판단해야 하는가"가 아직 섞여 있기 때문이다.

운영 보드가 먼저 답해야 할 질문은 아래 3개다.

1. 지금 Runtime 트래픽 규모와 방어 동작은 정상 범위인가
2. 지금 방어 결과가 평소와 다르게 치우치고 있는가
3. 지금 어떤 `match` 또는 `reason_code`가 운영자가 볼 정도로 튀고 있는가

즉 Grafana의 주 목적은
"서비스가 살아 있나"를 넘어서
"방어 Runtime이 지금 어떤 판단을 하고 있는가"를 빠르게 보는 데 있다.

---

## 3. 역할 분리 원칙

### 3.1 Grafana

- 목적: 운영자가 지금 Runtime이 어떤 상태인지 본다.
- 성격: 상황판, 추세 확인, read-only
- 주 데이터 소스: ClickHouse
- 판단 질문:
  - 지금 요청량이 정상 범위인가
  - 어떤 tier/action으로 분포하고 있는가
  - block/throttle/challenge가 평소와 달라졌는가
  - 어떤 reason_code가 상위로 올라오는가

### 3.2 Discord

- 목적: 운영자가 지금 후속조치가 필요한 post-review 결과를 바로 받는다.
- 성격: 알림, 운영 전달, 후속조치 트리거
- 주 데이터 소스: PostgreSQL `post_review_runs`, `post_review_session_results`
- 판단 질문:
  - 어떤 `match_id` / 시간 구간에서 suspicious 결과가 나왔는가
  - 어떤 세션을 우선 봐야 하는가
  - backend 전달 실패가 있었는가

### 3.3 분리 원칙

1. Grafana는 상태와 추세만 본다.
2. Discord는 조치가 필요한 결과만 보낸다.
3. ClickHouse 지표 변동만으로 Discord를 울리지 않는다.
4. PostgreSQL post-review 결과가 Discord 본문 authority다.
5. ClickHouse 데이터는 Discord 본문이 아니라 보강 정보로만 붙인다.

---

## 4. 현재 보드 진단

현재 Grafana JSON `[AI] 텔레메트리 & 봇 탐지 현황` 보드는
이미 운영에 필요한 재료를 일부 갖고 있지만,
역할이 3개 섞여 있다.

현재 보드에 섞여 있는 축:

1. 서비스 헬스
   - Istio 성공률
   - 요청률
   - 응답시간
   - gRPC 성공률
   - 실행 인스턴스
2. 런타임 이벤트 카운터
   - telemetry ingest
   - precheck
   - challenge
   - evaluate decision
3. 로그 탐색
   - Loki 로그 스트림

현재 보드의 장점:

- 서비스 장애나 지연 이상은 빨리 볼 수 있다.
- ext_authz / gRPC 계층 상태도 같이 확인할 수 있다.
- 현재 메트릭이 이미 Prometheus에 올라와 있어 진입 비용이 낮다.

현재 보드의 한계:

- 운영자가 "지금 방어가 어떻게 작동하고 있나"를 한눈에 보기 어렵다.
- 서비스 건강도와 방어 판단 결과가 한 보드에 섞여 signal이 약해진다.
- `tier`, `reason_code`, `match` 같은 운영 판단 축이 약하다.
- Loki 로그까지 첫 화면에 들어가 보드 목적이 더 흐려진다.

따라서 현재 보드는 폐기보다 분리가 맞다.

- 현재 보드의 강한 부분은 `서비스 헬스 보드`로 유지
- 운영자가 실제로 보는 새 보드는 `운영 상태판`으로 별도 구성

---

## 5. Grafana 작업 방향성

### 5.1 북극성

Grafana 운영 보드의 북극성은 아래 한 문장으로 잡는 것이 맞다.

`운영자가 지금 방어 Runtime의 상태 변화와 이상 징후를 1분 안에 파악하는 보드`

이 기준이면
Grafana는 deep investigation 도구가 아니라
현재 상태와 추세를 빠르게 보는 상황판이 된다.

### 5.2 보드를 2개로 분리

가장 실용적인 방향은 Grafana를 아래 2개 보드로 분리하는 것이다.

1. `AI Runtime Health`
   - 현재 JSON 보드를 기반으로 유지
   - Prometheus / Loki 중심
   - 목적: 서비스 장애, 지연, 인스턴스 문제 확인
2. `AI Defense Runtime Overview`
   - 새 운영 보드
   - ClickHouse 중심
   - 목적: RPM, tier/action 분포, block/throttle/challenge 변화, reason_code, match 요약 확인

즉 지금 보드는 잘못된 것이 아니라
`운영 상태판`이 아니라 `서비스 헬스 보드`로 보는 것이 맞다.

### 5.3 현재 보드에서 유지할 것

현재 JSON 보드에서 아래는 유지 가치가 높다.

- AI 서비스 성공률
- AI 서비스 요청률
- AI 서비스 응답시간 P95
- gRPC 성공률
- 인증 검사 지연시간
- 실행 인스턴스

이 항목들은 없어도 되는 것이 아니라
서비스 헬스 보드에 있어야 하는 항목들이다.

### 5.4 현재 보드에서 약화하거나 분리할 것

아래는 운영 상태판 기준으로는 약화 또는 분리가 맞다.

- Loki 로그 스트림
- 엔드포인트 분포
- telemetry ingest / precheck / challenge를 한 패널에 섞은 요청 추이
- 한 보드 안에서 서비스 헬스와 봇 탐지 분포를 같이 보여주는 구조

로그는 triage 시점에 들어가면 충분하고,
기본 상황판의 첫 화면에 둘 필요는 없다.

---

## 6. V1 최소 구성

### 6.1 Grafana 최소 대시보드

운영 상태판은 대시보드 1개만 두고,
아래 패널만 기본 화면으로 둔다.

| 패널 | 목적 | 주 데이터 소스 | 비고 |
| --- | --- | --- | --- |
| 요청량 RPM | 현재 트래픽 규모 확인 | ClickHouse | 기본 time-series |
| tier 분포 | T0/T1/T2/T3 쏠림 확인 | ClickHouse | pie 또는 stacked bar |
| action 분포 | NONE / THROTTLE / CHALLENGE / BLOCK 분포 확인 | ClickHouse | pie 또는 stacked bar |
| block rate | 차단 비율 급변 여부 확인 | ClickHouse | percent stat + trend |
| throttle delay p50/p90 | throttle 체감 지연 확인 | ClickHouse | p50, p90 2개 선이면 충분 |
| challenge pass/fail rate | challenge 품질 저하 여부 확인 | ClickHouse | pass/fail 비율만 |
| reason_code breakdown | 상위 reason_code 확인 | ClickHouse | top N만 표시 |
| match 단위 요약 | 최근 이상 match 후보 확인 | ClickHouse | 최근 window 기준 table |

메모:

- `post-review` 결과 패널은 운영 상태판 기본 항목으로 두지 않는다.
- 꼭 필요하면 보조 row에 최근 `suspicious_count` 또는 `backend_delivery_status=FAILED` 건수 정도만 추가한다.
- 기본 화면은 "Runtime 상태 확인"에 집중하고, post-review 상세는 Discord 알림에서 시작한다.

### 6.2 Grafana에서 하지 않을 것

아래는 V1 최소안에서 제외한다.

- PostgreSQL `post_review_*`를 대량 조인해서 복잡한 통합 대시보드 만들기
- 세션 단위 deep drill-down 보드를 여러 장 운영하기
- Discord 알림 내용을 Grafana 패널로 그대로 중복 노출하기
- RPM/block rate 같은 지표 변동만으로 별도 운영 알림 체계 만들기

즉 Grafana 운영 상태판은
"지금 Runtime이 어떤 상태인가"만 빠르게 보이면 된다.

---

## 7. Discord 최소 알림 정책

Discord는 알림 종류를 최소 2개로 제한한다.

### 7.1 알림 1: Suspicious 결과 발생

- 알림 이름: `POST_REVIEW_SUSPICIOUS`
- 트리거:
  - `post_review_runs.status IN ('SUCCESS', 'PARTIAL_SUCCESS')`
  - `post_review_runs.suspicious_count > 0`
- 의미:
  - 운영자가 후속 검토하거나 전달해야 할 suspicious 결과가 생겼다.

필수 본문:

- `match_id`
- `window_start_ms`
- `window_end_ms`
- `candidate_count`
- `suspicious_count`
- `summary_text_json`
- suspicious 상위 N개 세션
- 각 세션의 `evidence_summary`
- 각 세션의 `backend_delivery_status`

권장 보강 정보:

- 해당 window의 block rate
- 해당 window의 throttle p90
- suspicious session의 최근 action
- suspicious session의 최근 tier

보강 정보 소스:

- ClickHouse
- session 보강 시 기본 조회 기준은 `session_id + 시간 구간`

운영 원칙:

- 상위 N은 `3`으로 제한한다.
- suspicious가 `0`이면 보내지 않는다.
- digest성 요약 메시지는 보내지 않는다.

### 7.2 알림 2: Backend 전달 실패

- 알림 이름: `POST_REVIEW_DELIVERY_FAILED`
- 트리거:
  - `post_review_session_results.review_result = 'SUSPICIOUS'`
  - `post_review_session_results.backend_delivery_status = 'FAILED'`
- 의미:
  - suspicious 결과는 나왔지만 downstream/backend 전달이 실패했다.

필수 본문:

- `match_id`
- `window_start_ms`
- `window_end_ms`
- 실패한 `session_id` 목록
- 각 세션의 `evidence_summary`
- `backend_delivery_status='FAILED'`

권장 보강 정보:

- 해당 window의 block rate
- 해당 window의 throttle p90
- 실패 세션의 최근 action / tier

운영 원칙:

- 이 알림은 retry 또는 수동 전달 판단용이다.
- 동일 세션에 대해 중복 발송이 필요하면 dedupe 기준은 `match_id + session_id + backend_delivery_status`로 둔다.

### 7.3 Discord에서 하지 않을 것

아래는 V1 최소안에서 제외한다.

- RPM spike 알림
- block rate spike 알림
- challenge fail rate 알림
- reason_code top N 변경 알림
- suspicious_count = 0 인 정상 완료 알림
- 주기적 summary digest 알림

즉 Discord는 "지금 누가 봐야 하는 결과가 생겼는가"만 보낸다.

---

## 8. Discord 본문 권장 포맷

Discord 메시지는 길게 쓰지 말고
운영자가 바로 조치 대상을 파악할 수 있는 형태로 제한한다.

권장 순서:

1. 헤더
   - 알림 종류
   - `match_id`
   - `window_start_ms ~ window_end_ms`
2. 요약
   - `candidate_count`
   - `suspicious_count`
   - `summary_text_json`
3. 상위 suspicious 세션
   - `session_id`
   - `evidence_summary`
   - `backend_delivery_status`
   - 최근 `action`, 최근 `tier`
4. 보강 지표
   - block rate
   - throttle p90

메모:

- Discord 본문은 운영 전달용이므로 장문 분석 리포트로 만들지 않는다.
- 자세한 추적은 별도 조회 경로에서 하고, Discord는 triage 시작점으로만 쓴다.

---

## 9. 구현 기준

### 9.1 데이터 authority

- 서비스 헬스 보드 authority: Prometheus / Loki
- 운영 상태판 authority: ClickHouse
- Discord authority: PostgreSQL `post_review_*`
- Discord enrichment: ClickHouse

### 9.2 조인 기준

- post-review 결과 식별: `match_id`
- suspicious session 보강 조회: `session_id + window_start_ms + window_end_ms`

메모:

- raw runtime observability는 현재 기준 `session_id + 시간 구간` 조회가 가장 안전하다.
- Discord 본문을 만들 때 ClickHouse 보강 정보가 빠져도 알림 자체는 보내야 한다.

### 9.3 운영 우선순위

Infra 팀은 아래 순서로 구현하면 된다.

1. 기존 Prometheus/Loki 보드를 `서비스 헬스 보드`로 정리
2. ClickHouse 기반 `운영 상태판` 1개 신설
3. Discord webhook 2종 알림
4. Discord용 ClickHouse 보강 조회

---

## 10. 최종 요청 사항

Infra 팀 전달 기준 최소 요구사항은 아래다.

1. 기존 `[AI] 텔레메트리 & 봇 탐지 현황` 보드는 서비스 헬스 보드로 재정의한다.
2. 운영자가 실제로 보는 새 Grafana 보드는 ClickHouse 기반 Runtime 상태판으로 분리한다.
3. 새 Grafana 기본 패널은 RPM, tier, action, block rate, throttle p50/p90, challenge pass/fail, reason_code, match 요약까지만 둔다.
4. Discord는 `POST_REVIEW_SUSPICIOUS`, `POST_REVIEW_DELIVERY_FAILED` 2종만 보낸다.
5. Discord 본문 authority는 PostgreSQL `post_review_*`로 고정한다.
6. ClickHouse 지표는 Discord 트리거가 아니라 보강 정보로만 사용한다.

이 범위를 넘는 drill-down, 통합 보드, 지표성 알림 증설은
운영 실제 사용 후 필요성이 확인된 다음 단계에서만 추가한다.
