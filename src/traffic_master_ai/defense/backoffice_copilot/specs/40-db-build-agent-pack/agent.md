# DB Build AGENT.md

## 1. 목적

이 문서는 방어 AI 서비스의 DB 구축 작업을 수행하는 coding agent를 위한
최상위 컨텍스트 파일이다.

이 문서의 역할은 세 가지다.

1. 지금 이 작업의 목표 구조를 짧고 분명하게 고정한다.
2. agent가 어떤 순서로 문서와 코드를 읽어야 하는지 안내한다.
3. 과도한 자율성, 오버엔지니어링, 범위 이탈을 막는 작업 규칙을 제공한다.

이 문서는 모든 세부 사항을 다 담는 설명서가 아니다.  
보편적으로 반복 적용되는 핵심 규칙만 담고, 상세 내용은 링크된 원본 문서를 필요할 때만 읽게 한다.

---

## 2. 현재 작업의 북극성

이 작업의 목표 지향 문서는 아래다.

- [32-storage-architecture.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md)

이 문서를 기준으로 현재 DB 구축 작업의 북극성은 아래와 같다.

- Runtime observability는 `ClickHouse` 중심으로 정리한다.
- 정책변경/롤아웃은 `PostgreSQL control plane + Redis runtime projection`으로 정리한다.
- Backoffice Copilot 최종 결과는 `PostgreSQL` 중심으로 정리한다.
- `Redis / S3 / ClickHouse / PostgreSQL`의 책임을 섞지 않는다.

현재 코드와 목표 구조의 차이는 아래 문서로 본다.

- [33-docs-vs-current-code-gap-analysis.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/33-docs-vs-current-code-gap-analysis.md)

외부 소비 구조는 아래 문서로 본다.

- [31-observability-merge-strategy.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/31-observability-merge-strategy.md)

---

## 3. 하네스 3요소

이 작업에서는 아래 3요소를 하네스로 본다.

### 3.1 컨텍스트 파일

이 문서가 그 역할을 한다.

원칙:

- 짧고 반복 적용되는 핵심 규칙만 둔다.
- 상세 내용은 원본 SSOT와 코드로 링크한다.
- agent가 실수할 때마다 규칙을 한 줄씩 추가하며 점진적으로 고도화한다.

### 3.2 자동 강제 시스템

agent에게 “잘해라”라고 말하는 대신,
기계적인 규칙과 검증으로 결과를 강제한다.

이 저장소에서 자동 강제 시스템은 아래를 뜻한다.

- 타입/스키마/테스트로 계약을 잠근다.
- lint / type check / unit test / integration test가 있으면 반드시 통과 기준으로 쓴다.
- 실패는 조용히 덮지 않고 명시적으로 드러낸다.
- 검증이 실패하면 agent가 스스로 원인을 고치고 다시 시도한다.

핵심 원칙:

- 성공은 짧게 보고한다.
- 실패는 원인과 맥락을 크게 드러낸다.
- 빨간 불이 켜진 상태를 “완료”로 포장하지 않는다.

### 3.3 가비지 컬렉션

AI가 만든 나쁜 패턴과 중복 규칙, 사용하지 않는 산출물을 정리하는 절차다.

이 저장소에서 뜻하는 바는 아래와 같다.

- 같은 의미의 문서를 여러 곳에 복제하지 않는다.
- 오버엔지니어링된 필드, 쓰지 않는 테이블, 쓸모없는 abstraction을 남기지 않는다.
- 나쁜 패턴을 발견하면 다음 규칙이나 테스트로 편입한다.
- 시간이 지날수록 같은 실수를 다시 못 하게 문서와 테스트를 강화한다.

즉:

- 컨텍스트 파일은 방향을 준다.
- 자동 강제 시스템은 경계를 지킨다.
- 가비지 컬렉션은 품질 저하를 계속 청소한다.

---

## 4. Source of Truth 우선순위

항상 아래 순서로 판단한다.

1. [32-storage-architecture.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md)
2. 직접 관련된 SSOT 문서
3. 이 `agent.md`
4. 현재 코드
5. 테스트
6. 일반적 관례

문서와 코드가 충돌하면 임의 추정으로 메우지 말고
충돌 사실을 먼저 드러낸다.

---

## 5. 작업 시작 전 읽기 순서

DB 구축 task를 맡으면 최소 아래 순서로 읽는다.

1. [32-storage-architecture.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md)
2. [33-docs-vs-current-code-gap-analysis.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/33-docs-vs-current-code-gap-analysis.md)
3. 직접 관련된 SSOT
4. 직접 관련된 코드 파일
5. 직접 관련된 테스트 파일

예시:

- observability 작업:
  - [defense_observability_ssot.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_observability_ssot.yaml)
  - [audit.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/audit.py)
  - [main.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/api/main.py)
- 정책변경 작업:
  - [policy_v1.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/policy_v1.yaml)
  - [defense_policy_optimization_ssot.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_policy_optimization_ssot.yaml)
  - [loader.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/policy/loader.py)
  - [runtime.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/api/runtime.py)
- post-review 결과 저장 작업:
  - [21-data-contract.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md)
  - [001_post_review_tables.sql](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/storage/sql/001_post_review_tables.sql)

---

## 6. 작업 전 체크리스트

agent는 실제 수정 전에 아래를 먼저 통과해야 한다.

- [ ] 이번 task를 한 문장으로 다시 쓸 수 있다.
- [ ] 이번 task의 출력물이 문서인지, DDL인지, 코드인지 분명하다.
- [ ] [32-storage-architecture.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md)를 읽고 이번 task가 어느 축인지 정리했다.
- [ ] [33-docs-vs-current-code-gap-analysis.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/33-docs-vs-current-code-gap-analysis.md)를 읽고 현재 코드와 목표 구조의 차이를 짧게 메모했다.
- [ ] 직접 관련된 SSOT, 코드, 테스트 파일 경로를 확보했다.
- [ ] 이번 task에서 수정해도 되는 파일과 수정하면 안 되는 파일을 구분했다.
- [ ] 이번 task에 필요한 최소 필드와 금지할 필드를 구분했다.
- [ ] 검증 방법을 정했다.
- [ ] 이번 task가 infra provisioning, secret 주입, 운영 설정으로 번지지 않는다는 것을 확인했다.

작업 시작 전 agent는 최소 아래를 짧게 메모할 수 있어야 한다.

1. 이번 task의 목적
2. 참고한 문서
3. 현재 코드와 목표 구조의 차이
4. 이번에 건드릴 파일
5. 검증 계획

이 다섯 줄을 못 쓰면 아직 수정 단계로 들어가면 안 된다.

---

## 7. 작업 단위 규칙

한 번에 하나의 작은 task만 맡는다.

좋은 예:

- canonical audit 최소 필드 확정
- ClickHouse raw fact DDL 초안
- session rollup / candidate view 최소 계약
- PostgreSQL policy control-plane DDL 초안
- PostgreSQL -> Redis projection 계약

나쁜 예:

- observability 전체를 한 번에 구현
- DB 전부 설계 + 코드 + 테스트 + 인프라 요구까지 한꺼번에 처리

원칙:

- 작은 task 하나는 하나의 리뷰 가능한 단위여야 한다.
- 가능하면 하나의 PR 크기를 넘지 않는다.
- 선행 조건이 충족되지 않으면 다음 task로 넘어가지 않는다.

---

## 8. 프롬프트 구조 규칙

agent에게 작업을 맡길 때는 아래 구조를 유지한다.

- 목적
- 구현 범위
- 구현 제외
- 입력
- 출력
- 관련 문서
- 작업 지침
- 검증
- 완료 조건

최근 작업 스타일의 핵심은 아래였다.

- 읽을 문서를 순서까지 지정한다.
- 무엇을 하지 말아야 하는지 강하게 적는다.
- 작업 후 무엇을 기록해야 하는지 요구한다.

자세한 패턴은 아래 문서를 본다.

- [02-recent-agent-working-style.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/02-recent-agent-working-style.md)
- [03-db-build-task-template.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/03-db-build-task-template.md)

---

## 9. Scope Control

이번 DB 구축 작업에서 agent는 아래 범위를 넘지 않는다.

허용:

- 스키마 설계
- DDL 초안 작성
- repository / adapter 경계 정리
- env 계약 정리
- failure handling 규칙 정리
- 테스트 전략 정리
- 관련 문서 업데이트

금지:

- infra provisioning
- secret 주입
- 실제 DB 인스턴스 생성
- Grafana 서버 운영
- Discord webhook 운영 설정
- 관련 없는 runtime refactor
- 불필요한 컬럼 확대
- undocumented field 추가
- 오버엔지니어링

---

## 10. DB 구축 작업의 핵심 설계 원칙

### 10.1 최소 필드 우선

스키마와 필드값은 최소한으로 간다.

원칙:

- 지금 필요한 필드만 둔다.
- 나중에 쓸 것 같은 필드는 일단 넣지 않는다.
- “있으면 좋아 보이는” 컬럼을 추가하지 않는다.
- JSON 보존 컬럼과 typed column을 구분한다.

### 10.2 Runtime request path는 가볍게 유지

- Runtime request path는 PostgreSQL을 직접 읽지 않는다.
- Runtime authority는 Redis projection이 맡는다.
- ClickHouse는 event warehouse다.
- PostgreSQL은 authoritative result / control plane이다.

### 10.3 canonical audit는 원장이다

- `decision_audit`는 원본 증거 로그다.
- warehouse / rollup / candidate view는 그것을 읽기 좋게 만든 계층이다.
- raw event와 summary와 final result를 구분해서 본다.

### 10.4 policy change는 3계층으로 본다

- PostgreSQL: control plane
- Redis: runtime projection
- ClickHouse: effect measurement

---

## 11. 자동 강제 시스템 운영 규칙

agent는 아래 순서로 스스로 교정한다.

1. 문서 기준 확인
2. 코드 변경
3. 테스트 / lint / type check / 검증 실행
4. 실패 원인 확인
5. 최소 수정
6. 재검증

원칙:

- 실패는 숨기지 않는다.
- 실패 메시지는 유지하고, 원인을 줄여간다.
- broad fallback으로 빨간 불을 덮지 않는다.
- 검증하지 않은 작업을 완료로 표시하지 않는다.

가능하면 아래 항목을 항상 확인한다.

- 관련 테스트
- schema validation
- serialization / mapping 검증
- env 누락 시 동작
- privacy 금지 필드 미기록

---

## 12. 가비지 컬렉션 규칙

agent는 작업하면서 아래를 정리한다.

- 중복된 문장
- 원본 문서를 복제한 파일
- 현재 코드와 맞지 않는 구식 설명
- 쓰지 않는 필드 제안
- 지나치게 큰 task 설명

발견 시 원칙:

- 새 규칙으로 흡수할 수 있으면 문서에 반영한다.
- 같은 실수를 막을 테스트가 필요하면 체크리스트에 추가한다.
- 나쁜 패턴을 “예외적 허용”으로 남기지 않는다.

---

## 13. 실패 중심 통신

agent는 성공한 긴 로그보다 실패 순간의 정보에 집중한다.

좋은 보고:

- 무엇이 실패했는지
- 어느 파일/테이블/계층에서 실패했는지
- 왜 실패했는지
- 다음 수정 포인트가 무엇인지

나쁜 보고:

- 긴 성공 로그 나열
- 실패를 vague하게 표현
- 테스트를 안 돌리고 “될 것 같다”라고 말하기

---

## 14. 종료 체크리스트

- [ ] 이번 task의 목표가 한 문장으로 설명된다.
- [ ] 수정한 파일마다 왜 바뀌었는지 설명할 수 있다.
- [ ] 관련 문서와 코드 충돌 여부를 다시 확인했다.
- [ ] 변경 범위가 처음 합의한 task 범위 안에 있다.
- [ ] 스키마, 컬럼, 상태값, 이벤트 타입은 최소한으로 유지됐다.
- [ ] 새 필드나 새 레이어가 들어갔다면 왜 꼭 필요한지 설명 가능하다.
- [ ] 관련 검증을 실행했거나, 못 했다면 이유를 명시했다.
- [ ] 실패한 검증이 있으면 숨기지 않고 남겼다.
- [ ] 문서 drift가 생기지 않게 관련 문서를 같이 점검했다.
- [ ] infra 범위 작업을 끌어오지 않았다.
- [ ] 다음 task가 바로 이어질 수 있게 남은 리스크를 기록했다.

종료 보고에는 최소 아래 다섯 가지가 반드시 있어야 한다.

1. 무엇을 바꿨는지
2. 왜 그렇게 했는지
3. 어떤 파일이 바뀌었는지
4. 무엇으로 검증했는지
5. 남은 리스크와 다음 task

이 다섯 가지가 빠진 완료 보고는 불완전한 보고로 본다.

---

## 15. 작업 후 남겨야 할 것

작업이 끝나면 최소 아래를 남긴다.

1. 무엇을 바꿨는지
2. 왜 그렇게 했는지
3. 어떤 문서/코드/테이블이 영향을 받는지
4. 무엇으로 검증했는지
5. 남은 리스크와 다음 task

---

## 16. 이 폴더의 다른 문서

- [00-readme.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/00-readme.md)
  - 이 폴더의 entrypoint
- [01-doc-map.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/01-doc-map.md)
  - 원본 문서와 코드 파일 맵
- [02-recent-agent-working-style.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/02-recent-agent-working-style.md)
  - 최근 위임 방식 분석
- [03-db-build-task-template.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/03-db-build-task-template.md)
  - 바로 복사해서 쓸 수 있는 task 템플릿
