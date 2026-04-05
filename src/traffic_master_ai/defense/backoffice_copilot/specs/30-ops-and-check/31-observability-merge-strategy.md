# Observability Merge Strategy

## 1. 문서 목적

이 문서는 기존 `defense_observability_ssot.yaml`의 Runtime 관측 데이터 정의를
Backoffice Copilot 결과물과 병합해,

- `defense_audit_events` 계열 관측 테이블과
- `post_review_runs` / `post_review_session_results` 결과 테이블을
- Discord, Grafana, 외부 운영 파이프라인이 함께 소비하는 구조

로 정리하는 방법을 정의한다.

이 문서는 UI 설계 문서가 아니라
공통 데이터 계약과 외부 소비 방식을 다루는 문서다.

관련 문서:

- `../00-core-rules/00-core-rules.md`
- `../01-service-overview/01-service-overview.md`
- `../10-post-review-rules/10-post-review-rules.md`
- `../11-review-output-rules/11-review-output-rules.md`
- `../21-data-contract/21-data-contract.md`
- `30-ops-and-checks.md`
- `../../d0_mvp/ssot_specs/L2/obs_opt/defense_observability_ssot.yaml`
- `../../d0_mvp/ssot_specs/L2/obs_opt/defense_admin_console_ssot.yaml`

---

## 2. 현재 문서와 붙여준 문서의 차이

현재 저장소 문서와 방금 정리한 초안은 방향은 같지만 강조점이 조금 달랐다.

### 기존 저장소 문서의 장점

- observability 문서를 어떻게 축소하고 무엇을 유지할지 더 명확했다.
- Grafana/Discord를 외부 소비자로 분리하는 원칙이 더 선명했다.
- `session_id + 시간 구간` 조인 규칙, 책임 분리, 후속 문서 구조가 더 자세했다.
- `defense_audit_events`와 `post_review_*`를 대체 관계가 아닌 보완 관계로 설명한 점이 좋았다.

### 붙여준 문서의 장점

- 제목이 명확했다.
- 문장과 섹션 구조가 더 간결했다.
- 불필요한 완곡 표현이 적고 빠르게 읽혔다.
- “UI 설계 문서가 아니라 데이터 계약 문서”라는 포지션이 처음부터 잘 보였다.

### 이번 병합 원칙

이번 병합본은 아래 원칙을 따른다.

1. 제목과 문장 톤은 붙여준 문서의 간결함을 따른다.
2. 조인 기준, 책임 분리, 외부 소비 방식은 기존 저장소 문서의 상세함을 유지한다.
3. 내부 Admin Console 중심 표현은 줄이고, 외부 소비 계약 중심으로 재정리한다.
4. observability와 post-review 결과가 서로 보완 관계라는 설명은 유지한다.

---

## 3. 배경과 결정

기존 observability 문서는 near-real-time 관리자 콘솔을 전제로
warehouse 스키마, KPI, drill-down 질의, 위젯 예시를 함께 정의했다.

현재 방향은 다르다.

- 내부 관리자 대시보드 제품을 직접 만드는 것이 핵심 목표가 아니다.
- Runtime 관측 데이터와 Backoffice Copilot 결과를
  외부 소비자(Discord, Grafana, 운영 배치)가 함께 읽는 방향으로 간다.
- observability 문서의 UI/view 계약은 약화시키고,
  데이터 테이블, KPI, 외부 소비 규칙을 Backoffice Copilot 문맥으로 병합한다.

핵심 결정:

1. Runtime 관측의 원본 증거 SSOT는 계속 `decision_audit`이다.
2. near-real-time 운영 조회의 기본 테이블은 `defense_audit_events`다.
3. 사후판단의 정식 출력은 계속 `post_review_runs`, `post_review_session_results`다.
4. Discord/Grafana는 내부 콘솔 대체물이 아니라 외부 소비자다.
5. 병합의 목표는 대시보드 제품 개발이 아니라 공통 데이터 계약 정리다.

---

## 4. 병합 후 전체 구조

운영 데이터 구조는 아래 3층으로 본다.

### 4.1 Runtime 관측층

- 원본: `decision_audit`
- 적재 결과: `defense_audit_events`
- 역할:
  - 실시간 방어 이벤트 기록
  - tier/action/block/challenge/error KPI 집계
  - session/trace drill-down 근거 제공

### 4.2 Post-review 결과층

- 정식 저장:
  - `post_review_runs`
  - `post_review_session_results`
- 역할:
  - 시간 구간 단위 사후판단 결과 저장
  - suspicious 세션, evidence, 요약, 전달 상태 저장

### 4.3 외부 소비층

- Discord
- Grafana
- 운영 배치 / 알림 / 후속 처리기

역할:

- Runtime 관측은 `defense_audit_events`에서 읽는다.
- 사후판단 결과는 `post_review_*`에서 읽는다.
- 필요 시 둘을 `session_id + 시간 구간` 기준으로 조합한다.

---

## 5. 문서 병합 원칙

### 5.1 observability 문서에서 유지할 것

`defense_observability_ssot.yaml`에서 아래는 계속 권위로 유지한다.

- `decision_audit` 최소 스키마
- 허용 `eventType`
- PII 금지 규칙
- dedup-aware 집계 규칙
- `defense_audit_events` warehouse 테이블 개념
- KPI 정의
- alert 조건 정의

즉 observability 문서는 Runtime 관측 데이터의
증거, 이벤트, 집계 규칙 권위 문서다.

### 5.2 observability 문서에서 약화할 것

아래는 더 이상 제품 요구사항의 중심으로 두지 않는다.

- 내부 Admin Console 화면 구성
- 위젯 배치
- UI refresh 주기
- 콘솔 페이지 정보 구조
- 내부 drill-down UX

이 항목들은 구현 예시 또는 질의 예시 수준으로 낮춘다.

### 5.3 Backoffice Copilot 문서에 새로 고정할 것

Backoffice Copilot 문맥에서 아래를 고정한다.

- Runtime 관측 테이블과 post-review 결과 테이블의 병행 사용 원칙
- Discord/Grafana가 consume해야 하는 우선 데이터 소스
- 어떤 지표는 runtime warehouse에서 읽고 어떤 결과는 post-review 테이블에서 읽는지
- 두 계층을 조합할 때의 조인 기준
- export 파일은 후속 산출물이라는 원칙

---

## 6. 병합 후 데이터 소스 우선순위

### 6.1 Runtime 관측 / 운영 상태

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

### 6.2 사후판단 / 운영 후속조치

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

### 6.3 결론

- Runtime 관측은 `defense_audit_events`가 우선이다.
- 사후판단 결과는 `post_review_*`가 우선이다.
- 두 계층은 대체 관계가 아니라 보완 관계다.

---

## 7. 외부 소비자별 병합 방식

### 7.1 Grafana

Grafana는 2개 데이터 영역을 분리해서 본다.

#### Runtime 패널

- 기본 소스: `defense_audit_events`
- 대표 패널:
  - 요청량 RPM
  - tier 분포
  - action 분포
  - throttle applied rate
  - throttle delay p50/p90
  - block rate
  - challenge pass/fail rate
  - error breakdown

이 패널들은 기존 observability KPI 정의를 그대로 재사용한다.

#### Post-review 패널

- 기본 소스:
  - `post_review_runs`
  - `post_review_session_results`
- 대표 패널:
  - 시간 구간별 suspicious_count 추이
  - 최근 run 상태
  - 최근 suspicious 세션 수
  - backend_delivery_status 분포
  - evidence_summary 샘플

#### Grafana 병합 원칙

1. 상단: Runtime health / anomaly KPI
2. 중단: Post-review suspicious 결과
3. 하단: session_id 기준 탐색 또는 링크

즉 같은 보드에서 보되, 쿼리 소스는 분리한다.

### 7.2 Discord

Discord는 대시보드가 아니라 알림 채널이므로
`post_review_*` 중심으로 보낸다.

기본 소스:

- `post_review_runs`
- `post_review_session_results`

최소 포함 항목:

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

Runtime 관측 보강 필드:

- 해당 window 내 block rate
- 해당 window 내 throttle p90
- 해당 suspicious session의 최근 action/tier

이 보강 데이터는 `defense_audit_events`에서 읽는다.

즉 Discord는 `post_review_*`를 본문으로 삼고,
`defense_audit_events`는 문맥 보강용으로만 붙인다.

---

## 8. 병합 시 조인 기준

Runtime warehouse와 post-review 결과는 저장 목적이 다르므로
조인 규칙을 명확히 고정해야 한다.

### 8.1 1차 조인 키

- `session_id`
- 시간 구간
  - `window_start_ms <= ts_ms <= window_end_ms`

### 8.2 2차 보강 키

가능하면 아래를 추가 사용한다.

- `trace_id`
- `eventType`
- `serverDecision.policyVersion`
- payload 내부 `match_id` 또는 `gameId`

### 8.3 금지 사항

아래는 단독 조인 키로 쓰지 않는다.

- `reasonCode`
- `flowState`
- `review_result`
- `evidence_summary`

이 값들은 의미 필드이지 식별 키가 아니다.

### 8.4 실무 원칙

특정 suspicious session row에 대한 Runtime 상세 근거를 볼 때는:

1. `post_review_session_results.session_id` 확보
2. 상위 run의 `window_start_ms`, `window_end_ms` 조회
3. `defense_audit_events`에서 동일 `session_id + 시간 구간`으로 조회

이 방식이 기본 drill-down 계약이다.

---

## 9. 산출물 사용 규칙

### 9.1 정식 저장소

정식 저장소는 계속 아래 2개다.

1. `post_review_runs`
2. `post_review_session_results`

### 9.2 observability warehouse

`defense_audit_events`는 Runtime 관측 / 운영 분석 저장소이지
사후판단 결과 저장소가 아니다.

즉:

- `defense_audit_events` = Runtime의 사건 기록
- `post_review_*` = 사후판단의 결론

### 9.3 export 파일

- `summary.json`
- `suspicious_sessions.jsonl`
- `suspicious_sessions.csv`

이 파일들은 후속 산출물이며, Discord/Grafana의 기본 데이터 소스가 아니다.

---

## 10. 기존 observability 내용을 어떻게 흡수할 것인가

### 10.1 그대로 재사용

- `decision_audit.required_min_schema`
- `mandatory_events.required_audit_event_types`
- `aggregation_rules.dedup_policy`
- `near_real_time_pipeline.components.warehouse.schema`
- `kpis.overview.*`
- `kpis.integrity.*`
- `alerts.rules`

### 10.2 Backoffice Copilot 문맥으로 번역

- Overview 위젯 -> Grafana runtime 패널
- Session Drilldown -> `session_id + 시간 구간` 기반 탐색 쿼리
- External Links -> Discord/Grafana에서 참조 가능한 링크 또는 상세 조회 경로
- Admin Console 구현 -> 외부 소비 시스템이 참조하는 쿼리/테이블 계약

### 10.3 비중 축소

- 내부 관리자 페이지 컴포넌트 구성
- UI refresh 규칙
- 화면 단위 id/위젯 명세

---

## 11. 권장 문서 구조

유지:

- `defense_observability_ssot.yaml`
- `00-core-rules.md`
- `10-post-review-rules.md`
- `11-review-output-rules.md`

추가:

- 본 문서
- 필요 시:
  - `Discord payload contract`
  - `Grafana query pack`
  - `warehouse-to-post-review join recipes`

즉 observability는 입력/관측 규칙을,
Backoffice 문서는 결과 저장과 외부 소비 방식을 맡는다.

---

## 12. 운영 책임 분리

### Runtime 팀

- `decision_audit`, `defense_audit_events` 품질 보장
- eventType, reasonCode, dedup 규칙 유지
- warehouse 적재 파이프라인 운영

### Backoffice Copilot 팀

- `post_review_runs`, `post_review_session_results` 품질 보장
- suspicious 결과 생성
- evidence_summary / summary_text 생성
- 운영 후속 소비를 위한 최소 DTO/export 제공

### 인프라 / 운영 팀

- Grafana dashboard 구성
- Discord 전송 파이프라인 구성
- warehouse와 PostgreSQL을 읽어 외부 채널에 노출

즉 Discord/Grafana 실제 구현은 여전히 인프라/운영 책임이다.
우리 쪽 문서는 그들이 안정적으로 consume할 수 있는 데이터 계약만 제공한다.

---

## 13. 최종 결론

앞으로 observability 문서는 내부 대시보드 설계서가 아니라
Runtime 관측 데이터 계약서로 유지하는 편이 맞다.

Backoffice Copilot 문서 쪽에서는 아래를 새 기준으로 잡는다.

1. Runtime 관측은 `defense_audit_events`를 사용한다.
2. 사후판단 결과는 `post_review_runs`, `post_review_session_results`를 사용한다.
3. Grafana는 두 계층을 나란히 보여주는 외부 소비자다.
4. Discord는 post-review 결과 중심 알림 채널이다.
5. 두 계층의 병합 기준은 `session_id + 시간 구간`이다.
6. export 파일은 후속 산출물이며 1차 소비 소스가 아니다.

이 원칙으로 정리하면,
기존 observability 문서의 유효한 데이터 정의를 버리지 않으면서도
Backoffice Copilot 결과물과 외부 운영 채널을 한 구조로 묶을 수 있다.
