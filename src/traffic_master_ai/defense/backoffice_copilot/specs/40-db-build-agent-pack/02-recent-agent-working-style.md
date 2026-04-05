# 최근 Agent 작업 방식 정리

이 문서는 최근 작업 방식을 분석한 보조 문서다.  
실제 작업 지침은 [agent.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/agent.md)에 반영된다.

즉 이 문서는 최근 방식의 장점을 발굴하는 용도이고,
`agent.md`는 그 장점에 하네스 3요소를 결합해 실제 업무 지침으로 고정한 파일이다.

## 1. 어디서 추출했는가

최근 agent 작업 방식은 아래 문서들에서 가장 분명하게 드러난다.

- [02-prompt_guardrail_agents.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md)
- [02-implementation-task-breakdown-v2.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md)
- [task-prompts.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-prompts.md)

## 2. 최근 위임 방식의 핵심 패턴

최근에는 agent에게 일을 아래 방식으로 맡기는 패턴이 강했다.

### 2.1 한 번에 하나의 task만 맡긴다

- `Task 0`, `Task 1`, `Task 2`처럼 작게 자른다.
- 한 프롬프트에서 여러 task를 섞지 않는다.
- 선행 작업이 끝나지 않은 task는 보내지 않는다.

### 2.2 시작 전에 읽을 문서를 순서까지 지정한다

보통 아래 순서가 반복된다.

1. guardrail 문서
2. implementation breakdown 문서
3. 이전 task 실행 로그
4. 관련 SSOT / 계약 문서
5. 현재 코드 경계

즉 agent가 임의로 문맥을 선택하지 않게 만들고,
읽어야 할 문서를 먼저 고정한다.

### 2.3 프롬프트 구조가 일정하다

최근 task 프롬프트는 거의 항상 아래 항목을 포함한다.

- 목적
- 구현 범위
- 구현 제외
- 입력
- 출력
- 관련 문서
- 작업 지침
- 검증
- 작업 완료 후 기록
- 완료 조건

이 패턴 덕분에 agent가 scope를 벗어나기 어렵다.

### 2.4 문서 기준선이 먼저 고정되고, 그 다음 구현으로 간다

최근 작업 방식은 바로 코드를 짜게 하지 않고,
먼저 해석 충돌을 문서에서 정리하는 순서를 탔다.

흐름은 대체로 아래였다.

1. SSOT 정리
2. 공통 DTO/경계 정리
3. 저장 계층 정리
4. 입력/분석/후처리 정리
5. 최종 workflow 조립

즉 문서와 경계를 먼저 잠그고, 구현은 그 뒤에 붙이는 방식이다.

### 2.5 금지 범위를 매우 구체적으로 적었다

최근 프롬프트는 항상 아래를 명시적으로 막았다.

- 관련 없는 리팩터링
- 새 요구사항 추가
- task 범위 밖 코드 변경
- 외부 연동 실제 구현
- undocumented field 추가
- 저장소 추가

즉 “무엇을 하라”보다 “무엇을 하지 마라”가 강하게 적혀 있었다.

### 2.6 완료 후 로그를 남기게 했다

`task-prompts.md` 기준으로는 작업 후 변경 파일 요약 문서를 남기게 했다.

즉 단순 구현보다

- 무엇을 읽었는지
- 무엇을 바꿨는지
- 무엇으로 검증했는지
- 다음 task에 넘길 리스크가 무엇인지

를 남기는 방식이었다.

## 3. 최근 코드 작업 흐름에서 보이는 실제 방향

최근 git log와 최신 `dev` 기준으로 보면, agent 작업 방향은 아래 축으로 움직였다.

- decision state를 실제 Redis에 연결
- VQA verify 상태와 runtime risk/tier 흐름 정리
- policyVersion 동기화 writer 경로 수정
- observability / DB / 정책변경 문서 정리

즉 최근 agent 작업은
`Runtime state 안정화 -> observability 정리 -> DB 아키텍처 명세화`
흐름으로 진행됐다고 보는 게 맞다.

## 4. DB 구축 작업에 그대로 가져와야 할 패턴

DB 구축용 agent 작업도 아래 방식으로 보내는 게 가장 안전하다.

### 4.1 task를 작게 쪼갠다

예:

- Task A: canonical audit 필드 확정
- Task B: ClickHouse raw fact DDL 초안
- Task C: session rollup / candidate view 계약
- Task D: PostgreSQL policy control-plane DDL 초안
- Task E: env / repository / failure handling 문서화

### 4.2 각 task마다 읽기 순서를 고정한다

최소한 아래를 고정하는 게 좋다.

1. [32-storage-architecture.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md)
2. [33-docs-vs-current-code-gap-analysis.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/33-docs-vs-current-code-gap-analysis.md)
3. 관련 SSOT
4. 관련 코드 파일
5. 최근 변경이 들어간 테스트

### 4.3 프롬프트에 구현 제외를 강하게 넣는다

DB 구축 task에는 특히 아래를 자주 금지해야 한다.

- infra provisioning
- secret 주입
- 실제 Grafana / Discord 연동
- 관련 없는 runtime refactor
- 불필요한 컬럼 확장
- 오버엔지니어링

### 4.4 검증 방법을 task마다 붙인다

예:

- 문서 sync 검증
- schema diff 검토
- repository unit test
- serialization test
- env 누락 테스트

## 5. 지금 DB 구축에서 agent에게 맡기기 좋은 작업 단위

지금 시점에서 agent에게 맡기기 좋은 단위는 아래 순서다.

1. `defense_audit_events` 최소 typed column 확정
2. policy/control-plane PostgreSQL 4테이블 최소 컬럼 확정
3. session rollup / match rollup / candidate view 최소 계약 확정
4. env / failure handling / projection worker 계약 정리
5. DDL 초안 작성
6. repository / adapter 경계 초안 작성

즉 최근 방식대로라면,
지금도 “한 번에 하나의 작은 task”로 보내는 게 맞다.
