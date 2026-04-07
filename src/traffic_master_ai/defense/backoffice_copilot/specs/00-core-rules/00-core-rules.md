## 1. 문서 목적

이 문서는 Backoffice Copilot 사후 판단 시스템의 최상위 원칙을 정의한다.

이 문서의 목적은 다음과 같다.

- 서비스의 정체성을 고정한다.
- 하위 문서가 따라야 하는 불변 규칙을 정의한다.
- 구현 과정에서 임의 해석을 막는다.
- 문서 간 충돌 시 최우선 기준이 된다.

이 문서는 서비스의 헌법 역할을 하며, 하위 문서는 이 문서를 위반할 수 없다.

관련 문서:

- `01-service-overview.md`: 서비스 범위/사용자/입출력/처리 흐름
- `10-post-review-rules.md`: 후보 추출/세션 분석/LLM/backend 전달 도메인 규칙
- `11-review-output-rules.md`: PostgreSQL 정식 출력 및 export 파생 규칙
- `21-data-contract.md`: DTO/DB 컬럼 계약
- `30-ops-and-checks.md`: 운영/검증 체크 규칙
- `31-observability-merge-strategy.md`: Runtime observability와 Backoffice 결과물의 외부 소비 병합 전략
- `../../d0_mvp/ssot_specs/L2/obs_opt/defense_observability_ssot.yaml`: Runtime 관측 이벤트/KPI/warehouse 권위 문서

---

## 2. 서비스 정의

Backoffice Copilot은 실시간 방어 엔진이 아니다.

Backoffice Copilot은 Runtime이 정상 통과시킨 세션 중,
지정 시간 구간 종료 후 다시 볼 가치가 있는 세션을
`session_id` 기준으로 재분석하는 사후 판단 시스템이다.

이 시스템은 다음을 수행한다.

- 후보 세션 추출
- 세션 흐름 분석
- 세션별 정상 / 악성 의심 레이블링
- 근거 요약 생성
- 시간 구간 전체 요약 생성
- PostgreSQL 정식 저장
- 필요 시 export 후속 생성

이 시스템은 다음을 수행하지 않는다.

- 실시간 차단/허용 판정
- 정책 자동 반영
- 계정/토큰 제재 집행
- Discord/Grafana 실제 연동
- 백오피스 UI 제공
- 관리자 조회 API 제공 또는 사용

---

## 3. 사후 판단 대상 정의

사후 판단 대상은 아래 조건을 모두 만족하는 세션이다.

1. `session_id`가 존재한다.
2. 지정 시간 구간 내 활동 기록이 존재한다.
3. Runtime에서 최종 차단되지 않았다.
4. Runtime 중 T1 또는 T2 흔적이 존재한다.

세부 후보 추출 규칙과 hard filter는 `10-post-review-rules.md`를 따른다.

사후 판단 대상이 아닌 세션은 아래와 같다.

1. Runtime에서 이미 T3 또는 BLOCK 처리된 세션
2. `session_id`가 없어 세션 흐름을 추적할 수 없는 요청
3. 의심 흔적이 거의 없는 일반 정상 세션

---

## 4. 입력 데이터 원칙

입력은 Runtime이 남긴 공식 감사 로그를 사용한다.

입력 우선순위는 아래와 같다.

1. `defense_audit_events.jsonl`
2. `decision_audit.jsonl`

입력 데이터의 공식 해석 규칙은 아래와 같다.

- row loader는 원시 row를 읽는 책임만 가진다.
- `flowState`는 공식 해석 필드다.
- `terminalReason`은 공식 종료 해석 필드다.
- `terminalReason`은 단독으로 해석하지 않고 `flowState`, `reasonCode`와 함께 해석한다.
- `flowState`, `terminalReason`, `reasonCode`, `latest_*` 해석은 semantic mapping 계층 책임이다.
- `defense_audit_events`는 집계 결과가 아니라 이벤트 1건 = row 1건 구조다.
- `decision_audit`는 원본 감사 로그다.
- 사후 판단 파이프라인은 로그 기반으로 동작한다.

---

## 5. 출력 원칙

정식 출력은 아래 PostgreSQL 2개 테이블 저장이다.

1. `post_review_runs`
2. `post_review_session_results`

export 파일은 DB 저장 이후 생성되는 후속 산출물이며 필요할 때만 만든다.

1. `summary.json`
2. `suspicious_sessions.jsonl`
3. `suspicious_sessions.csv`

출력의 최소 핵심 필드는 아래와 같다.

### 세션 단위

- `session_id`
- `review_result`
- `evidence_summary`

### 시간 구간 단위

- `summary_text`
- `suspicious_sessions[]`

허용되는 세션 레이블은 아래 2개뿐이다.

- `NORMAL`
- `SUSPICIOUS`

다른 레이블은 허용하지 않는다.

금지 레이블 예:

- `REVIEW_NEEDED`
- `UNSURE`
- `MALICIOUS`
- `HIGH_RISK`

---

## 6. 시스템 책임 분리

### Runtime 책임

- 실시간 상태 추적
- 실시간 티어 계산
- allow/throttle/require_s3/block 결정
- 감사 로그 기록

### Backoffice Copilot 책임

- 로그 기반 후보 세션 추출
- 로그 기반 세션 흐름 분석
- 정상 / 악성 의심 레이블링
- evidence_summary 생성
- 시간 구간 요약 생성
- PostgreSQL 정식 저장
- `Backend request DTO` 생성
- backend adapter 경계 처리
- 응답 기반 `backend_delivery_status` 갱신
- 필요 시 export 후속 생성

### 인프라 팀 책임

- 외부 backend 서버/API 구현
- Discord 연결
- Grafana 연결
- 결과 payload 소비 및 노출

---

## 7. LLM 사용 원칙

LLM은 아래 역할만 수행한다.

1. 세션별 `review_result` 생성
2. 세션별 `evidence_summary` 생성
3. 시간 구간 3줄 요약 생성

LLM은 아래를 수행하면 안 된다.

1. Runtime의 실시간 판단 재정의
2. 입력에 없는 사실 생성
3. 제재 집행 결정
4. 정책 자동 반영 결정

LLM이 실패해도 시스템은 최소 결과를 남겨야 한다.

---

## 8. Fallback 원칙

LLM 실패 시에도 아래는 반드시 수행 가능해야 한다.

- 후보 세션 추출
- 세션 흐름 재구성
- 기본 통계 계산
- PostgreSQL 정식 저장

LLM 실패 시 대체 원칙은 아래와 같다.

- `review_result`는 규칙 기반 fallback 사용
- `evidence_summary`는 템플릿 문장 사용
- `summary_text`는 템플릿 3줄 사용

즉, LLM 실패는 전체 파이프라인 실패 조건이 아니다.

---

## 9. 병렬 처리 원칙

그래프 전체는 직렬 흐름을 유지한다.

허용되는 병렬화는 노드 내부에 한정한다.

허용:

- 로그 입력 수집 병렬 처리
- 세션 분석 노드 내부 세션별 병렬 처리
- 사후 판단 노드 내부 세션별 병렬 LLM 호출

비허용:

- 노드 간 임의 병렬 분기
- 요약 생성 이전의 결과 조립 분산
- 레이블링 규칙 없는 동적 노드 추가

---

## 10. 구현 금지 사항

아래는 금지한다.

1. 노드 수 임의 변경
2. 새로운 review_result 값 추가
3. Discord/Grafana 실제 연동 구현을 AI 파트 범위에 포함하는 것
4. 계정/토큰 제재 로직 구현
5. 입력에 없는 정보를 evidence_summary에 생성
6. suspicious가 아닌 세션을 suspicious 파일에 저장
7. 관리자 조회 API 의존 구조를 다시 추가하는 것

---

## 11. 문서 권위 규칙

이 문서는 최상위 문서다.

하위 문서는 이 문서를 위반할 수 없다.

충돌 시 수정 우선순위는 아래와 같다.

1. 하위 문서를 수정한다.
2. 상위 문서를 바꾸는 것은 제품 방향 변경으로 간주한다.

---

## 12. 변경 허용 범위

이 문서를 변경할 수 있는 경우는 아래뿐이다.

- 서비스 정체성 변경
- 사후 판단 대상 정의 변경
- 입력 로그 구조 변경
- 출력 파일 구조 변경
- 허용 레이블 변경
- Runtime/Backoffice/Infra 책임 분리 변경
- LLM 역할 범위 변경

세부 구현 변경은 하위 문서에서 처리한다.
