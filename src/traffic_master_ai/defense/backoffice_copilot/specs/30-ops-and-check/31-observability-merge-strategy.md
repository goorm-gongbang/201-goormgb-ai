## 1. 문서 목적

이 문서는 기존 `defense_observability_ssot.yaml`의 관측 데이터 정의를
Backoffice Copilot 결과물과 병합해,

- 내부 전용 관리자 대시보드 없이
- `defense_audit_events` 계열 관측 테이블과
- `post_review_runs` / `post_review_session_results` 결과 테이블을
- Discord, Grafana, 외부 운영 파이프라인이 함께 소비하는 구조

로 정리하는 방법을 정의한다.

이 문서는 “새 UI를 어떻게 만들 것인가”가 아니라
“어떤 데이터를 어떤 책임으로 병합해 외부 소비자에게 내보낼 것인가”를 다룬다.

관련 문서:

- `../00-core-rules/00-core-rules.md`: 최상위 원칙과 책임 분리
- `../01-service-overview/01-service-overview.md`: 서비스 범위, 사용자, 최종 산출물 사용 방식
- `../10-post-review-rules/10-post-review-rules.md`: 후보/분석/전달 도메인 규칙
- `../11-review-output-rules/11-review-output-rules.md`: 정식 출력과 export 파생 규칙
- `../21-data-contract/21-data-contract.md`: post-review 결과 필드/컬럼 계약
- `30-ops-and-checks.md`: 운영 검증 규칙
- `../../d0_mvp/ssot_specs/L2/obs_opt/defense_observability_ssot.yaml`: Runtime observability 증거/warehouse/KPI 권위 문서
- `../../d0_mvp/ssot_specs/L2/obs_opt/defense_admin_console_ssot.yaml`: 기존 콘솔/조회 질의 예시 문서

---

## 2. 배경과 결정

기존 observability 문서는 near-real-time 관리자 콘솔을 전제로
warehouse 스키마, KPI, drill-down 질의, 위젯 예시를 함께 정의했다.

하지만 현재 방향은 아래와 같다.

- 우리 팀이 자체 관리자 대시보드를 직접 만들 가능성은 낮다.
- 대신 Runtime 관측 데이터와 Backoffice Copilot 사후판단 결과를
  외부 소비자(Discord, Grafana, 운영 배치)에서 함께 보는 방향으로 간다.
- 따라서 observability 문서의 “UI/view 계약”은 약화시키고,
  “데이터 테이블 / KPI / 외부 소비 규칙”을 Backoffice Copilot 문맥으로 병합한다.

핵심 결정:

1. Runtime 관측의 원본 증거 SSOT는 계속 `decision_audit`이다.
2. near-real-time 운영 조회의 기본 테이블은 `defense_audit_events`다.
3. 사후판단의 정식 출력은 계속 `post_review_runs`, `post_review_session_results`다.
4. Discord/Grafana는 내부 콘솔 대체물이 아니라 외부 소비자다.
5. 병합의 목표는 “대시보드 제품 개발”이 아니라 “공통 데이터 계약 정리”다.

---

## 3. 병합 후 전체 구조

병합 후 운영 데이터 구조는 아래 3층으로 본다.

### 3.1 Runtime 관측층

- 원본: `decision_audit`
- 적재 결과: `defense_audit_events`
- 역할:
  - 실시간 방어가 어떤 이벤트를 냈는지 기록
  - tier/action/block/challenge/error KPI 집계
  - session/trace drill-down 근거 제공

### 3.2 Post-review 결과층

- 정식 저장:
  - `post_review_runs`
  - `post_review_session_results`
- 역할:
  - 시간 구간 단위 사후판단 결과 저장
  - suspicious 세션, evidence, 요약 3줄, 전달 상태 저장

### 3.3 외부 소비층

- Discord
- Grafana
- 운영 배치 / 알림 / 후속 처리기

역할:
- Runtime 관측은 `defense_audit_events`에서 읽는다.
- 사후판단 결과는 `post_review_*`에서 읽는다.
- 필요 시 둘을 `session_id + 시간 구간` 기준으로 조합한다.

---

## 4. 문서 병합 원칙

### 4.1 observability 문서에서 유지할 것

`defense_observability_ssot.yaml`에서 아래는 계속 권위로 유지한다.

- `decision_audit` 최소 스키마
- 허용 `eventType`
- PII 금지 규칙
- dedup-aware 집계 규칙
- `defense_audit_events` warehouse 테이블 개념
- KPI 정의
- alert 조건 정의

즉, observability 문서는 여전히 Runtime 관측 데이터의
“증거/이벤트/집계 규칙” 권위 문서다.

### 4.2 observability 문서에서 약화할 것

아래는 더 이상 제품 요구사항의 중심으로 두지 않는다.

- 내부 Admin Console 화면 구성
- 위젯 배치
- UI refresh 주기
- 콘솔 페이지 정보 구조
- 내부 drill-down UX

이 항목들은 더 이상 “반드시 구현해야 하는 제품 계약”이 아니라
“외부 소비자가 참고할 수 있는 질의 예시” 수준으로 낮춘다.

### 4.3 Backoffice Copilot 문서에 새로 고정할 것

Backoffice Copilot 문맥에서 아래를 고정한다.

- Runtime 관측 테이블과 post-review 결과 테이블의 병행 사용 원칙
- Discord/Grafana가 consume해야 하는 우선 데이터 소스
- 어떤 지표는 runtime warehouse에서 읽고,
  어떤 결과는 post-review 테이블에서 읽는지
- 두 계층을 조합할 때의 조인 기준
- export 파일은 계속 후속 산출물이라는 원칙

---

## 5. 병합 후 데이터 소스 우선순위

### 5.1 Runtime 관측/운영 상태

우선 데이터 소스:

1. `defense_audit_events`
2. 부족 시 `decision_audit`

사용 용도:

- RPM
- tier 분포
- action 분포
- block rate
- throttle delay
- challenge pass/fail
- reasonCode breakdown
- trace/session drill-down

### 5.2 사후판단/운영 후속조치

우선 데이터 소스:

1. `post_review_runs`
2. `post_review_session_results`
3. 필요 시 `summary.json`, `suspicious_sessions.*`

사용 용도:

- 시간 구간 요약
- suspicious 세션 목록
- evidence_summary
- backend 전달 상태
- 운영자 후속 검토
- Discord 알림 payload

### 5.3 결론

Runtime 관측은 `defense_audit_events`가 우선이고,
사후판단 결과는 `post_review_*`가 우선이다.

두 계층은 서로 대체 관계가 아니라 보완 관계다.

---

## 6. 외부 소비자별 병합 방식

## 6.1 Grafana

Grafana는 아래 2개 데이터 영역을 분리해서 본다.

### A. Runtime 패널

기본 소스: `defense_audit_events`

대표 패널:

- 요청량 RPM
- tier 분포
- action 분포
- throttle applied rate
- throttle delay p50/p90
- block rate
- challenge pass/fail rate
- error breakdown

이 패널들은 기존 observability KPI 정의를 그대로 재사용한다.

### B. Post-review 패널

기본 소스:

- `post_review_runs`
- `post_review_session_results`

대표 패널:

- 시간 구간별 suspicious_count 추이
- 최근 run 상태(`SUCCESS`/`PARTIAL_SUCCESS`/`FAILED`)
- 최근 suspicious 세션 수
- backend_delivery_status 분포
- evidence_summary 샘플

### C. Grafana에서의 병합 원칙

Grafana에서는 한 패널 안에서 모든 것을 섞기보다
Runtime 관측 패널과 Post-review 결과 패널을 분리한다.

권장 레이아웃:

1. 상단: Runtime health / anomaly KPI
2. 중단: Post-review suspicious 결과
3. 하단: session_id 기준 drill-down 링크 또는 탐색 패널

즉 Grafana는 “runtime 상태 모니터링”과
“사후판단 결과 확인”을 같은 보드에서 보되,
데이터 소스는 분리해서 쿼리한다.

## 6.2 Discord

Discord는 대시보드가 아니라 알림 채널이므로
`post_review_*` 중심으로 보내는 것이 맞다.

### Discord 알림 기본 소스

- `post_review_runs`
- `post_review_session_results`

### Discord 알림에 포함할 최소 항목

- `match_id`
- `window_start_ms`
- `window_end_ms`
- `candidate_count`
- `suspicious_count`
- `summary_text_json`
- suspicious 상위 N개
  - `session_id`
  - `review_result`
  - `evidence_summary`
  - `backend_delivery_status`

### Discord에서 Runtime 관측을 붙이는 방식

Discord 알림 본문은 post-review 결과 중심으로 만들고,
원하면 아래를 보강 필드로 붙인다.

- 해당 window 내 block rate
- 해당 window 내 throttle p90
- 해당 suspicious session의 최근 action/tier

이 보강 데이터는 `defense_audit_events`에서 읽어온다.

즉 Discord는 `post_review_*`를 본문으로 삼고,
`defense_audit_events`는 문맥 보강용으로만 붙인다.

---

## 7. 병합 시 조인 기준

Runtime warehouse와 post-review 결과는 저장 목적이 다르므로
조인 규칙을 명확히 고정해야 한다.

### 7.1 1차 조인 키

- `session_id`
- 시간 구간(`window_start_ms <= ts_ms <= window_end_ms`)

### 7.2 2차 보강 키

가능하면 아래를 추가 사용한다.

- `trace_id`
- `eventType`
- `serverDecision.policyVersion`
- payload 내부 `match_id` 또는 `gameId`가 존재하는 경우 그 필드

### 7.3 금지 사항

아래는 단독 조인 키로 쓰지 않는다.

- `reasonCode`
- `flowState`
- `review_result`
- `evidence_summary`

이 값들은 의미 필드이지 식별 키가 아니다.

### 7.4 실무 원칙

Post-review 결과에서 특정 suspicious session row를 보고
Runtime 상세 근거를 보고 싶으면,

1. `post_review_session_results.session_id`를 잡고
2. 상위 run의 `window_start_ms`, `window_end_ms`를 가져오고
3. `defense_audit_events`에서 동일 session_id + 시간 구간으로 조회한다.

이 방식이 기본 drill-down 계약이다.

---

## 8. 병합 후 산출물 사용 규칙

## 8.1 정식 저장소

정식 저장소는 계속 아래 2개다.

1. `post_review_runs`
2. `post_review_session_results`

이 원칙은 바꾸지 않는다.

## 8.2 observability warehouse

`defense_audit_events`는 정식 “사후판단 결과 저장소”가 아니라
Runtime 관측/운영 분석 저장소다.

즉:

- `defense_audit_events`는 Runtime의 사건 기록
- `post_review_*`는 사후판단의 결론

이다.

## 8.3 export 파일

아래는 계속 후속 산출물이다.

- `summary.json`
- `suspicious_sessions.jsonl`
- `suspicious_sessions.csv`

Discord/Grafana의 기본 소스로 export 파일을 쓰지 않는다.
항상 DB 또는 warehouse를 우선 사용한다.

---

## 9. 기존 observability 내용을 어떻게 흡수할 것인가

## 9.1 그대로 재사용할 항목

`defense_observability_ssot.yaml`에서 아래는 거의 그대로 재사용한다.

- `decision_audit.required_min_schema`
- `mandatory_events.required_audit_event_types`
- `aggregation_rules.dedup_policy`
- `near_real_time_pipeline.components.warehouse.schema`
- `kpis.overview.*`
- `kpis.integrity.*`
- `alerts.rules`

## 9.2 Backoffice Copilot 문맥으로 번역할 항목

아래는 “내부 콘솔” 언어 대신 “외부 소비” 언어로 바꿔 적는다.

- “Overview 위젯” -> “Grafana runtime 패널”
- “Session Drilldown” -> “session_id + 시간 구간 기반 탐색 쿼리”
- “External Links” -> “Discord/Grafana에서 참조 가능한 링크 또는 상세 조회 경로”
- “Admin Console 구현” -> “외부 소비 시스템이 참조하는 쿼리/테이블 계약”

## 9.3 폐기 또는 비중 축소할 항목

아래는 제품 요구사항 중심에서 내린다.

- 내부 관리자 페이지 컴포넌트 구성
- UI refresh 규칙
- 화면 단위 id/위젯 명세

이들은 구현 예시로만 남겨도 충분하다.

---

## 10. 권장 병합 문서 구조

문서 체계는 아래처럼 정리하는 것을 권장한다.

### 유지

- `defense_observability_ssot.yaml`
  - Runtime 관측 데이터/이벤트/KPI 권위 문서

- `00-core-rules.md`
  - Backoffice Copilot의 최상위 원칙

- `10-post-review-rules.md`
  - 도메인 규칙

- `11-review-output-rules.md`
  - 정식 출력 계약

### 추가 또는 흡수

- 본 문서
  - observability와 Backoffice 결과물의 병합 소비 전략

- 필요 시 후속 문서
  - `Discord payload contract`
  - `Grafana query pack`
  - `warehouse-to-post-review join recipes`

즉 observability는 “입력/관측 규칙”을 담당하고,
Backoffice 문서는 “결과 저장과 외부 소비 방식”을 담당하는 구조로 정리한다.

---

## 11. 운영 책임 분리

### Runtime 팀

- `decision_audit`와 `defense_audit_events` 품질 보장
- eventType, reasonCode, dedup 규칙 유지
- warehouse 적재 파이프라인 운영

### Backoffice Copilot 팀

- `post_review_runs`, `post_review_session_results` 품질 보장
- suspicious 결과 생성
- evidence_summary / summary_text 생성
- 운영 후속 소비를 위한 최소 DTO/export 제공

### 인프라/운영 팀

- Grafana dashboard 구성
- Discord 전송 파이프라인 구성
- warehouse와 PostgreSQL을 읽어 외부 채널에 노출

즉 Discord/Grafana 실제 구현은 여전히 인프라/운영 책임이다.
우리 쪽 문서는 그들이 안정적으로 consume할 수 있는 데이터 계약만 제공한다.

---

## 12. 최종 결론

앞으로는 observability 문서를 “내부 대시보드 설계서”로 쓰기보다
“Runtime 관측 데이터 계약서”로 축소해서 유지하는 편이 맞다.

그리고 Backoffice Copilot 문서 쪽에서 아래를 새 기준으로 잡는다.

1. Runtime 관측은 `defense_audit_events`를 사용한다.
2. 사후판단 결과는 `post_review_runs`, `post_review_session_results`를 사용한다.
3. Grafana는 두 계층을 나란히 보여주는 외부 소비자다.
4. Discord는 post-review 결과 중심 알림 채널이다.
5. 두 계층의 병합 기준은 `session_id + 시간 구간`이다.
6. export 파일은 계속 후속 산출물이며 1차 소비 소스가 아니다.

이 원칙으로 정리하면,
기존 observability 문서의 유효한 데이터 정의를 버리지 않으면서도
Backoffice Copilot 결과물과 외부 운영 채널을 한 구조로 묶을 수 있다.
