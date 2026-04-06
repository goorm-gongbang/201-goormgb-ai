# DB Build Task Prompt Template

아래 템플릿은 DB 구축 작업을 AI agent에게 맡길 때 바로 복사해서 쓰기 위한 최소 형식이다.

```md
당신은 이 저장소에서 DB 구축 작업을 수행하는 coding agent다. 이번 작업은 아래 한 가지 task만 수행한다.

## Task 제목
[여기에 task 제목]

## 작업 시작 전 필수 읽기 순서
1. `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/agent.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/33-docs-vs-current-code-gap-analysis.md`
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`
5. [이전 task 산출물 문서]
6. [이번 task와 직접 관련된 SSOT 문서]
7. [이번 task와 직접 관련된 코드 파일]
8. [관련 테스트 파일]

## 목적
- [이 task가 해결해야 하는 한 가지 목적]

## 구현 범위
- [허용되는 변경 1]
- [허용되는 변경 2]
- [허용되는 변경 3]

## 구현 제외
- infra provisioning
- secret 주입
- 실제 Grafana / Discord 연동
- 관련 없는 리팩터링
- undocumented field 추가
- 오버엔지니어링
- 이번 task 범위 밖 코드 변경

## 입력
- `32-storage-architecture.md`
- [관련 SSOT]
- [관련 코드]

## 출력
- [문서 초안 / DDL 초안 / repository 초안 / 테스트 초안 중 하나]

## 관련 문서
- [문서 경로 1]
- [문서 경로 2]
- [문서 경로 3]

## 작업 지침
1. 먼저 현재 코드와 문서 차이를 짧게 메모하라.
2. 최소 필드 / 최소 계약만 사용하라.
3. 새 컬럼이나 새 레이어를 추가할 때는 왜 필요한지 문서 기준으로 설명 가능해야 한다.
4. 문서와 코드가 충돌하면 충돌 사실을 먼저 드러내라.
5. 범위 밖 파일은 수정하지 마라.
6. 검증 실패 시 성공 로그보다 실패 원인과 수정 포인트를 먼저 보고하라.
7. 완료 조건을 충족할 때까지 같은 task 안에서 필요한 최소 보정을 스스로 진행하라.
8. 완료 조건을 충족하면 사용자 추가 확인을 기다리지 말고 task를 스스로 종료하라.

## 검증
- [문서 검증 명령]
- [테스트 명령]
- [필요 시 schema / lint / type check]

## 작업 로그
- 기본 로그 파일: `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`
- 이 task가 끝나면 위 파일에 아래 항목을 append하라.
  1. task 번호와 제목
  2. 작업 일시
  3. 실제로 수정한 파일 목록
  4. 파일별 수정 요약
  5. 검증에 사용한 명령과 결과 요약
  6. 남은 리스크 또는 다음 task에 넘길 입력
- 결과 메시지에는 작업 로그에 기록한 위치 또는 섹션도 함께 적어라.

## 작업 완료 후 기록
아래를 반드시 요약하라.
1. 무엇을 바꿨는지
2. 왜 그렇게 했는지
3. 어떤 파일이 바뀌었는지
4. 무엇으로 검증했는지
5. 남은 리스크
6. 다음 task가 바로 사용할 입력
7. 작업 로그에 append한 위치

## 완료 조건
- [완료 조건 1]
- [완료 조건 2]
- [완료 조건 3]
```

## 추천 task 분해 예시

지금 DB 구축 작업은 아래처럼 쪼개는 것이 안전하다.

1. canonical audit 최소 필드 확정
2. ClickHouse raw fact 최소 DDL 초안
3. session rollup / match rollup / candidate view 최소 계약
4. PostgreSQL policy control-plane 최소 DDL 초안
5. PostgreSQL -> Redis projection 계약 문서화
6. env / failure handling / test plan 정리
