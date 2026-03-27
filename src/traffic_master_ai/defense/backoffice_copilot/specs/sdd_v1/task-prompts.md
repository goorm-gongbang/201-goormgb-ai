# SDD v1 Task Prompts

## 문서 운영 원칙
- 이 문서는 Backoffice Copilot 구현용 task 프롬프트를 순차적으로 누적하는 문서다.
- 한 번에 하나의 task 프롬프트만 추가한다.
- 다음 task 프롬프트는 이전 task 결과를 검토한 뒤 작성한다.
- 각 task 프롬프트에는 반드시 작업 후 변경 파일 요약 문서 작성 요구를 포함한다.
- 프롬프트 문구를 다듬더라도, 이미 수행이 끝난 task의 요구사항 의도는 임의로 바꾸지 않는다.

---

## Task 0. SSOT 동기화 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 0`만 수행한다. 목적은 SSOT 문서들 사이에 남아 있는 해석 충돌을 정리해서, 이후 Task 1부터는 모든 구현이 동일한 기준(`match_id`, DB-first, no-`payment_success`, semantic mapping, backend boundary) 위에서 시작되도록 만드는 것이다.

## 작업 시작 전 필수 읽기 순서
아래 문서를 먼저 읽고, 충돌 지점을 메모한 뒤 수정에 들어가라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-shared-terms-and-doc-map.md`
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/00-core-rules.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/01-service-overview/01-service-overview.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/10-post-review-rules.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/11-review-output-rules.md`
8. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`
9. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`
10. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/30-ops-and-checks.md`

그 다음, 실제 동기화가 필요한 경우에만 같은 번호의 `.yaml` 파일을 읽고 `.md` 기준으로 맞춰라.

## 목적
- v1 run 식별자를 `match_id` 단일 기준으로 고정한다.
- 정식 출력/완료 기준을 PostgreSQL 2테이블 저장 우선으로 고정한다.
- 후보 추출과 사후판단 대상 정의에서 `payment_success` 또는 그에 준하는 표현을 제거한다.
- `flowState`, `terminalReason`, `reasonCode`, `latest_*` 해석 책임이 semantic mapping 계층에 있음을 문서상 명확히 한다.
- backend 범위를 `Backend request DTO` 생성, adapter 경계, `backend_delivery_status` 갱신까지로 제한한다.

## 구현 범위
- 문서 수정만 수행한다.
- 우선 수정 대상은 아래 문서들이다.
  - `00-core-rules/00-core-rules.md`
  - `00-core-rules/00-core-rules.yaml`
  - `01-service-overview/01-service-overview.md`
  - `01-service-overview/01-service-overview.yaml`
  - `10-post-review-rules/10-post-review-rules.md`
  - `10-post-review-rules/10-post-review-rules.yaml`
  - `11-review-output-rules/11-review-output-rules.md`
  - `11-review-output-rules/11-review-output-rules.yaml`
  - `20-langgraph-node-spec/20-langgraph-node-spec.md`
  - `20-langgraph-node-spec/20-langgraph-node-spec.yaml`
  - `21-data-contract/21-data-contract.md`
  - `21-data-contract/21-data-contract.yaml`
  - `30-ops-and-check/30-ops-and-checks.md`
  - `30-ops-and-check/30-ops-and-checks.yaml`
- `02-shared-terms-and-docs/02-shared-terms-and-doc-map.md`는 용어/권위/읽기 순서 설명이 Task 0 결과와 어긋나는 부분이 있을 때만 함께 수정한다.
- 동일 번호 `.md`와 `.yaml`이 다르면 `.md` 본문 의미를 우선 SSOT로 보고 `.yaml`을 동기화한다.
- 표현 drift를 없애는 범위에서만 수정한다. 큰 구조 개편이나 새 문서 추가는 하지 않는다.

## 구현 제외
- 코드 구현
- DTO/DB schema 실제 구현
- 테스트 코드 추가
- 새 요구사항 추가
- Task 1 이후 내용을 미리 끌어와 상세 설계 확장
- 관련 없는 리팩터링, 파일 이동, 문서 재편집

## 입력
- 현재 Backoffice Copilot SSOT 문서 세트
- `02-implementation-task-breakdown-v2.md`의 Task 0 확정 기준
- `02-prompt_guardrail_agents.md`의 SDD 가드레일

## 출력
- v1 기준으로 해석이 일치하는 SSOT 문서 세트
- 같은 번호의 `.md`/`.yaml`이 서로 어긋나지 않는 상태
- 작업 후 변경 이력을 기록한 문서 1개

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/01-service-overview/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-shared-terms-and-doc-map.md`

## 작업 지침
1. 먼저 `rg`로 아래 충돌 표현을 전수 검색해 수정 후보를 식별하라.
   - `review_run_id`
   - `payment_success`
   - `reports/post_review`
   - `결제 단계 이후`
   - export 파일이 정식 저장처럼 읽히는 문장
   - semantic mapping 책임이 빠져 있거나 loader/interpreter 책임이 섞인 문장
   - backend 실제 구현 범위를 우리 범위처럼 읽히게 만드는 문장
2. `02-implementation-task-breakdown-v2.md`의 확정 기준을 우선 적용하라.
   - run 식별자는 `match_id`
   - 출력 기준은 DB-first
   - 후보 추출에는 `payment_success`를 사용하지 않음
   - 의미 해석 책임은 semantic mapping 계층
   - backend 범위는 DTO/adapter 경계 + 상태 갱신까지
3. 상위 문서(`00`, `01`)는 서비스 정체성과 제품 범위를 설명하는 수준으로 정리하되, 하위 문서(`10`, `11`, `20`, `21`, `30`)와 충돌하는 문장을 남기지 마라.
4. `review_run_id`는 v1의 활성 식별자로 남겨두지 마라.
   - 허용되는 경우는 “사용하지 않는다”, “재도입 금지”, “과거 충돌 설명”처럼 금지/배제 문맥뿐이다.
5. export 관련 문장을 삭제하지는 말고, 반드시 “DB 저장 이후 생성되는 후속 산출물”로 읽히도록 맞춰라.
6. `payment_success`, “결제 단계 이후”, “payment stage”처럼 v1 후보 조건으로 오해될 수 있는 표현은 제거하거나 승인된 규칙 표현으로 바꿔라.
   - F 상태 모델(`F4R`, `F4M`, `FX`) 설명 자체를 없앨 필요는 없지만, 이를 Task 0 확정 기준에 없는 새로운 hard filter처럼 격상하지 마라.
7. semantic mapping 관련 문구는 아래 뜻이 읽히도록 맞춰라.
   - row loader는 원시 row를 읽는 책임만 가진다.
   - `flowState`, `terminalReason`, `reasonCode`, `latest_*` 해석은 semantic mapping 계층 책임이다.
   - row loader / event interpreter / semantic mapping 책임이 섞이지 않게 표현한다.
8. backend 관련 문구는 아래 뜻이 읽히도록 맞춰라.
   - 우리 구현 범위는 `Backend request DTO` 생성과 adapter 경계 정의, 응답 기반 `backend_delivery_status` 갱신까지다.
   - 외부 backend 서버/API 자체 구현은 범위 밖이다.
   - Discord/Grafana 실제 연동도 범위 밖이다.
9. 문서별 권위는 유지하라.
   - 필드 계약은 `21`
   - 노드 책임은 `20`
   - 출력 계약은 `11`
   - 도메인 해석은 `10`
   - 운영 검증은 `30`
   - 상위 범위/정체성은 `00`, `01`
10. 같은 의미를 모든 문서에 복붙하지 마라. 권위 문서에는 명확히 쓰고, 다른 문서에는 충돌만 제거하는 식으로 최소 수정하라.
11. `02-implementation-task-breakdown-v2.md`와 `02-prompt_guardrail_agents.md`는 이번 작업의 기준 문서다. 오타나 명백한 참조 오류가 아니라면 수정하지 마라.

## 현재 저장소에서 우선 확인할 drift 예시
아래는 이미 드러난 예시일 가능성이 높다. 이 예시만 고치고 끝내지 말고 같은 류의 표현을 전수 확인하라.

- `02-shared-terms-and-doc-map.md`에 `review_run_id`가 활성 용어처럼 남아 있는지
- `00-core-rules.*` 또는 `01-service-overview.*`에 출력 파일 3개가 정식 출력처럼 읽히는 문장이 있는지
- `00-core-rules.*` 또는 `01-service-overview.*`에 `payment_success` 또는 “결제 단계 이후” 의미가 후보 조건처럼 남아 있는지
- 상위 문서에 semantic mapping 책임이 불명확하거나 loader/interpreter 책임이 뒤섞인 표현이 있는지
- backend 범위가 외부 구현까지 포함하는 것처럼 읽히는 표현이 있는지

## 검증
작업 후 최소 아래를 검증하라.

1. 대상 문서들에서 `review_run_id`가 활성 v1 식별자로 남아 있지 않다.
2. 대상 문서들에서 `payment_success`나 동등 의미 표현이 후보 추출 규칙으로 남아 있지 않다.
3. export 파일은 DB 저장 이후 후속 산출물로 읽힌다.
4. semantic mapping 책임이 문서상 분명하다.
5. backend 범위가 DTO/adapter/status update 경계로 제한되어 읽힌다.
6. `.md`와 짝이 있는 `.yaml`이 의미상 동기화되어 있다.

필요하면 아래와 같은 검색으로 검증하라.

- `rg -n "review_run_id|payment_success|reports/post_review|결제 단계 이후" src/traffic_master_ai/defense/backoffice_copilot/specs`
- `rg -n "semantic mapping|flowState|terminalReason|reasonCode|latest_" src/traffic_master_ai/defense/backoffice_copilot/specs`
- `rg -n "Backend request DTO|backend_delivery_status|backend" src/traffic_master_ai/defense/backoffice_copilot/specs`

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 새로 만들거나 갱신해서 Task 0 결과를 남겨라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- 문서상 v1 구현 기준이 `match_id`, DB-first, no-`payment_success`, semantic mapping, backend boundary로 일관되게 읽힌다.
- coding agent가 더 이상 `review_run_id`, export-first, `payment_success`, backend 실제 구현 범위를 혼동하지 않는다.
- 문서 수정 외 기능 추가가 없다.
- 변경 파일 요약 문서가 `specs/sdd_v1` 아래에 남는다.
```

---

## Task 1. 공통 계약 및 패키지 골격 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 1`만 수행한다. 목적은 후속 Task 2~10이 공통 import 기준과 고정된 책임 경계 위에서 구현될 수 있도록, 공통 DTO, graph state, warnings/errors 구조, config skeleton, package boundary를 최소 범위로 확정하는 것이다.

이번 작업은 반드시 Task 0 완료 상태를 전제로 한다. Task 0 기준이 흔들리는 상태라면 임의 보정으로 진행하지 말고 충돌 사실을 드러내라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, Task 1에서 고정해야 할 계약과 금지 범위를 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 0 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/00-core-rules.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/10-post-review-rules.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`

그 다음 현재 코드 구조를 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/`
- `src/traffic_master_ai/defense/backoffice_copilot/core/`

구현 스타일 참고가 필요하면 아래 기존 패턴도 확인하라.

- `src/traffic_master_ai/defense/d0_mvp/core/models.py`
- `src/traffic_master_ai/defense/api/state.py`

단, 기존 코드 패턴이 spec과 충돌하면 spec을 우선한다.

## 목적
- `match_id` 기반 run context와 graph input/state 계약을 고정한다.
- `DefenseAuditEventRow`, `SessionSummary`, `SessionAnalysis` 공통 DTO를 고정한다.
- LLM input/output DTO와 backend request/response DTO를 고정한다.
- warnings/errors 구조를 후속 task가 재정의하지 않도록 최소 형태로 고정한다.
- 최소 config skeleton과 package/module boundary를 만들어 이후 task의 import 경로를 안정화한다.

## 구현 범위
- `match_id` 기반 run input 또는 run context 타입
- graph state 계약
- `DefenseAuditEventRow`
- `SessionSummary`
- `SessionAnalysis`
- LLM input DTO
- LLM output DTO
- Backend request DTO
- Backend response DTO
- warnings/errors container 타입
- 최소 config skeleton
- stable export surface를 포함한 package/module skeleton

## 구현 제외
- 비즈니스 로직
- row loader / event interpreter / semantic mapping 구현
- DB 저장/repository/DDL
- validator 구현
- LLM 호출 구현
- backend 실제 호출 구현
- workflow 조립
- 테스트 스위트 본격 추가
- undocumented field 추가

## 입력
- Task 0 완료 문서
- `20-langgraph-node-spec.*`
- `21-data-contract.*`
- `00-core-rules.*`
- `10-post-review-rules.*`

## 출력
- 공통 타입/모델 계층
- 최소 config skeleton
- 후속 task가 재사용할 수 있는 stable import 경로
- 필요 최소한의 package boundary code skeleton

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

## 권장 구현 방향
현재 `src/traffic_master_ai/defense/backoffice_copilot/core/`가 비어 있다면, 아래와 같은 최소 구조를 우선 검토하라.

- `core/models.py`: DTO 모델 모음
- `core/state.py`: run input/context + graph state
- `core/issues.py`: warnings/errors 타입
- `core/config.py`: 최소 config skeleton
- `core/__init__.py`: 안정적인 export surface

정확한 파일명은 조금 달라도 되지만, 역할이 겹치는 파일을 여러 개 만들지 말고 3~5개 수준의 작은 모듈로 끝내라. prose 문서보다 코드 골격으로 경계를 드러내는 쪽을 우선한다.

## 작업 지침
1. Task 0 완료 로그를 읽고, 최소한 아래 기준이 문서상 이미 고정되었는지 재확인하라.
   - run 식별자는 `match_id`
   - `review_run_id`는 사용하지 않음
   - 중간 산출물은 메모리 DTO
   - semantic mapping 책임은 별도 계층
   - backend 범위는 DTO/adapter/status update 경계
2. 새 코드는 `src/traffic_master_ai/defense/backoffice_copilot/` 아래 최소 범위로만 추가하라. 기존 `defense` 다른 패키지는 참고만 하고 건드리지 마라.
3. 인메모리 DTO와 state는 가능하면 `@dataclass(slots=True)`를 사용하라. 경계 인터페이스가 정말 필요할 때만 `Protocol`을 써라.
4. 공통 계약 필드명은 Task 0 기준 문서와 동일하게 `snake_case`로 맞춰라.
   - `session_id`를 사용하고, shared contract에 `sessionId`를 재도입하지 마라.
   - `match_id` 외 별도 run 식별자를 만들지 마라.
5. `DefenseAuditEventRow`는 raw row 최소 구조만 가져야 한다.
   - semantic mapping 결과 필드를 여기에 섞지 마라.
   - `flowState`, `terminalReason`, `reasonCode`, `latest_*` 해석 로직이나 해석 전용 필드를 Task 1에 넣지 마라.
6. `SessionSummary`와 `SessionAnalysis`는 메모리 DTO로만 정의하라.
   - repository 메서드, DB 컬럼 지식, persistence helper를 붙이지 마라.
   - 단순 직렬화/표현 helper 정도가 정말 필요하면 최소 수준으로만 두어라.
7. graph state는 `20-langgraph-node-spec.md`에 나온 공통 상태 필드만 담아라.
   - 임의 캐시, metrics, retry history, debug blob, future validator 결과, 중간 persistence 포인터를 미리 넣지 마라.
   - Node 6 출력 필드를 위해 타입이 필요하면, `21`/`11`에 이미 있는 필드만 반영한 얇은 record DTO로 제한하라.
8. warnings/errors는 문자열 list로 흩어지지 않도록 최소 구조를 고정하라.
   - 예: `code`, `message`, `context`
   - 단, Task 9a/9b 전에 과한 validation taxonomy를 만들지 마라.
9. config skeleton은 현재 문서에 이미 있는 cross-task 입력만 반영하라.
   - 예: `match_id`, `window_start_ms`, `window_end_ms`, `limit`, `use_raw_audit_fallback`
   - DB/LLM/backend/env 세부 설정을 Task 1에서 확장하지 마라.
10. 후속 task가 안정적으로 import할 수 있도록 export surface를 정리하라.
   - later task가 로컬 타입을 다시 정의하지 않게 만들어야 한다.
   - 그렇다고 광범위한 facade 계층이나 service locator를 만들지는 마라.
11. spec에 없는 필드를 “나중에 필요할 것 같아서” 넣지 마라.
   - undocumented field 추가 금지
   - `review_run_id` 재도입 금지
   - `payment_success` 같은 미합의 필드 도입 금지
12. module boundary는 “책임 분리”만 보여주면 충분하다.
   - Task 2 저장소
   - Task 3 loader / semantic mapping
   - Task 6 LLM caller
   - Task 10 workflow wiring
   위 구현체를 Task 1에서 미리 만들지 마라.

## 최소 고정 대상
아래 항목은 후속 task가 다시 정의하지 않도록 이번에 고정해야 한다.

1. run input / run context
2. graph state
3. `DefenseAuditEventRow`
4. `SessionSummary`
5. `SessionAnalysis`
6. LLM input/output DTO
7. Backend request/response DTO
8. warnings/errors item 구조
9. package export 경로

## 검증
작업 후 최소 아래를 검증하라.

1. 새 공통 계약에서 `review_run_id`가 존재하지 않는다.
2. 새 공통 계약에 undocumented field가 없다.
3. `DefenseAuditEventRow`에 semantic mapping 결과가 섞여 있지 않다.
4. `SessionSummary`/`SessionAnalysis`가 메모리 DTO로만 표현된다.
5. 후속 task가 같은 타입을 재정의하지 않고 import할 수 있는 구조다.
6. 생성한 모듈들이 import 가능하다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- 필요 시 새 공통 계약을 import하는 최소 단위 테스트

단, Task 11 범위로 넘어가는 대규모 테스트 작성은 하지 마라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 1 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0 기록을 지우지 마라.
- 로그가 단일 task 형식이라면, Task 0 내용을 보존한 상태로 “여러 task를 순차 기록하는 형식”으로 정리해도 된다.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- 후속 task가 공통 계약을 재정의하지 않고 바로 사용할 수 있다.
- 중간 산출물은 메모리 DTO로만 처리된다는 점이 구조에 반영된다.
- package/module 경계가 최소한의 코드 골격으로 드러난다.
- undocumented field가 없고 `review_run_id`가 재도입되지 않는다.
- Task 1 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 2. PostgreSQL 저장소 기반 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 2`만 수행한다. 목적은 PostgreSQL 2테이블 저장 구조와 write adapter/repository 경계를 먼저 고정해서, 이후 Task 8이 이미 정의된 저장 계층만 소비하도록 만드는 것이다.

이 task는 Task 3과 병렬 가능하지만, 이번 프롬프트에서는 Task 2 범위만 수행한다. loader/semantic mapping/LLM/workflow 영역까지 확장하지 마라.

이번 작업은 반드시 Task 1 구현 완료 상태를 전제로 한다. Task 1 공통 계약이 실제 코드와 로그에 없거나 spec과 어긋나면 임의로 우회하지 말고 충돌 사실을 드러내라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, 저장소 계층에서 고정해야 할 계약과 금지 범위를 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 1 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/11-review-output-rules.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/30-ops-and-checks.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/10-post-review-rules.md`

그 다음 현재 공통 계약과 기존 PostgreSQL 패턴을 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/config.py`
- `src/traffic_master_ai/defense/api/database.py`
- `src/traffic_master_ai/defense/api/etl_worker.py`

단, 기존 구현 패턴이 spec과 충돌하면 spec을 우선한다.

## 목적
- `post_review_runs`와 `post_review_session_results` 저장 구조를 코드 레벨로 고정한다.
- Task 1의 `PostReviewRunRecord`, `PostReviewSessionResultRecord`를 소비하는 repository/write adapter 경계를 만든다.
- PK conflict policy 연결 지점을 명시적으로 만든다.
- allowed value / JSONB / 타입 검증 helper를 분리한다.
- DB-first 구조를 고정하되 export/backend/workflow 범위를 끌어오지 않는다.

## 구현 범위
- PostgreSQL DDL 또는 migration 산출물
- `post_review_runs`
- `post_review_session_results`
- repository/write adapter
- PK conflict policy 연결 지점
- column-level validator helper
- allowed value validator helper
- JSONB 구조 validator helper
- 최소 PostgreSQL 연결 진입점

## 구현 제외
- backend 실제 호출
- export 생성
- workflow 조립
- ClickHouse/S3 저장 추가
- 중간 산출물 전용 테이블 추가
- read/query 서비스 확장
- 운영 UI/API 구현
- Task 9a의 validator 전체 구조 선구현

## 입력
- Task 1 공통 계약 코드
- `11-review-output-rules.*`
- `21-data-contract.*`
- `30-ops-and-checks.*`
- `10-post-review-rules.*`
- PostgreSQL 연결 방식

## 출력
- DDL/migration
- repository 계층
- write adapter
- column-level validator 기초

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/config.py`

## 권장 구현 방향
기존 `core` 계약을 건드리지 않는 선에서 아래와 같은 최소 저장소 구조를 우선 검토하라.

- `storage/__init__.py`
- `storage/connection.py` 또는 `storage/database.py`
- `storage/repository.py`
- `storage/validators.py`
- `storage/sql/001_post_review_tables.sql` 또는 이에 준하는 명시적 SQL 파일

정확한 파일명은 조금 달라도 되지만, 새 migration framework나 ORM abstraction layer를 크게 추가하지 마라. 저장소에 별도 migration 체계가 없으므로, 최소한의 명시적 SQL 산출물과 Python write adapter 조합으로 끝내는 쪽을 우선한다.

## 작업 지침
1. Task 1 로그와 코드를 읽고, 아래 공통 계약이 실제 구현되어 있는지 먼저 확인하라.
   - `PostReviewRunRecord`
   - `PostReviewSessionResultRecord`
   - `RunStatus`
   - `ReviewResult`
   - `BackendDeliveryStatus`
2. 새 저장소 코드는 `src/traffic_master_ai/defense/backoffice_copilot/` 아래 최소 범위에만 추가하라. `core` 계약은 재정의하지 말고 import해서 써라.
3. 저장 테이블은 정확히 2개만 허용한다.
   - `post_review_runs`
   - `post_review_session_results`
   - 그 외 중간 산출물 테이블, staging 테이블, export 전용 테이블 추가 금지
4. 컬럼명, 타입, NULL, PK/UK, 허용값은 `21-data-contract.md`와 `11-review-output-rules.md`를 그대로 따른다.
   - `status ∈ {SUCCESS, PARTIAL_SUCCESS, FAILED}`
   - `review_result ∈ {NORMAL, SUSPICIOUS}`
   - `backend_delivery_status ∈ {PENDING, SENT, FAILED}`
5. JSONB validator는 최소한 아래를 검증할 수 있어야 한다.
   - `summary_text_json`이 길이 3 배열인지
   - `session_analysis_json`이 `SessionAnalysis` 최소 구조와 호환되는지
6. PK conflict policy는 숨은 기본값으로 묻어두지 말고, 명시적인 연결 지점으로 드러내라.
   - enum, strategy 인자, repository 설정 등 형태는 단순하게 택해도 된다.
   - 단, retry orchestration 전체를 지금 완성할 필요는 없다.
7. 저장소 계층은 write-focused로 유지하라.
   - insert/upsert/save 계열 write adapter만 만들고, 분석용 read/query API까지 넓히지 마라.
   - Task 8에서 row 조립 결과를 저장할 수 있을 정도면 충분하다.
8. PostgreSQL 연결 helper가 필요하면, 저장소의 기존 `TM_PG_URL` 관례를 우선 검토하라.
   - 새 env 이름을 여러 개 만들지 마라.
   - Alembic, 새 ORM, 별도 DB framework 추가 금지
9. SQLAlchemy 사용은 허용되지만, Task 2의 핵심은 저장 계약 고정이다.
   - ORM 모델링이 과해지면 오히려 범위를 넘는다.
   - 명시적 SQL + 얇은 adapter 조합이면 충분하다.
10. export/backend/workflow 문구나 코드는 넣지 마라.
   - export 생성은 Task 8
   - backend 실제 호출은 범위 밖
   - workflow wiring은 Task 10
11. ClickHouse/S3를 저장소 후보로 다시 꺼내지 마라.
12. Task 9a validator와 역할이 겹치지 않게, 여기서는 “컬럼/허용값/JSONB 저장 전 검증 helper”까지만 만든다.

## 최소 고정 대상
아래 항목은 Task 8과 Task 9a/9b가 다시 설계하지 않도록 이번에 고정해야 한다.

1. `post_review_runs` DDL
2. `post_review_session_results` DDL
3. write repository interface
4. PostgreSQL adapter 진입점
5. PK conflict policy 연결 지점
6. allowed value helper
7. JSONB/type helper

## 검증
작업 후 최소 아래를 검증하라.

1. DDL/SQL 산출물에 허용 테이블이 정확히 2개뿐이다.
2. `status`, `review_result`, `backend_delivery_status` 허용값 검증이 반영된다.
3. `summary_text_json`, `session_analysis_json` 검증 helper가 존재한다.
4. repository가 Task 1 record DTO를 재정의하지 않고 import해서 사용한다.
5. 저장소 모듈이 import 가능하고 문법 오류가 없다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- validator 단위 테스트 또는 저장 SQL smoke 검증
- DB가 로컬에 준비되어 있지 않다면, live DB 성공을 가장하지 말고 정적/단위 검증까지만 명시하라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 2 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0, Task 1 기록을 지우지 마라.
- 저장소 구현 범위와 검증 범위를 분리해서 기록하라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- 허용 테이블은 2개뿐이다.
- `review_result`, `backend_delivery_status`, `status` 허용값이 반영된다.
- JSONB 저장 대상 구조를 검증할 수 있다.
- repository/write adapter가 Task 1 공통 계약을 재사용한다.
- Task 2 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 3. 입력 row 로더 + semantic mapping 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 3`만 수행한다. 목적은 입력 로딩과 의미 해석을 명확히 분리해서, 이후 Task 4부터 규칙 기반 집계/분석이 안정적으로 돌아가도록 `analysis_input`과 semantic mapping/interpreter 계층을 준비하는 것이다.

이 task는 Task 2와 병렬 가능하지만, 이번 프롬프트에서는 Task 3 범위만 수행한다. PostgreSQL 저장소/DDL/validator 전체 구조까지 끌어오지 마라.

이번 작업은 반드시 Task 1 구현 완료 상태를 전제로 한다. Task 1 공통 계약이 실제 코드와 로그에 없거나 spec과 어긋나면 임의 보정으로 진행하지 말고 충돌 사실을 드러내라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, loader와 semantic mapping의 책임 경계를 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 1 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/00-core-rules.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/01-service-overview/01-service-overview.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/10-post-review-rules.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`
8. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`

그 다음 현재 공통 계약과 참고 가능한 로그 스키마 패턴을 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/config.py`
- `src/traffic_master_ai/defense/d0_mvp/observability/schemas.py`

단, 기존 패턴이 spec과 충돌하면 spec을 우선한다.

## 목적
- `defense_audit_events` 입력 로딩을 time-window 기준으로 고정한다.
- raw row 로딩과 semantic mapping 책임을 분리한다.
- `analysis_input`을 Task 4가 소비할 수 있는 형태로 준비한다.
- `flowState`, `terminalReason`, `reasonCode`, `latest_*`, `terminal_outcome` 해석 함수를 semantic mapping 계층에 고정한다.
- 핵심/보강/비사용 event 분류를 후속 task가 재정의하지 않도록 구조화한다.

## 구현 범위
- `defense_audit_events` 시간 구간 필터 로딩
- `limit` 처리
- `raw_audit_available` 기록
- 핵심/보강/비사용 event 분류
- semantic mapping 함수
- event interpreter 또는 이에 준하는 해석 계층
- `analysis_input` 준비

## 구현 제외
- candidate 추출
- `SessionSummary` 집계
- `SessionAnalysis` 생성
- LLM 호출
- DB 저장
- `decision_audit` 실제 raw fallback 조회 구현
- export 생성
- workflow 조립

## 입력
- graph input
- `defense_audit_events.jsonl`
- Task 1 공통 계약 코드

## 출력
- `analysis_input`
- semantic mapping/interpreter 계층

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/01-service-overview/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`

## 권장 구현 방향
기존 `core` 계약을 재사용하는 선에서 아래와 같은 최소 구조를 우선 검토하라.

- `ingest/__init__.py`
- `ingest/loader.py`
- `ingest/semantic_mapping.py`
- `ingest/interpreter.py` 또는 `ingest/classification.py`

정확한 파일명은 조금 달라도 되지만, loader와 semantic mapping을 한 파일/한 함수에 몰아넣지 마라. 역할이 섞이면 Task 4~5가 바로 흔들린다.

## 작업 지침
1. Task 1 공통 계약을 먼저 확인하라.
   - `DefenseAuditEventRow`는 raw row 최소 구조다.
   - `PostReviewRunInput`, `PostReviewGraphState`, `AnalysisInput`을 우선 재사용하라.
2. 만약 현재 `AnalysisInput` 계약이 Task 3 출력(`raw_audit_available` 포함)을 담기에 부족하면, 문서에 이미 있는 요구를 만족하는 최소 보정만 허용한다.
   - 예: raw row 묶음 + `raw_audit_available`을 담는 작은 typed container
   - 단, 이 기회에 다른 미래 필드까지 미리 넣지 마라.
   - 보정이 필요했다면 Task 3 기록에 명시하라.
3. loader는 raw row 로딩만 담당한다.
   - JSONL 파싱
   - 시간 구간 필터
   - `limit` 처리
   - `raw_audit_available` 기록
   - raw `DefenseAuditEventRow` 생성
4. semantic mapping 계층은 의미 해석만 담당한다.
   - `flowState`
   - `terminalReason`
   - `reasonCode`
   - `latest_*`
   - `terminal_outcome`
   - 해석 함수는 raw row 또는 payload를 입력으로 받되, raw DTO 자체를 semantic DTO로 바꾸는 식의 무분별한 확장은 하지 마라.
5. event interpreter는 semantic mapping 결과를 소비해 event를 분류하거나 후속 집계용 형태를 준비할 수 있다.
   - 하지만 candidate hard filter나 session 집계 자체는 Task 4로 넘겨라.
6. event 분류는 최소한 아래 3종을 구분하라.
   - 핵심 event
   - 보강 event
   - 비사용 event
   - `S3_CHALLENGE_HALTED`는 비사용으로 분리하라.
7. `payment_success`, 결제 단계 도달 여부, payment stage 같은 미합의 필드를 loader/interpreter에 도입하지 마라.
8. `limit` 처리는 비결정적으로 구현하지 마라.
   - 시간 구간 필터 이후의 적용 순서를 코드 주석이나 테스트에서 분명히 하라.
   - source order를 유지하든 정렬하든, 결과가 재현 가능해야 한다.
9. Task 3에서 `decision_audit`를 대량 조회하거나 raw fallback을 실제 수행하지 마라.
   - 지금 필요한 것은 `raw_audit_available` 기록과 semantic mapping 준비뿐이다.
10. DB 저장, repository 호출, backend 전달, export 생성 코드를 넣지 마라.
11. 가능하면 Task 1 타입을 import해서 재사용하고, 유사 타입을 새로 만들지 마라.

## 최소 고정 대상
아래 항목은 Task 4~5가 다시 설계하지 않도록 이번에 고정해야 한다.

1. `defense_audit_events` loader 경계
2. `analysis_input` 형태
3. `raw_audit_available` 기록 방식
4. event 분류 기준 구조
5. semantic mapping 함수 경계
6. `S3_CHALLENGE_HALTED` 비사용 처리

## 검증
작업 후 최소 아래를 검증하라.

1. 입력 row DTO는 최소 구조를 유지한다.
2. 해석 책임은 semantic mapping 계층에만 있다.
3. `S3_CHALLENGE_HALTED`는 비사용으로 분리된다.
4. loader와 interpreter가 한 함수/한 모듈로 뒤섞여 있지 않다.
5. `payment_success` 같은 미합의 필드가 도입되지 않았다.
6. 생성한 모듈들이 import 가능하다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- loader 단위 테스트 또는 JSONL fixture 기반 최소 smoke test
- semantic mapping 단위 테스트

단, Task 4 후보 추출이나 Task 5 raw fallback까지 앞당겨 구현하지 마라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 3 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0, Task 1 기록을 지우지 마라.
- Task 1 계약을 최소 보정했다면, 무엇을 왜 바꿨는지 분명히 적어라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- 입력 row DTO는 최소 구조를 유지한다.
- 해석 책임은 semantic mapping 계층에만 있다.
- `S3_CHALLENGE_HALTED`는 비사용으로 분리된다.
- Task 4가 소비할 수 있는 `analysis_input`이 준비된다.
- Task 3 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 4. SessionSummary 집계기 + candidate 추출기 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 4`만 수행한다. 목적은 규칙 기반 분석의 첫 번째 실제 산출물인 `candidate_sessions`를 생성해서, LLM 이전 단계에서 어떤 세션을 분석 대상으로 넘길지 확정하는 것이다.

이 task는 직렬 구간이다. 반드시 Task 3 완료 상태를 전제로 하고, raw fallback/SessionAnalysis/LLM/DB 저장 범위까지 확장하지 마라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, 후보 집계기와 candidate hard filter 범위를 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 3 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/10-post-review-rules.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/01-service-overview/01-service-overview.md`

그 다음 현재 공통 계약과 Task 3 산출물을 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/issues.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/loader.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/semantic_mapping.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/interpreter.py`

Task 3가 `AnalysisInput`을 최소 보정했다면 그 계약을 존중하고, 여기서 다시 크게 흔들지 마라.

## 목적
- `analysis_input`을 `session_id` 기준으로 집계한다.
- `SessionSummary` 필드를 문서 기준으로 산출한다.
- 현재 합의된 최소 candidate hard filter만 적용한다.
- `session_summaries`와 `candidate_sessions`를 분리된 산출물로 만든다.
- candidate 0건이어도 구조를 유지하고 warning만 남긴다.

## 구현 범위
- `session_id` 기준 집계
- `SessionSummary` 필드 산출
- candidate 최소 규칙 적용
- candidate 0건 warning 처리
- `session_summaries`
- `candidate_sessions`

## 구현 제외
- raw fallback 조회
- `SessionAnalysis` 생성
- LLM 호출
- DB 저장
- backend 전달
- export 생성
- semantic mapping 규칙 자체 재설계

## 입력
- `analysis_input`
- semantic interpreter
- Task 1 공통 계약 코드

## 출력
- `session_summaries`
- `candidate_sessions`

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/01-service-overview/*`
- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/issues.py`

## 권장 구현 방향
Task 3 산출물을 소비하는 최소 집계 계층을 만들고, 필요하면 아래 정도의 구조를 우선 검토하라.

- `analysis/__init__.py`
- `analysis/session_summary.py` 또는 `analysis/candidates.py`

정확한 파일명은 조금 달라도 되지만, 집계 로직과 hard filter를 한 곳에서 읽기 좋게 유지하라. semantic mapping 구현을 여기서 다시 풀어헤치지 마라.

## 작업 지침
1. Task 3 로그와 코드를 먼저 확인하라.
   - `analysis_input` 형태
   - semantic mapping/interpreter 경계
   - event 분류 구조
   - `S3_CHALLENGE_HALTED` 비사용 처리
2. 집계는 `session_id` 기준으로만 수행하라.
   - `session_id` 없는 row를 임의 보정해 세션에 끼워 넣지 마라.
   - 누락 row는 필요하면 warning/error 맥락으로만 남겨라.
3. `SessionSummary`는 Task 1 공통 DTO를 재사용하라.
   - 새 summary 타입을 만들지 마라.
   - 필드는 `21-data-contract.md`의 최소 구조를 그대로 따른다.
4. `latest_flow_state`, `latest_action`, `latest_tier`, `terminal_outcome`은 Task 3 semantic mapping/interpreter 결과를 통해서만 산출하라.
   - raw payload를 Task 4에서 다시 직접 해석하지 마라.
5. candidate hard filter는 아래 합의 규칙만 사용하라.
   - `seen_t1 || seen_t2`
   - `block_event_count == 0`
   - `latest_action != BLOCK`
   - `latest_tier != T3`
   - `terminal_outcome == NOT_BLOCKED`
6. 아래 규칙은 다시 끌어오지 마라.
   - `payment_success`
   - 결제 단계 도달 여부
   - payment stage
   - 상위 문서의 F 상태 설명을 hard filter처럼 재해석한 조건
   - 기타 비정의 heuristic
7. `session_summaries`와 `candidate_sessions`는 구분해서 유지하라.
   - `session_summaries`는 집계 결과 전체다.
   - `candidate_sessions`는 hard filter를 통과한 subset이다.
8. candidate가 0건이어도 실패 처리하지 마라.
   - 구조는 그대로 유지하라.
   - `PipelineIssue` warning을 남기되 error/fatal로 올리지 마라.
9. 집계 순서와 결과 순서는 재현 가능해야 한다.
   - session 순서나 최신 이벤트 선택 기준을 코드에서 명확히 하라.
   - 동일 입력에서 동일 결과가 나와야 한다.
10. Task 4에서는 `SessionAnalysis`를 만들지 마라.
   - timeline summary
   - suspicious signals
   - raw fallback
   - `needs_raw_fallback`
   이 네 가지는 Task 5 범위다.
11. DB 저장, backend 전달, export 생성, workflow 호출을 넣지 마라.

## 최소 고정 대상
아래 항목은 Task 5 이후가 다시 설계하지 않도록 이번에 고정해야 한다.

1. `session_id` 기준 집계 방식
2. `SessionSummary` 산출 방식
3. candidate hard filter
4. `session_summaries`와 `candidate_sessions`의 관계
5. candidate 0건 warning 처리 방식

## 검증
작업 후 최소 아래를 검증하라.

1. `candidate_sessions`가 최초 생성된다.
2. `seen_t1 || seen_t2`, `NOT_BLOCKED` 등 현재 합의 규칙만 사용한다.
3. `payment_success`나 비정의 필드가 후보 조건에 들어가지 않았다.
4. candidate 0건이어도 warning만 남기고 구조는 유지된다.
5. `SessionSummary`가 Task 1 공통 DTO를 재사용한다.
6. 생성한 모듈들이 import 가능하다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- candidate 집계 단위 테스트
- candidate 0건 warning 케이스 테스트

단, Task 5 범위인 `SessionAnalysis` 생성이나 raw fallback까지 앞당겨 구현하지 마라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 4 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0~3 기록을 지우지 마라.
- candidate 0건 처리 방식을 왜 warning으로 둔 것인지 로그에 남겨라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- `candidate_sessions`가 최초 생성된다.
- `seen_t1 || seen_t2`, `NOT_BLOCKED` 등 현재 합의 규칙만 사용한다.
- candidate가 0건이어도 warning만 남기고 구조는 유지한다.
- Task 4 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 5. raw fallback 조회기 + SessionAnalysis 생성기 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 5`만 수행한다. 목적은 `candidate_sessions`를 LLM 입력 직전 분석 객체인 `session_analysis_list`로 변환해서, Node 4가 바로 소비할 수 있는 `SessionAnalysis` 최소 구조를 완성하는 것이다.

이 task는 Task 4 완료 상태를 전제로 한다. 세션별 내부 병렬은 허용되지만, 이번 프롬프트에서는 Task 5 범위만 수행한다. LLM 입력 빌더, 최종 레이블, DB 저장, workflow 조립으로 확장하지 마라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, raw fallback 경계와 `SessionAnalysis` 생성 범위를 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 4 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/10-post-review-rules.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/30-ops-and-checks.md`

그 다음 현재 공통 계약과 앞선 task 산출물을 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/loader.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/semantic_mapping.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/interpreter.py`
- `src/traffic_master_ai/defense/backoffice_copilot/analysis/session_summary.py`
- `src/traffic_master_ai/defense/backoffice_copilot/analysis/candidates.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`

Task 4가 만든 candidate 집계 계약을 존중하고, 여기서 candidate hard filter를 다시 정의하지 마라.

## 목적
- `candidate_sessions`를 `SessionAnalysis` 최소 구조로 변환한다.
- 필요한 경우에만 제한적 raw fallback을 수행한다.
- `timeline_summary`, `suspicious_signals`, `needs_raw_fallback`를 문서 기준으로 생성한다.
- `SessionAnalysis`를 저장 가능한 JSON 구조로 유지한다.
- `session_analysis_list`를 Task 6이 바로 소비할 수 있는 형태로 완성한다.

## 구현 범위
- `decision_audit` 제한 조회
- `session_id + time window` 제약
- `timeline_summary`
- `suspicious_signals`
- `needs_raw_fallback`
- `SessionAnalysis` 최소 구조 생성
- candidate 세션별 내부 병렬 처리

## 구현 제외
- LLM input builder
- 최종 레이블 생성
- DB 저장
- backend 전달
- export 생성
- workflow 조립
- candidate hard filter 재설계

## 입력
- `candidate_sessions`
- `analysis_input`
- optional raw fallback rows
- Task 1 공통 계약 코드
- Task 3 semantic mapping/interpreter 계층

## 출력
- `session_analysis_list`

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/*`
- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/semantic_mapping.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`

## 권장 구현 방향
Task 4 집계 결과를 소비하는 최소 분석 계층을 만들고, 필요하면 아래 정도의 구조를 우선 검토하라.

- `analysis/__init__.py`
- `analysis/session_analysis.py`
- `analysis/raw_fallback.py` 또는 `analysis/fallback.py`

정확한 파일명은 조금 달라도 되지만, raw fallback 조회기와 `SessionAnalysis` 조립기를 한 덩어리 거대 함수로 만들지 마라. 조회 경계와 분석 조립 경계가 분리돼야 한다.

## 작업 지침
1. Task 4 로그와 코드를 먼저 확인하라.
   - `candidate_sessions` 산출 방식
   - `session_summaries`와 `candidate_sessions`의 관계
   - candidate 0건 warning 처리 방식
2. `SessionAnalysis`는 Task 1 공통 DTO를 재사용하라.
   - 새 analysis 타입을 만들지 마라.
   - 필드는 `21-data-contract.md`의 최소 구조를 그대로 따른다.
3. `latest_flow_state`, `latest_action`, `latest_tier`, `terminal_outcome`, `seen_t1`, `seen_t2`, `vqa_fail_count`, `throttle_event_count`는 이미 존재하는 candidate/semantic mapping 결과를 우선 재사용하라.
   - Task 5에서 raw payload 전체를 다시 장황하게 재해석하지 마라.
4. raw fallback은 아래 조건에서만 수행하라.
   - payload 파싱 실패
   - semantic mapping 이후에도 핵심 해석 필드 누락
   - 근거 요약 생성에 필요한 문맥 부족
5. raw fallback 조회는 반드시 제한 조회만 허용한다.
   - `session_id` 제한 필수
   - `time window` 제한 필수
   - 전량 스캔 금지
   - `decision_audit` 전체 스캔, 넓은 prefix 조회, 전체 match 단위 재조회 금지
6. `needs_raw_fallback`는 의미 있게 유지하라.
   - fallback이 필요하지 않은 세션에 무조건 true를 주지 마라.
   - fallback을 시도했더라도 해결되지 않은 부족 문맥은 그대로 드러나게 하라.
7. `timeline_summary`와 `suspicious_signals`는 규칙 기반으로 생성하라.
   - 입력 근거 밖 추측 금지
   - 문자열 배열 구조 유지
   - 빈 배열을 허용할지 여부는 문서 최소 구조와 실제 근거량을 기준으로 판단하되, 무의미한 placeholder 문구를 채우지 마라.
8. `SessionAnalysis`는 저장 가능한 JSON 구조여야 한다.
   - `storage/validators.py`의 최소 구조 검증과 충돌하지 않게 유지하라.
   - dataclass 안에 비직렬화 객체, callable, 복잡한 enum 객체를 넣지 마라.
9. candidate 세션별 내부 병렬은 허용된다.
   - 단, bounded 방식으로 유지하라.
   - 출력 순서는 재현 가능해야 한다.
   - 동일 입력에서 동일 `session_analysis_list` 순서가 나오게 하라.
10. Task 5에서는 아래를 하지 마라.
   - LLM input DTO 생성
   - `review_result` 생성
   - `evidence_summary` 생성
   - DB 저장
   - backend 전달
11. `payment_success`, 결제 단계 도달 여부, payment stage 같은 미합의 필드를 다시 끌어오지 마라.
12. raw fallback이 불가능하거나 데이터가 부족해도 전체 task를 즉시 실패로 몰지 마라.
   - 해당 세션의 `needs_raw_fallback`, `timeline_summary`, `suspicious_signals`에 문맥 부족이 드러나도록 처리하라.
   - 단, silent fail은 금지다.

## 최소 고정 대상
아래 항목은 Task 6 이후가 다시 설계하지 않도록 이번에 고정해야 한다.

1. raw fallback 트리거 조건
2. `decision_audit` 제한 조회 경계
3. `needs_raw_fallback` 처리 방식
4. `timeline_summary` 생성 방식
5. `suspicious_signals` 생성 방식
6. `SessionAnalysis` 조립 방식

## 검증
작업 후 최소 아래를 검증하라.

1. LLM 입력 직전 분석 객체가 문서 최소 구조대로 완성된다.
2. full raw scan이 없다.
3. raw fallback은 `session_id + time window` 제한 조회만 사용한다.
4. `SessionAnalysis`가 저장 가능한 JSON 구조다.
5. `payment_success` 같은 미합의 필드가 도입되지 않았다.
6. 생성한 모듈들이 import 가능하다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- `SessionAnalysis` 단위 테스트
- raw fallback 제한 조회 경계 테스트
- `storage.validators.validate_session_analysis_json(...)` 호환 smoke test

단, Task 6 범위인 LLM input builder나 최종 레이블 생성까지 앞당겨 구현하지 마라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 5 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0~4 기록을 지우지 마라.
- raw fallback을 언제 트리거했고, 어떤 제한을 걸었는지 로그에 남겨라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- LLM 입력 직전 분석 객체가 문서 최소 구조대로 완성된다.
- full raw scan이 없다.
- raw fallback은 제한 조회만 사용한다.
- `SessionAnalysis`는 저장 가능한 JSON 구조다.
- Task 5 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 6. LLM 입력 빌더 + 출력 검증기 + 세션별 fallback 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 6`만 수행한다. 목적은 세션별 `review_result`, `evidence_summary`를 생성해서 `review_results`를 확정하고, 이후 저장기와 요약 생성기가 그대로 소비할 수 있도록 만드는 것이다.

이 task는 반드시 Task 5 완료 상태를 전제로 한다. 세션별 bounded concurrency는 허용되지만, 이번 프롬프트에서는 Task 6 범위만 수행한다. 3줄 summary 생성, DB 저장, backend 전달, workflow 조립까지 확장하지 마라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, LLM 입력/출력 계약과 fallback 경계를 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 5 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/00-core-rules.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/10-post-review-rules.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`
8. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/30-ops-and-checks.md`

그 다음 현재 공통 계약과 앞선 task 산출물을 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/issues.py`
- `src/traffic_master_ai/defense/backoffice_copilot/analysis/session_analysis.py`
- `src/traffic_master_ai/defense/backoffice_copilot/analysis/fallback.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`

Task 5가 만든 `session_analysis_list` 계약을 존중하고, 여기서 `SessionAnalysis` 구조를 다시 흔들지 마라.

## 목적
- `SessionAnalysis`를 `LlmReviewInput`으로 변환하는 빌더를 만든다.
- LLM 출력 파서/검증기로 허용 레이블과 필수 필드를 강제한다.
- 입력 근거 밖 추측을 막는 경계를 코드로 고정한다.
- LLM 실패나 출력 불량 시 세션별 fallback으로 `review_result`, `evidence_summary`를 생성한다.
- `review_results`를 Task 8 저장기와 Task 7 summary 생성기가 소비할 수 있는 형태로 확정한다.

## 구현 범위
- LLM input DTO builder
- LLM caller/adapter 경계
- LLM output parser/validator
- 허용 레이블 강제
- hallucination 방지 가드
- 세션별 fallback
- bounded concurrency
- `review_results`

## 구현 제외
- 3줄 summary 생성
- DB 저장
- backend 전달
- export 생성
- workflow 조립
- 모델 선택/외부 provider 운영 설정 확장

## 입력
- `match_id`
- `window_start_ms`
- `window_end_ms`
- `session_analysis_list`
- Task 1 공통 계약 코드

## 출력
- `review_results`

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/*`
- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/issues.py`

## 권장 구현 방향
기존 공통 계약을 재사용하는 선에서 아래와 같은 최소 review 계층을 우선 검토하라.

- `review/__init__.py`
- `review/input_builder.py`
- `review/output_parser.py`
- `review/fallback.py`
- `review/executor.py` 또는 `review/service.py`

정확한 파일명은 조금 달라도 되지만, 입력 빌더, 출력 검증, fallback, 실행기를 한 함수에 몰아넣지 마라. LLM adapter 경계와 규칙 기반 fallback 경계가 분리돼야 한다.

## 작업 지침
1. Task 5 로그와 코드를 먼저 확인하라.
   - `session_analysis_list` 구조
   - `needs_raw_fallback` 의미
   - `timeline_summary`, `suspicious_signals` 생성 방식
2. LLM 입력은 Task 1의 `LlmReviewInput` DTO를 재사용하라.
   - 새 LLM 입력 타입을 만들지 마라.
   - 필드는 `match_id`, window, `session_analysis`, 고정 task envelope만 사용하라.
3. LLM 출력은 Task 1의 `LlmReviewOutput` DTO를 재사용하라.
   - 허용 레이블은 정확히 `NORMAL`, `SUSPICIOUS` 둘뿐이다.
   - 그 외 레이블은 reject하고 fallback으로 전환하라.
   - `evidence_summary` 빈 문자열, 공백 문자열, 누락 값은 reject하라.
4. 입력 근거 밖 추측 금지를 코드 경계로 반영하라.
   - 출력 검증에서 최소한 아래를 막아야 한다.
   - 허용되지 않은 레이블
   - 빈 `evidence_summary`
   - 구조 불일치
   - 명백한 비정상 응답
   - 단, 자연어 진술의 진위 전체를 완벽 검증하려는 과도한 NLP 검사는 넣지 마라.
5. LLM caller는 adapter 경계로만 만들라.
   - 외부 provider SDK/네트워크 결합을 강하게 박아 넣지 마라.
   - 호출 인터페이스를 작게 두고, 실제 provider 주입이 가능하게 하라.
   - provider가 없거나 호출 실패해도 fallback 경로가 있어야 한다.
6. fallback은 세션별로 독립 적용하라.
   - LLM 호출 실패
   - 출력 파싱 실패
   - 허용 레이블 위반
   - 빈 `evidence_summary`
   - 타임아웃/예외
   위 경우에는 규칙 기반 `review_result`와 템플릿 `evidence_summary`를 생성하라.
7. fallback 사용 이력은 추적 가능해야 한다.
   - `SessionReviewResult` 스키마를 undocumented field로 확장하지 마라.
   - 대신 `PipelineIssue` warning 또는 동등한 기존 상태 경로에 `session_id`, 실패 이유, fallback 적용 여부를 남겨라.
8. bounded concurrency는 허용된다.
   - 세션별 병렬 처리만 허용
   - 동시성 상한은 명시적으로 드러내라.
   - 출력 순서는 재현 가능해야 한다.
   - 동일 입력에서 동일 `review_results` 순서가 나오게 하라.
9. `review_results`는 Task 1의 `SessionReviewResult`를 재사용하라.
   - 새 결과 DTO를 만들지 마라.
10. Task 6에서는 아래를 하지 마라.
   - `summary_text` 생성
   - DB row 조립/저장
   - backend payload 생성/전달
   - 최종 run status 분류
11. `payment_success`, payment stage, runtime 판정 재정의 같은 미합의 규칙을 fallback 로직에 다시 끌어오지 마라.
12. silent fail은 금지다.
   - 세션 단위 실패가 발생해도 fallback 또는 warning으로 추적 가능해야 한다.

## 최소 고정 대상
아래 항목은 Task 7~8이 다시 설계하지 않도록 이번에 고정해야 한다.

1. LLM input builder 경계
2. LLM output parser/validator 경계
3. 허용 레이블 강제 규칙
4. fallback 트리거와 fallback 산출 방식
5. bounded concurrency 실행 방식
6. `review_results` 조립 방식

## 검증
작업 후 최소 아래를 검증하라.

1. `review_result`는 `NORMAL`/`SUSPICIOUS` 둘 중 하나다.
2. LLM 실패 시에도 fallback으로 결과를 만든다.
3. 허용 레이블 외 결과는 reject된다.
4. 빈 `evidence_summary`는 reject된다.
5. fallback 사용 이력이 추적 가능하다.
6. 생성한 모듈들이 import 가능하다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- output parser 단위 테스트
- fallback 단위 테스트
- bounded concurrency smoke test

단, Task 7 범위인 3줄 summary 생성이나 Task 8 범위인 저장/전달까지 앞당겨 구현하지 마라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 6 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0~5 기록을 지우지 마라.
- 어떤 경우에 fallback으로 전환했는지, 어떤 형태로 추적 가능하게 했는지 로그에 남겨라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- `review_result`는 `NORMAL`/`SUSPICIOUS` 둘 중 하나다.
- LLM 실패 시에도 fallback으로 결과를 만든다.
- 허용 레이블 외 결과는 reject된다.
- `review_results`가 저장기와 요약 생성기가 소비할 수 있는 구조로 완성된다.
- Task 6 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 7. Window summary 생성기 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 7`만 수행한다. 목적은 시간 구간 3줄 요약인 `summary_text`를 독립 모듈로 구현해서, Task 8 저장기가 이를 소비만 하도록 만드는 것이다.

이 task는 반드시 Task 6 완료 상태를 전제로 한다. 이번 프롬프트에서는 Task 7 범위만 수행한다. DB 저장, backend 전달, export 생성, run row 조립으로 확장하지 마라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, window summary 생성 범위와 Task 8과의 경계를 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 6 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/00-core-rules.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/01-service-overview/01-service-overview.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`
8. `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/11-review-output-rules.md`

그 다음 현재 공통 계약과 앞선 task 산출물을 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/issues.py`
- `src/traffic_master_ai/defense/backoffice_copilot/review/service.py`
- `src/traffic_master_ai/defense/backoffice_copilot/review/fallback.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`

Task 6이 만든 `review_results` 계약을 존중하고, 여기서 세션별 레이블링 로직을 다시 정의하지 마라.

## 목적
- `review_results`, `session_analysis_list`, run context를 요약 입력으로 조립한다.
- 항상 길이 3의 `summary_text`를 생성한다.
- LLM 실패 시 template fallback으로 3줄 요약을 만든다.
- `summary_text`를 Task 8이 그대로 소비할 수 있는 구조로 고정한다.
- 요약 생성기를 저장기와 독립된 모듈로 유지한다.

## 구현 범위
- summary 입력 조립
- 3줄 요약 생성
- 길이 3 검증
- LLM 실패 시 template fallback
- `summary_text`

## 구현 제외
- DB 저장
- backend 전달
- export 생성
- run row 조립
- 최종 status 분류
- Task 8 저장 로직과 결합

## 입력
- `review_results`
- `session_analysis_list`
- `match_id`
- `window_start_ms`
- `window_end_ms`

## 출력
- `summary_text`

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/01-service-overview/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`

## 권장 구현 방향
Task 6 산출물을 소비하는 최소 summary 계층을 만들고, 필요하면 아래 정도의 구조를 우선 검토하라.

- `summary/__init__.py`
- `summary/input_builder.py`
- `summary/window_summary.py`
- `summary/fallback.py`

정확한 파일명은 조금 달라도 되지만, summary 생성 로직을 Task 8 저장기 안에 넣지 마라. summary 생성기와 저장기는 별도 모듈이어야 한다.

## 작업 지침
1. Task 6 로그와 코드를 먼저 확인하라.
   - `review_results` 구조
   - fallback 추적 방식
   - `SessionReviewResult`와 `SessionAnalysis` 관계
2. `summary_text`는 정확히 길이 3의 문자열 배열이어야 한다.
   - 길이 2, 길이 4, 단일 문자열, dict 형태는 모두 금지다.
   - `storage.validators.validate_summary_text_json(...)`와 충돌하지 않게 유지하라.
3. summary 입력은 기존 산출물을 조합해서 만들라.
   - `review_results`
   - `session_analysis_list`
   - `match_id`
   - window
   - 필요 시 candidate/suspicious count는 위 입력에서 파생 계산하라.
   - Task 8 저장 row를 미리 만들기 위해 summary 생성 로직을 거꾸로 끌어오지 마라.
4. 요약 생성은 독립 모듈로 유지하라.
   - Task 8은 이 산출물을 소비만 해야 한다.
   - 저장기 안으로 요약 생성 로직을 흡수하지 마라.
5. LLM 기반 summary 생성이 있다면, 입력 근거 밖 추측 금지를 유지하라.
   - 입력에 없는 사실 생성 금지
   - 과도한 서사적 문장 금지
   - 저장/전달 상태 같은 Task 8 이후 정보 선반영 금지
6. LLM 실패 시 template fallback을 제공하라.
   - fallback이어도 길이 3은 반드시 맞춰라.
   - 무의미한 placeholder 대신, 현재 run의 실제 집계와 세션 결과를 반영한 단순 템플릿을 사용하라.
7. `summary_text`는 run-level 요약이다.
   - 개별 세션 상세를 장황하게 나열하지 마라.
   - suspicious 수, 후보 수, 전반적 특이점 같은 window-level 관점으로 유지하라.
8. Task 7에서는 아래를 하지 마라.
   - DB row 생성
   - export 필드 매핑
   - backend payload 생성
   - 최종 run status 계산
9. silent fail은 금지다.
   - summary 생성 실패 시 fallback 또는 명시적 warning 경로가 있어야 한다.
10. summary가 3줄을 못 맞추는 상황을 허용하지 마라.
   - 검증에서 reject하고 fallback 또는 보정으로 길이 3을 맞춰라.

## 최소 고정 대상
아래 항목은 Task 8 이후가 다시 설계하지 않도록 이번에 고정해야 한다.

1. summary 입력 조립 경계
2. 3줄 요약 생성 방식
3. 길이 3 검증 규칙
4. template fallback 방식
5. `summary_text` 소비 경계

## 검증
작업 후 최소 아래를 검증하라.

1. 항상 길이 3의 summary를 반환한다.
2. LLM 실패 시 template fallback이 동작한다.
3. `summary_text`가 `storage.validators.validate_summary_text_json(...)`와 호환된다.
4. summary 생성 로직이 저장기와 분리돼 있다.
5. 생성한 모듈들이 import 가능하다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- summary 길이 3 단위 테스트
- fallback 단위 테스트
- validator 호환 smoke test

단, Task 8 범위인 저장/전달/DB 기반 export까지 앞당겨 구현하지 마라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 7 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0~6 기록을 지우지 마라.
- 왜 summary 생성기를 저장기와 분리했는지, fallback이 어떤 형식인지 로그에 남겨라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- 항상 길이 3의 summary를 반환한다.
- LLM 실패 시 template fallback이 동작한다.
- `Task 8`은 이 산출물을 소비만 한다.
- Task 7 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 8. 결과 저장기 + backend payload 생성기 + export 생성기 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 8`만 수행한다. 목적은 Node 6 계약대로 DB-first 저장을 수행하고, suspicious-only backend payload와 DB 기반 export를 생성해서 최종 결과 산출 단계를 완성하는 것이다.

이 task는 반드시 Task 2, Task 6, Task 7 완료 상태를 전제로 한다. 이번 프롬프트에서는 Task 8 범위만 수행한다. 외부 backend 실제 구현, Discord/Grafana 실제 연동, 최종 status 분류까지 확장하지 마라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, DB-first 저장과 suspicious-only 전달 경계를 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 2, Task 6, Task 7 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/10-post-review-rules.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/11-review-output-rules.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`
8. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/30-ops-and-checks.md`

그 다음 현재 공통 계약과 앞선 task 산출물을 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`
- `src/traffic_master_ai/defense/backoffice_copilot/review/service.py`
- `src/traffic_master_ai/defense/backoffice_copilot/summary/window_summary.py`

Task 2 저장소 경계와 Task 7 `summary_text` 계약을 존중하고, 여기서 저장기 안으로 요약 생성 로직을 다시 끌어오지 마라.

## 목적
- run row와 session row를 DB-first 기준으로 조립/저장한다.
- suspicious 세션만 backend payload로 변환한다.
- backend adapter 경계 호출 결과를 `backend_delivery_status`에 반영한다.
- DB row 기반으로 optional export를 생성한다.
- `post_review_runs_row`, `post_review_session_result_rows`, `backend_request`, `backend_response`를 graph state에 남긴다.

## 구현 범위
- run row 조립/저장
- session row 조립/저장
- `backend_request` 생성
- adapter boundary 호출
- `backend_response` 반영
- `backend_delivery_status` 갱신
- DB 기반 export 생성
- optional export files

## 구현 제외
- 외부 backend 실제 구현
- Discord/Grafana 실제 연동
- 최종 status 분류
- validator skeleton 전체 완성
- workflow 조립

## 입력
- Task 2 저장 계층
- `review_results`
- `summary_text`
- `session_analysis_list`
- `candidate_sessions`
- run context (`match_id`, `window_start_ms`, `window_end_ms`)

## 출력
- DB rows
- `backend_request`
- `backend_response`
- optional export files

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/*`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`

## 권장 구현 방향
기존 저장소 계층과 공통 DTO를 재사용하는 선에서 아래 정도의 최소 output 계층을 우선 검토하라.

- `output/__init__.py`
- `output/persistence.py`
- `output/backend_adapter.py`
- `output/exporter.py`

정확한 파일명은 조금 달라도 되지만, row 조립/저장, backend payload 처리, export 생성을 한 거대 함수로 합치지 마라. 책임 경계가 보이도록 분리하라.

## 작업 지침
1. Task 2, Task 6, Task 7 로그와 코드를 먼저 확인하라.
   - write repository 경계
   - `review_results` 구조
   - `summary_text` 길이 3 보장
   - `SessionAnalysis` 저장 호환성
2. DB 저장은 항상 export보다 먼저다.
   - `post_review_runs` 저장
   - `post_review_session_results` 저장
   - 그 다음 필요 시 export 생성
   - DB 저장 실패 상태에서 export 성공만으로 완료 처리하지 마라.
3. run row는 Task 1의 `PostReviewRunRecord`를 재사용하라.
   - `match_id`
   - window
   - `candidate_count`
   - `suspicious_count`
   - `summary_text_json`
   - `status`
4. session row는 Task 1의 `PostReviewSessionResultRecord`를 재사용하라.
   - `review_result`
   - `evidence_summary`
   - `session_analysis_json`
   - `backend_delivery_status`
5. row 조립 시 허용값과 JSON 구조는 Task 2 validator를 그대로 사용하라.
   - `status`
   - `review_result`
   - `backend_delivery_status`
   - `summary_text_json`
   - `session_analysis_json`
6. `suspicious_count`는 `review_results`의 `SUSPICIOUS` 수와 일치해야 한다.
   - run row와 session row 정합성을 여기서 맞춰라.
7. backend payload는 suspicious-only다.
   - `review_result='SUSPICIOUS'` 세션만 `Backend request DTO` 후보로 변환하라.
   - `NORMAL` 세션을 backend payload에 포함하지 마라.
8. backend는 adapter boundary까지만 구현하라.
   - request DTO 생성
   - adapter 호출 인터페이스
   - response DTO 반영
   - `backend_delivery_status` 갱신
   - 외부 backend 서버/API 자체 구현은 범위 밖이다.
9. `backend_delivery_status`는 전달 상태를 정확히 반영하라.
   - 전달 전 기본값
   - 성공 시 갱신
   - 실패 시 갱신
   - 전달 시도 세션에서 비어 있으면 안 된다.
10. export는 DB row 기반 후속 산출물이다.
   - `summary.json`
   - `suspicious_sessions.jsonl`
   - `suspicious_sessions.csv`
   - export는 저장된 DB row를 기준으로 만들고, 저장 전 임시 집계를 다시 따로 신뢰하지 마라.
11. export 필터는 suspicious-only를 유지하라.
   - suspicious export는 `review_result='SUSPICIOUS'` row만 포함
12. Task 8에서는 아래를 하지 마라.
   - 외부 backend 서버/API 구현
   - Discord/Grafana 실제 연동
   - 최종 run status resolver 완성
   - summary 생성 로직 재구현
13. silent fail은 금지다.
   - 저장 실패는 명시적 오류
   - backend 전달 실패는 상태 기록 후 드러나야 함
   - export 실패는 정책에 따라 warning으로 남기되, DB 저장 성공 사실과 분리해서 다뤄라

## 최소 고정 대상
아래 항목은 Task 9b와 Task 10이 다시 설계하지 않도록 이번에 고정해야 한다.

1. run row 조립 방식
2. session row 조립 방식
3. suspicious-only backend payload 생성 방식
4. adapter boundary 호출/응답 반영 방식
5. `backend_delivery_status` 갱신 방식
6. DB 기반 export 생성 방식

## 검증
작업 후 최소 아래를 검증하라.

1. DB-first 저장이 성공한다.
2. 전달 대상은 `SUSPICIOUS`만이다.
3. `Task 7` 산출물을 그대로 소비한다.
4. `summary_text_json`은 길이 3 배열로 저장된다.
5. `backend_delivery_status`는 전달 시도 세션에서 비어 있지 않다.
6. export는 DB 저장 이후 후속 단계로 생성된다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- row 조립 단위 테스트
- suspicious-only backend payload 테스트
- export 매핑 테스트
- 저장소 validator/serializer 호환 smoke test

단, Task 9b 범위인 최종 상태 분류까지 앞당겨 구현하지 마라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 8 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0~7 기록을 지우지 마라.
- DB-first 저장 순서, suspicious-only payload, export 생성 시점을 로그에 분명히 남겨라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- DB-first 저장이 성공한다.
- 전달 대상은 `SUSPICIOUS`만이다.
- `Task 7` 산출물을 그대로 소비한다.
- backend는 payload 생성과 상태 갱신까지만 다룬다.
- export는 DB 저장 이후 후속 단계로 처리된다.
- Task 8 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 9a. 기본 validator 골격 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 9a`만 수행한다. 목적은 후반부에 붙을 실행 상태/운영 검증이 뒤늦게 새지 않도록, 입력/컬럼/허용값/경고-오류 누적의 최소 validator skeleton과 validation interface를 먼저 고정하는 것이다.

이 task는 반드시 Task 1, Task 2 완료 상태를 전제로 한다. Task 3 이후 세부 확장은 가능하지만, 이번 프롬프트에서는 Task 9a 범위만 수행한다. 최종 status resolver, stage별 실제 결과 집계, workflow 조립까지 확장하지 마라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, skeleton 단계에서 무엇을 고정하고 무엇을 남겨둘지 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 1, Task 2 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/30-ops-and-checks.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/11-review-output-rules.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/00-core-rules.md`

그 다음 현재 공통 계약과 저장 계층의 validation helper를 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/issues.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/repository.py`

Task 2에서 이미 고정한 저장 전 컬럼/허용값/JSONB helper를 존중하고, 여기서 같은 검증을 중복 구현해 두 겹으로 꼬이게 만들지 마라.

## 목적
- 입력 파라미터 validator skeleton을 만든다.
- DB 컬럼 validator skeleton을 만든다.
- allowed value validator skeleton을 만든다.
- warnings/errors container skeleton을 만든다.
- Task 9b가 확장할 validation/report interface를 고정한다.

## 구현 범위
- 입력 파라미터 validator 골격
- DB 컬럼 validator 골격
- allowed value validator 골격
- warnings/errors container 골격
- validation report 또는 이에 준하는 상태/검증 인터페이스

## 구현 제외
- 최종 status 분류 완성
- stage별 실제 결과 집계 완성
- export 실패 정책 최종 반영
- backend 전달 성공/실패 해석 완성
- workflow 조립

## 입력
- Task 1 공통 계약
- Task 2 저장 계층
- 문서의 allowed value / column rule

## 출력
- validator skeleton
- 상태/검증 인터페이스

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`

## 권장 구현 방향
Task 2 저장 helper 위에 얇은 validation orchestration skeleton을 얹는 선에서 아래 정도의 최소 구조를 우선 검토하라.

- `validation/__init__.py`
- `validation/input_checks.py` 또는 `validation/params.py`
- `validation/db_checks.py`
- `validation/allowed_values.py`
- `validation/report.py`

정확한 파일명은 조금 달라도 되지만, 실제 run status resolver와 stage 집계를 미리 다 구현하는 거대 모듈로 만들지 마라. Task 9b가 확장할 자리를 명시적으로 남겨라.

## 작업 지침
1. Task 1, Task 2 로그와 코드를 먼저 확인하라.
   - `RunStatus`
   - `ReviewResult`
   - `BackendDeliveryStatus`
   - `PostReviewRunRecord`
   - `PostReviewSessionResultRecord`
   - `storage/validators.py`의 기존 helper 범위
2. Task 9a는 skeleton 단계다.
   - 최종 status resolver까지 한 번에 끝내려 하지 마라.
   - stage별 실제 결과 집계나 fatal/partial 판정은 Task 9b로 넘겨라.
3. 입력 파라미터 validator는 graph input 최소 구조를 대상으로 하라.
   - `match_id`
   - `window_start_ms`
   - `window_end_ms`
   - `limit`
   - `use_raw_audit_fallback`
   - 단, 여기서는 “최소 구조와 타입/기본 범위 확인” 수준만 고정하고, 실제 실행 결과 해석은 하지 마라.
4. DB 컬럼 validator skeleton은 Task 8 row 조립 결과가 나중에 연결될 수 있는 인터페이스여야 한다.
   - `post_review_runs` row
   - `post_review_session_results` row
   - 실제 저장 성공/실패 판정 전체는 아직 구현하지 마라.
5. allowed value validator는 문서의 허용값만 다뤄라.
   - `status ∈ {SUCCESS, PARTIAL_SUCCESS, FAILED}`
   - `review_result ∈ {NORMAL, SUSPICIOUS}`
   - `backend_delivery_status ∈ {PENDING, SENT, FAILED}`
   - 가능하면 Task 1 enum 또는 Task 2 helper를 재사용하고, 동일 allowed set을 여러 곳에 하드코딩하지 마라.
6. `storage/validators.py`와 역할을 분리하라.
   - Task 2는 저장 전 컬럼/허용값/JSONB helper다.
   - Task 9a는 그것을 감싸는 validation interface와 report skeleton이다.
   - 저장 helper 로직을 복사해 새 validator 파일에 중복 구현하지 마라.
7. warnings/errors container skeleton은 graph state와 충돌하지 않아야 한다.
   - `core/state.py`와 `core/issues.py`의 기존 구조를 우선 재사용하라.
   - Task 9b에서 warning/error를 누적하고 finalize할 수 있도록 append/merge 경로를 단순하게 남겨라.
8. validation report는 최소한 아래를 표현할 수 있어야 한다.
   - 어떤 check를 수행했는지
   - warning/error가 있는지
   - 후속 Task 9b가 stage/fatal/partial 판단을 붙일 확장 지점
   - 하지만 지금 당장 최종 판정 필드를 강하게 확정하지 마라.
9. 과한 taxonomy를 만들지 마라.
   - validator class, issue class, report class를 여러 단계로 과설계하지 마라.
   - Task 9b 전에 validation framework 자체가 주인공이 되면 범위를 넘는다.
10. Task 9a에서는 아래를 하지 마라.
   - DB 저장 결과 해석 완성
   - backend 전달 결과 해석 완성
   - export 실패 정책 완성
   - workflow graph 연결
11. `payment_success` 같은 미합의 필드나 문서에 없는 validation target을 끌어오지 마라.
12. Task 9b 확장 지점은 코드에서 분명해야 한다.
   - placeholder 함수
   - TODO 수준의 빈 껍데기가 아니라, 실제 import 가능한 skeleton
   - 하지만 반환값/판정은 최소 수준으로만 고정하라.

## 최소 고정 대상
아래 항목은 Task 9b가 다시 설계하지 않도록 이번에 고정해야 한다.

1. validation module boundary
2. graph input validator interface
3. DB row validator interface
4. allowed value validator interface
5. warnings/errors container 또는 report skeleton
6. `storage/validators.py`와의 책임 분리 방식

## 검증
작업 후 최소 아래를 검증하라.

1. 최소 validator skeleton이 존재한다.
2. 후속 `Task 9b`에서 확장 가능한 형태다.
3. `storage/validators.py`와 역할이 중복되지 않는다.
4. 허용값 validator가 문서 allowed set을 기준으로 동작한다.
5. warnings/errors container 또는 report skeleton이 import 가능하다.
6. 생성한 모듈들이 import 가능하다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- graph input validator 최소 단위 테스트
- allowed value validator 최소 단위 테스트
- report/warning container smoke test

단, Task 9b 범위인 최종 상태 분류와 stage별 체크 완성까지 앞당겨 구현하지 마라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 9a 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0~8 기록을 지우지 마라.
- 왜 skeleton까지만 구현했는지, Task 2 helper와 어떻게 책임을 분리했는지 로그에 남겨라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- 최소 validator skeleton이 존재한다.
- 후속 `Task 9b`에서 확장 가능한 형태다.
- `storage/validators.py`와 역할이 중복되지 않는다.
- 최종 status resolver까지 섣불리 구현하지 않는다.
- Task 9a 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 9b. 실행 상태/검증/체크 로직 완성 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 9b`만 수행한다. 목적은 Task 9a에서 만든 validator/check skeleton을 Task 8 실제 산출물 기준으로 완성해서, run의 최종 상태를 `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED` 중 하나로 문서 규칙대로 판정할 수 있게 만드는 것이다.

이 task는 반드시 Task 8, Task 9a 완료 상태를 전제로 한다. 이번 프롬프트에서는 Task 9b 범위만 수행한다. workflow 조립, Node 연결, 전체 통합 테스트 마무리까지 확장하지 마라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, 최종 상태 판정 기준과 fatal/partial 경계를 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 8, Task 9a 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/30-ops-and-checks.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/11-review-output-rules.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`

그 다음 현재 validator skeleton과 Task 8 출력 경계를 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/output/persistence.py`
- `src/traffic_master_ai/defense/backoffice_copilot/output/backend_adapter.py`
- `src/traffic_master_ai/defense/backoffice_copilot/output/exporter.py`

Task 9a에서 만든 skeleton과 Task 8의 실제 저장/전달 결과를 존중하고, 여기서 validation 구조를 새로 갈아엎지 마라.

## 목적
- pre-run checks를 완성한다.
- stage checks를 완성한다.
- fallback checks를 완성한다.
- warning/error 누적을 마감한다.
- fatal/partial 경계를 문서 기준으로 고정한다.
- 최종 run status resolver를 완성한다.

## 구현 범위
- Task 9a validator/check skeleton 확장
- pre-run validation/report 완성
- stage별 validation/check 완성
- fallback check 완성
- fatal/partial/success 분류
- final run status resolver
- warnings/errors finalized

## 구현 제외
- workflow 조립
- Node 간 wiring
- 전체 통합 테스트 마무리
- 저장/전달 로직 자체 재구현
- export 생성기 재설계

## 입력
- Task 9a validator skeleton
- Task 8 저장/전달 결과
- run row
- session rows
- backend response / delivery status
- export 결과 또는 export failure 정보

## 출력
- validation report
- final run status
- finalized warnings/errors

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/validators.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`

## 권장 구현 방향
Task 9a에서 만든 validator/report 구조를 그대로 확장하는 선에서, 아래 정도의 최소 status/check 계층을 우선 검토하라.

- `validation/__init__.py`
- `validation/checks.py`
- `validation/status_resolver.py`
- `validation/report.py`

정확한 파일명은 조금 달라도 되지만, 허용값 검증, stage check, 최종 status 판정을 한 거대 함수에 몰아넣지 마라. skeleton 확장 경로가 보이도록 분리하라.

## 작업 지침
1. Task 9a와 Task 8 로그/코드를 먼저 확인하라.
   - validator skeleton이 어디까지 구현됐는지
   - Task 8이 어떤 저장/전달 결과를 남기는지
   - warning/error 누적 경로가 어디인지
2. Task 9b는 Task 9a 구조를 확장해야 한다.
   - validator skeleton을 버리고 새 체계를 만들지 마라.
   - 함수명, report 타입, 에러 누적 방식이 이미 있으면 최대한 재사용하라.
3. 최종 status는 반드시 Task 8의 실제 결과 기준으로만 판정하라.
   - 저장 결과
   - session row 결과
   - backend 전달 결과
   - export 결과
   - 추정 상태나 미래 workflow 상태를 섞지 마라.
4. `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED` 판정 규칙은 문서를 우선한다.
   - DB 저장 실패는 fatal이다.
   - DB 저장 실패를 warning이나 partial로 낮추지 마라.
   - export 실패는 문서 정책상 partial 또는 warning 처리 가능성을 반영하되, 무조건 fatal로 올리지 마라.
5. `backend_delivery_status` 검증을 완성하라.
   - 전달 시도 세션이면 비어 있으면 안 된다.
   - 허용값은 문서의 allowed set만 사용하라.
   - suspicious-only 전달 정책과 충돌하지 않게 검증하라.
6. stage check는 최소한 아래 경계를 분리하라.
   - 입력/전제조건 체크
   - DB 저장 체크
   - backend 전달 체크
   - export 체크
   - warning/error finalize
7. fallback check는 silent fail을 막는 용도로 완성하라.
   - fallback이 사용된 경우, 해결 여부와 잔여 리스크가 warning/error에 드러나야 한다.
   - fallback 존재 자체를 곧바로 fatal로 올리지 마라.
8. run-level 상태와 session-level 상태를 혼동하지 마라.
   - 일부 suspicious 전달 실패가 있어도 전체 run이 항상 `FAILED`가 되는지 여부는 문서 규칙으로 판단하라.
   - 부분 실패 허용 조건을 코드에 명시적으로 드러내라.
9. warning/error 누적은 최종 판정 전에 마감돼야 한다.
   - 중복 메시지를 무의미하게 쌓지 마라.
   - fatal 근거와 partial 근거를 구분 가능하게 유지하라.
10. Task 9b에서는 아래를 하지 마라.
   - DB 저장 로직 수정
   - backend adapter 자체 재구현
   - export 생성 로직 재작성
   - workflow graph 조립
11. `payment_success` 같은 미합의 필드나, 문서에 없는 임의 상태값을 도입하지 마라.
12. 최종 status resolver는 재현 가능해야 한다.
   - 동일 입력이면 동일 `SUCCESS/PARTIAL_SUCCESS/FAILED`가 나와야 한다.
   - hidden global state나 비결정적 분기를 넣지 마라.

## 최소 고정 대상
아래 항목은 Task 10이 다시 설계하지 않도록 이번에 고정해야 한다.

1. final run status resolver 경계
2. fatal/partial/success 분류 기준
3. DB 저장 실패 fatal 처리
4. export 실패 처리 정책 반영 방식
5. `backend_delivery_status` validation 완성 방식
6. warnings/errors finalize 방식

## 검증
작업 후 최소 아래를 검증하라.

1. `SUCCESS / PARTIAL_SUCCESS / FAILED` 최종 분류가 문서 규칙대로 작동한다.
2. DB 저장 실패는 fatal로 분류된다.
3. partial failure 허용 조건이 반영된다.
4. 전달 시도 세션에서 `backend_delivery_status`가 비어 있으면 검증 실패가 난다.
5. export 실패는 문서 정책에 맞게 warning/partial/fatal 중 올바르게 처리된다.
6. 생성한 모듈들이 import 가능하다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- status resolver 단위 테스트
- DB failure fatal 분류 테스트
- export failure 정책 테스트
- `backend_delivery_status` validation 테스트

단, Task 10 범위인 workflow 조립이나 전체 graph 통합까지 앞당겨 구현하지 마라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 9b 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0~9a 기록을 지우지 마라.
- 어떤 조건을 fatal로 봤는지, 어떤 조건을 partial 허용으로 봤는지 로그에 분명히 남겨라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- `SUCCESS / PARTIAL_SUCCESS / FAILED` 최종 분류가 문서 규칙대로 작동한다.
- DB 저장 실패는 fatal로 처리된다.
- partial failure 허용 조건이 코드와 검증에 반영된다.
- warning/error 누적이 최종 상태 판정 전에 마감된다.
- Task 9b 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 10. LangGraph 파이프라인 조립 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 10`만 수행한다. 목적은 Task 3부터 Task 9b까지 고정한 노드 책임과 상태 흐름을 실제 LangGraph workflow로 조립해서, entrypoint 기준으로 전체 파이프라인이 실행 가능하도록 만드는 것이다.

이 task는 반드시 Task 3, Task 4, Task 5, Task 6, Task 7, Task 8, Task 9b 완료 상태를 전제로 한다. 이번 프롬프트에서는 Task 10 범위만 수행한다. 새 노드 추가, 관리자 API 의존 구조 도입, 외부 delivery 구현까지 확장하지 마라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, 노드 수/순서/입출력/state 전달 경계를 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 3, Task 4, Task 5, Task 6, Task 7, Task 8, Task 9b 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/00-core-rules.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/30-ops-and-checks.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`

그 다음 현재 공통 계약과 각 task 산출 모듈의 public surface를 확인하라.

- `src/traffic_master_ai/defense/backoffice_copilot/core/models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/loader.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/interpreter.py`
- `src/traffic_master_ai/defense/backoffice_copilot/analysis/candidates.py`
- `src/traffic_master_ai/defense/backoffice_copilot/analysis/session_analysis.py`
- `src/traffic_master_ai/defense/backoffice_copilot/review/executor.py`
- `src/traffic_master_ai/defense/backoffice_copilot/summary/window_summary.py`
- `src/traffic_master_ai/defense/backoffice_copilot/output/persistence.py`
- `src/traffic_master_ai/defense/backoffice_copilot/output/backend_adapter.py`
- `src/traffic_master_ai/defense/backoffice_copilot/output/exporter.py`
- `src/traffic_master_ai/defense/backoffice_copilot/validation/checks.py`
- `src/traffic_master_ai/defense/backoffice_copilot/validation/status_resolver.py`

앞선 task가 고정한 책임 경계를 존중하고, workflow 조립을 이유로 각 노드 내부 구현을 다시 섞지 마라.

## 목적
- 문서에 고정된 6개 노드를 실제 workflow로 연결한다.
- graph state 전달 경계를 고정한다.
- warnings/errors propagation을 전체 흐름에 반영한다.
- 내부 병렬 제한이 노드 경계 밖으로 새지 않게 유지한다.
- 실행 가능한 workflow entrypoint를 제공한다.

## 구현 범위
- node wiring
- state 전달
- warnings/errors propagation
- workflow entrypoint
- LangGraph app 또는 동등 실행 엔트리포인트
- 내부 병렬성 제한 반영

## 구현 제외
- 새로운 노드 추가
- 노드 순서 변경
- 관리자 API 의존 구조 도입
- 외부 delivery 구현
- 각 노드 내부 분석/저장/검증 로직 재설계
- 최종 테스트 코드 마감

## 입력
- Task 3 ~ Task 9b 산출물
- graph input (`match_id`, `window_start_ms`, `window_end_ms`, `limit`, `use_raw_audit_fallback`)

## 출력
- workflow entrypoint
- LangGraph app 또는 동등 실행 엔트리포인트
- 문서 계약대로 채워지는 최종 graph state

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/00-core-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`
- `src/traffic_master_ai/defense/backoffice_copilot/core/state.py`

## 권장 구현 방향
기존 task 산출 모듈을 호출하는 얇은 orchestration 계층만 추가하는 선에서 아래 정도의 최소 구조를 우선 검토하라.

- `workflow/__init__.py`
- `workflow/nodes.py`
- `workflow/graph.py`
- `workflow/app.py` 또는 `workflow/entrypoint.py`

정확한 파일명은 조금 달라도 되지만, 노드 구현과 workflow 조립을 한 파일의 거대 함수로 만들지 마라. node wrapper와 graph assembly를 분리하라.

## 작업 지침
1. 노드 수와 노드 순서는 문서에 고정된 6개를 그대로 따른다.
   - Node 1 입력 수집
   - Node 2 후보 세션 추출
   - Node 3 세션 분석
   - Node 4 사후 판단
   - Node 5 운영 요약 생성
   - Node 6 결과 저장/전달
2. 연결 규칙은 문서와 정확히 일치해야 한다.
   - Node1 → Node2
   - Node2 → Node3
   - Node3 → Node4
   - Node4 → Node5
   - Node4 + Node5 → Node6
   - 임의 분기, 우회 경로, 숨은 side path를 넣지 마라.
3. graph 시작 입력은 `match_id` 기준으로 고정하라.
   - `review_run_id`를 다시 끌어오지 마라.
   - graph input validation은 기존 계약을 재사용하라.
4. graph state는 Task 1 계약을 우선 재사용하라.
   - `analysis_input`
   - `candidate_sessions`
   - `session_analysis_list`
   - `review_results`
   - `summary_text`
   - `post_review_runs_row`
   - `post_review_session_result_rows`
   - `backend_request`
   - `backend_response`
   - `warnings`
   - `errors`
5. 각 node wrapper는 해당 task 산출 모듈을 thin wrapper로 호출하는 수준에 머물러야 한다.
   - Node 1에서 semantic mapping 세부 로직을 다시 구현하지 마라.
   - Node 6에서 summary 생성이나 status 분류를 다시 구현하지 마라.
6. `Task 7`과 `Task 8`의 경계를 유지하라.
   - summary 생성은 Node 5 책임이다.
   - 저장/전달은 Node 6 책임이다.
   - 저장기 안에 요약 생성을 흡수하거나, 요약 노드에서 저장 row를 만들지 마라.
7. warnings/errors propagation을 workflow 수준에서 끊지 마라.
   - 각 노드가 반환한 warning/error가 최종 state까지 유지돼야 한다.
   - fatal error가 발생했을 때도 silent swallow는 금지다.
8. 내부 병렬성은 각 노드 내부 경계를 존중하라.
   - Node 3 세션별 병렬
   - Node 4 bounded concurrency
   - workflow 조립 단계에서 이를 다시 전역 병렬 fan-out으로 바꾸지 마라.
9. 중간 persistence를 추가하지 마라.
   - Node 6 이전에 DB 저장 경로를 만들지 마라.
   - 임시 테이블, 중간 파일, cache persistence를 workflow 기본 경로에 넣지 마라.
10. workflow entrypoint는 실제 실행 가능해야 한다.
   - graph input을 받아 최종 state 또는 동등 결과를 반환해야 한다.
   - 노드 import 실패나 누락된 의존성이 있으면 명시적으로 드러나야 한다.
11. Task 10에서는 아래를 하지 마라.
   - 새로운 node 책임 정의
   - 외부 backend 서버/API 구현
   - 관리자 API 의존 구조 추가
   - 테스트 범위인 대규모 fixture 보강
12. 결과는 재현 가능해야 한다.
   - 동일 입력이면 동일 노드 순서로 실행돼야 한다.
   - hidden global state, 암묵적 singleton side effect, 비결정적 node selection을 넣지 마라.

## 최소 고정 대상
아래 항목은 Task 11이 다시 설계하지 않도록 이번에 고정해야 한다.

1. 6개 node wiring 방식
2. graph input/state 전달 경계
3. warnings/errors propagation 방식
4. Node 4 + Node 5 → Node 6 결합 방식
5. workflow entrypoint public surface
6. 중간 persistence 금지 원칙

## 검증
작업 후 최소 아래를 검증하라.

1. 노드 순서가 문서와 일치한다.
2. node count가 정확히 6개로 유지된다.
3. 임의 분기나 중간 persistence가 없다.
4. `match_id` 기반 graph input이 실제 entrypoint에서 동작한다.
5. `Task 7`과 `Task 8`의 경계가 workflow 조립 후에도 유지된다.
6. 생성한 모듈들이 import 가능하다.

가능하면 아래 수준의 검증을 수행하라.

- 대상 패키지 import smoke test
- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot`
- workflow entrypoint smoke test
- graph input → final state 최소 흐름 테스트
- warnings/errors propagation smoke test

단, Task 11 범위인 테스트/검증 코드 최종 마감까지 앞당겨 구현하지 마라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 10 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0~9b 기록을 지우지 마라.
- 어떤 노드 wrapper를 만들었는지, node wiring이 문서와 어떻게 일치하는지, 중간 persistence를 왜 두지 않았는지 로그에 남겨라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- node 순서가 문서와 정확히 일치한다.
- node count가 6개로 유지된다.
- 임의 분기나 중간 persistence가 없다.
- `Task 7`과 `Task 8`의 경계가 workflow 조립 후에도 유지된다.
- workflow entrypoint가 실제 실행 가능하다.
- Task 10 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```

---

## Task 11. 테스트/검증 코드 프롬프트

```md
당신은 이 저장소에서 SDD 방식으로 작업하는 coding agent다. 이번 작업은 Backoffice Copilot v1의 `Task 11`만 수행한다. 목적은 Task 1부터 Task 10까지 고정한 문서 계약을 회귀 가능한 테스트와 통합 검증 세트로 잠가서, 후속 리팩터링이나 다른 coding agent 작업이 경계를 깨면 바로 드러나게 만드는 것이다.

이 task는 shadow-parallel 레인과 최종 통합 마감의 두 겹 구조를 가진다. 하지만 이번 프롬프트에서는 Task 11 범위만 수행한다. 요구사항 추가, 문서 충돌 자체 해결, 제품 동작 재설계까지 확장하지 마라.

## 작업 시작 전 필수 확인
아래 순서대로 읽고, 어떤 계약을 어떤 테스트 레벨로 고정할지 정리한 뒤 구현하라.

1. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-prompt_guardrail_agents.md`
2. `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/02-implementation-task-breakdown-v2.md`
3. `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`의 Task 1 ~ Task 10 기록
4. `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/30-ops-and-checks.md`
5. `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/20-langgraph-node-spec.md`
6. `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/11-review-output-rules.md`
7. `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/21-data-contract.md`
8. `src/traffic_master_ai/defense/backoffice_copilot/specs/10-post-review-rules/10-post-review-rules.md`

그 다음 현재 구현물과 기존 테스트 패턴을 확인하라.

- `tests/defense/test_backoffice_copilot_ingest.py`
- `tests/defense/test_backoffice_copilot_candidates.py`
- `tests/defense/test_backoffice_copilot_session_analysis.py`
- `tests/defense/test_backoffice_copilot_review.py`
- `tests/defense/test_backoffice_copilot_summary.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/*`
- `src/traffic_master_ai/defense/backoffice_copilot/analysis/*`
- `src/traffic_master_ai/defense/backoffice_copilot/review/*`
- `src/traffic_master_ai/defense/backoffice_copilot/summary/*`
- `src/traffic_master_ai/defense/backoffice_copilot/output/*`
- `src/traffic_master_ai/defense/backoffice_copilot/validation/*`
- `src/traffic_master_ai/defense/backoffice_copilot/workflow/*`

문서와 기존 구현이 충돌하면 테스트로 감추지 말고 충돌 사실을 드러내라. 테스트를 구현 코드에 맞춰 억지로 휘게 만들지 마라.

## 목적
- 각 task 산출물별 최소 검증을 고정한다.
- 최종 workflow 기준 통합 테스트를 추가한다.
- fallback, suspicious-only 전달, DB 일관성, export 후속 검증을 회귀 가능하게 만든다.
- shadow test와 최종 통합 테스트를 정리된 구조로 남긴다.

## 구현 범위
- unit tests
- integration tests
- workflow tests
- fixture logs
- DB consistency tests
- fallback tests
- suspicious-only delivery tests

## 구현 제외
- 요구사항 추가
- 문서 충돌 자체 해결
- 제품 로직 수정이 주목적인 리팩터링
- 새 기능 설계

## 입력
- Task 1 ~ Task 10 구현물
- 문서 계약
- 기존 tests/defense 패턴

## 출력
- 회귀 테스트 스위트
- 통합 검증 세트
- 필요한 fixture logs

## 관련 문서
- `src/traffic_master_ai/defense/backoffice_copilot/specs/02-shared-terms-and-docs/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/20-langgraph-node-spec/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/11-review-output-rules/*`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/21-data-contract/*`

## 권장 구현 방향
기존 `tests/defense` 패턴을 재사용하는 선에서, task별 단위 테스트와 workflow 기준 통합 테스트를 분리하라. 아래 정도의 구조를 우선 검토하라.

- `tests/defense/test_backoffice_copilot_storage.py`
- `tests/defense/test_backoffice_copilot_validation.py`
- `tests/defense/test_backoffice_copilot_workflow.py`
- `tests/defense/fixtures/backoffice_copilot/*.jsonl` 또는 이에 준하는 fixture

정확한 파일명은 조금 달라도 되지만, 모든 검증을 하나의 거대 테스트 파일에 몰아넣지 마라. task별 회귀 포인트와 최종 통합 흐름이 구분돼야 한다.

## 작업 지침
1. Task 11은 두 겹 구조를 가져야 한다.
   - shadow-parallel: 각 task 완료 직후 붙는 단위/모듈 테스트
   - final integration: Task 10 이후 workflow 기준 통합 마감
   - 이번 작업에서는 이 둘을 문서 기준으로 정리해 실제 테스트 파일로 남겨라.
2. 테스트는 문서 계약을 잠그는 용도다.
   - 구현 세부를 과도하게 mock해서 문서 위반을 놓치지 마라.
   - 반대로 외부 의존성 때문에 flaky 해지지 않게 adapter/provider 경계는 적절히 stub 하라.
3. 최소한 아래 task별 회귀 포인트를 커버하라.
   - Task 1: 공통 DTO/state/import surface
   - Task 2: 2테이블/allowed value/JSON validator
   - Task 3: loader/semantic mapping 분리, `S3_CHALLENGE_HALTED` 비사용 처리
   - Task 4: candidate hard filter
   - Task 5: raw fallback 제한 조회, `SessionAnalysis` 최소 구조
   - Task 6: LLM output validation, fallback, 허용 레이블
   - Task 7: summary 길이 3, fallback
   - Task 8: DB-first, suspicious-only delivery, export는 DB 후속
   - Task 9a/9b: validator skeleton 확장, final status 분류
   - Task 10: 6-node workflow wiring
4. workflow 통합 테스트는 문서의 노드 연결 규칙을 반영해야 한다.
   - Node1 → Node2 → Node3 → Node4 → Node5 → Node6
   - Node4 + Node5 → Node6 결합
   - `match_id` 기반 graph input
   - 중간 persistence 없음
5. DB consistency 테스트는 최소한 아래를 검증하라.
   - `status/review_result/backend_delivery_status` 허용값
   - `summary_text_json` 길이 3
   - `session_analysis_json` 최소 구조
   - DB 저장 실패를 성공처럼 취급하지 않음
6. fallback 테스트는 최소한 아래를 검증하라.
   - raw fallback은 `needs_raw_fallback=true` 세션에만 제한 조회
   - LLM fallback 사용 이력 추적 가능
   - fallback이 있어도 silent fail이 아님
7. suspicious-only 전달 테스트는 최소한 아래를 검증하라.
   - `review_result='SUSPICIOUS'` row만 backend payload에 포함
   - 전달 시도 세션의 `backend_delivery_status`는 비어 있지 않음
   - NORMAL 세션이 payload/export suspicious 목록에 섞이지 않음
8. export 검증은 DB 이후 후속 단계로 테스트하라.
   - export 집계가 DB 집계와 일치
   - suspicious export는 `SUSPICIOUS` row만 포함
   - export 실패만으로 DB 저장 성공 run을 무조건 `FAILED`로 몰지 않음
9. fixture는 문서 계약을 드러내는 최소셋으로 유지하라.
   - 과도하게 큰 fixture로 테스트 의미를 흐리지 마라.
   - 한 fixture가 여러 경계를 동시에 애매하게 검증하지 않게 분리하라.
10. 외부 네트워크나 실제 backend/API 의존 테스트를 기본 경로에 넣지 마라.
   - adapter/provider stub 또는 in-memory 대체를 우선하라.
   - flaky integration test는 기본 회귀 스위트로 두지 마라.
11. Task 11에서는 아래를 하지 마라.
   - 문서 요구 변경
   - 구현 코드의 책임 경계 재설계
   - 테스트를 통과시키기 위한 스펙 완화
12. 테스트 명명과 배치는 후속 agent가 바로 찾을 수 있어야 한다.
   - `tests/defense/test_backoffice_copilot_*.py` 패턴을 우선 유지하라.
   - 어떤 task 계약을 잠그는 테스트인지 파일명/테스트명에서 드러내라.

## 최소 고정 대상
아래 항목은 이후 리팩터링에서도 테스트로 반드시 지켜져야 한다.

1. task별 핵심 계약 회귀 포인트
2. 6-node workflow 통합 검증
3. fallback 검증 경계
4. suspicious-only delivery 검증
5. DB-first/export 후속 검증
6. final status 분류 검증

## 검증
작업 후 최소 아래를 검증하라.

1. 각 task 산출물별 최소 검증이 존재한다.
2. 최종 workflow 기준 통합 테스트가 존재한다.
3. fallback 검증이 raw/LLM 모두에 대해 존재한다.
4. suspicious-only delivery와 `backend_delivery_status` 검증이 존재한다.
5. DB consistency와 export 후속 검증이 존재한다.
6. 테스트 모듈들이 import 가능하고 기본 실행이 가능하다.

가능하면 아래 수준의 검증을 수행하라.

- `python -m compileall src/traffic_master_ai/defense/backoffice_copilot tests/defense`
- `PYTHONPATH=src python3 -m unittest discover -s tests/defense -p 'test_backoffice_copilot*.py'`
- workflow 통합 테스트 단독 실행
- fallback 테스트 단독 실행
- suspicious-only delivery 테스트 단독 실행

단, 테스트 작성 중 발견한 문서/구현 충돌을 조용히 우회하지 마라. 충돌이 있으면 테스트 또는 로그에 분명히 드러내라.

## 작업 완료 후 기록
작업이 끝나면 아래 문서를 갱신해 Task 11 기록을 추가하라.

- `src/traffic_master_ai/defense/backoffice_copilot/specs/sdd_v1/task-execution-log.md`

주의:
- 기존 Task 0~10 기록을 지우지 마라.
- 어떤 계약을 어떤 테스트로 잠갔는지, shadow test와 최종 통합 테스트를 어떻게 나눴는지 로그에 남겨라.

반드시 아래 항목을 포함하라.

1. task 번호와 제목
2. 작업 일시
3. 실제로 수정한 파일 목록
4. 파일별 수정 요약
5. 검증에 사용한 명령과 결과 요약
6. 남은 리스크 또는 다음 task에 넘길 주의사항

## 완료 조건
- 각 task 산출물별 최소 검증이 존재한다.
- 최종 workflow 기준 통합 테스트가 존재한다.
- fallback, suspicious-only delivery, DB consistency, export 후속 검증이 테스트로 고정된다.
- shadow-parallel과 최종 통합 마감 구조가 테스트 배치에 드러난다.
- Task 11 변경 이력이 `specs/sdd_v1/task-execution-log.md`에 추가된다.
```
