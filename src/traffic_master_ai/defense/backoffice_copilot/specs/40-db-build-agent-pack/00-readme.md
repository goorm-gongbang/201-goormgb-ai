# DB Build Agent Pack

## 1. 목적

이 폴더는 방어 AI 서비스의 DB 환경 구축 작업을 진행할 때,
AI Agent가 먼저 읽어야 하는 문서와 작업 방식 기준을 한곳에 모아둔 entrypoint다.

중요한 원칙은 아래와 같다.

- 원본 SSOT 문서는 원래 위치를 유지한다.
- 이 폴더는 원본을 복제하지 않고, 읽기 순서와 작업 기준을 모아준다.
- DB 구축 작업의 기준 문서는 `32-storage-architecture.md`다.
- 이 폴더의 실제 최상위 작업 지침서는 `agent.md`다.
- `agent.md`는 하네스의 3요소인 컨텍스트 파일, 자동 강제 시스템, 가비지 컬렉션 원칙을 함께 담는다.

---

## 2. 가장 먼저 볼 파일

1. [agent.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/agent.md)
2. [32-storage-architecture.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md)
3. [33-docs-vs-current-code-gap-analysis.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/33-docs-vs-current-code-gap-analysis.md)
4. [31-observability-merge-strategy.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/31-observability-merge-strategy.md)

---

## 3. 이 폴더 안의 문서

- [agent.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/agent.md)
  - DB 구축 작업용 최상위 작업 지침서
- [01-doc-map.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/01-doc-map.md)
  - DB 구축 작업에 필요한 원본 문서와 코드 파일 맵
- [02-recent-agent-working-style.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/02-recent-agent-working-style.md)
  - 최근 agent 작업 방식과 프롬프트 패턴 분석
- [03-db-build-task-template.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/03-db-build-task-template.md)
  - DB 구축 작업을 agent에게 맡길 때 바로 복사해 쓸 수 있는 템플릿

---

## 4. 권장 시작 순서

1. `agent.md`를 읽고 작업 규칙과 하네스를 이해한다.
2. `32`를 읽고 목표 구조를 잡는다.
3. `33`을 읽고 현재 코드와의 gap을 확인한다.
4. `01-doc-map.md`를 따라 필요한 원본 문서를 연다.
5. `03-db-build-task-template.md`를 바탕으로 한 번에 하나의 작업만 보낸다.

---

## 5. 현재 작업 원칙

- DB 구축 작업의 중심 문서는 `32-storage-architecture.md`다.
- DB 구축 작업의 중심 컨텍스트 파일은 `agent.md`다.
- `31`은 소비 전략 문서다.
- `33`은 과도기 설명 문서다.
- AI팀은 애플리케이션이 DB를 어떻게 쓸지 정의하고 구현한다.
- 인프라 provisioning, secret 주입, DB 인스턴스 운영은 범위 밖이다.
