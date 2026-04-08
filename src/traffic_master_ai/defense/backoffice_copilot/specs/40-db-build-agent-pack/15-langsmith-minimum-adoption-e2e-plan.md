# LangSmith 최소 도입 E2E 작업 문서

## 1. 문서 목적

이 문서는 TM AI 팀의 LangSmith 최소 도입 작업을
코드 수정 전에 E2E 기준으로 고정하기 위한 실행 문서다.

이 문서의 목적은 아래 5가지다.

- 이번 task의 목적을 한 문장으로 고정
- 참고 문서와 현재 코드의 차이를 먼저 드러냄
- 실제로 건드릴 파일 범위를 미리 잠금
- 구현 순서와 검증 순서를 E2E로 정리
- 다음 코드 task가 바로 시작할 수 있는 입력을 남김

이번 문서는 방향 설명 문서가 아니다.
실제 구현 직전 체크리스트와 작업 분해 문서다.

---

## 2. 이번 task의 한 줄 목적

OpenAI API가 호출되는 핵심 경로에 LangSmith tracing을 최소 범위로 붙여서
기능별, 세션별, 단계별 token과 cost를 확인 가능한 상태로 만든다.

---

## 3. 참고 문서 우선순위

이번 task는 아래 순서로 판단한다.

1. [32-storage-architecture.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md)
2. [33-docs-vs-current-code-gap-analysis.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/33-docs-vs-current-code-gap-analysis.md)
3. [agent.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/agent.md)
4. [38-langsmith-minimum-adoption-work-plan.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/38-langsmith-minimum-adoption-work-plan.md)
5. [defense_observability_ssot.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_observability_ssot.yaml)
6. [defense_admin_console_ssot.yaml](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_admin_console_ssot.yaml)
7. 직접 관련된 코드와 테스트 파일

---

## 4. 현재 코드와 목표 상태의 차이

## 4.1 현재 코드 상태

현재 저장소는 아래 상태다.

- `backoffice_copilot/adapters/openai.py`가 `urllib`로 OpenAI API를 직접 호출한다.
- `d0_mvp/optimizer/effect_evaluator.py`도 OpenAI-compatible REST 호출을 직접 처리한다.
- `offline/pipeline.py`는 `/v1/responses` 기반 batch 호출을 사용한다.
- `.env.ai.example`에는 LangSmith env가 이미 들어 있다.
- `d0_mvp/observability/schemas.py`에는 `langsmith` 필드가 이미 있다.
- `d0_mvp/observability/dashboard.py`는 `langsmith.traceUrl` 링크를 읽을 준비가 되어 있다.

즉 저장소에는 LangSmith를 받을 자리와 운영 방향은 일부 준비돼 있지만,
실제 OpenAI 호출 코드에 tracing은 아직 붙어 있지 않다.

## 4.2 목표 상태

이번 최소 도입 후에는 아래가 가능해야 한다.

- LangSmith 프로젝트에 trace가 남는다.
- trace에서 token, cost, latency를 볼 수 있다.
- 최소한 `session_id`, `feature_name`, `agent_step_name`, `environment` 기준으로 구분된다.
- 필요 시 기존 observability payload에 `langsmith.runId`, `langsmith.traceUrl`을 남길 수 있다.

## 4.3 핵심 gap

지금 가장 큰 gap은 아래 4개다.

1. OpenAI 호출 공통 tracing helper가 없다.
2. 주요 호출 경로에 통일된 metadata 규칙이 없다.
3. LangSmith trace와 기존 observability payload를 연결하는 기준이 아직 없다.
4. 테스트는 OpenAI request payload 검증까지만 있고 tracing 계약 검증은 없다.

---

## 5. 이번 task의 범위

## 5.1 구현 범위

- LangSmith 최소 도입의 E2E 작업 순서 문서화
- 실제 수정 대상 파일 목록 고정
- 공통 metadata 규칙 고정
- 문서 기준 검증 순서 고정
- 다음 코드 task의 시작 입력 정리

## 5.2 구현 제외

- 실제 LangSmith SDK 코드 추가
- 실제 OpenAI adapter 수정
- 실제 observability payload 저장 로직 추가
- Grafana 연동
- OTel, Prometheus 통합
- 알람 자동화
- infra provisioning
- secret 주입

---

## 6. 이번 task에서 건드릴 파일과 건드리지 않을 파일

## 6.1 이번 문서 task에서 수정 가능한 파일

- [15-langsmith-minimum-adoption-e2e-plan.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/15-langsmith-minimum-adoption-e2e-plan.md)
- [task-execution-log.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md)

## 6.2 다음 코드 task에서 우선 검토할 파일

- [openai.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/adapters/openai.py)
- [__init__.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/__init__.py)
- [effect_evaluator.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/optimizer/effect_evaluator.py)
- [pipeline.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/offline/pipeline.py)
- [schemas.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/observability/schemas.py)
- [dashboard.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/observability/dashboard.py)
- [test_backoffice_copilot_openai.py](/Users/shadowmoon/201-goormgb-ai-1/tests/defense/test_backoffice_copilot_openai.py)
- [.env.ai.example](/Users/shadowmoon/201-goormgb-ai-1/.env.ai.example)

## 6.3 지금 건드리면 안 되는 것

- storage architecture 문서의 책임 구분
- 관련 없는 runtime policy 로직
- Grafana / Discord 범위 문서
- secret 실제 값 주입
- unrelated refactor

---

## 7. 최소 metadata 계약

이번 최소 도입에서 필수 metadata는 아래 4개다.

- `session_id`
- `feature_name`
- `agent_step_name`
- `environment`

권장 metadata는 아래다.

- `thread_id`
- `match_id`
- `policy_version`
- `source_event_id`
- `owner_team`
- `model_name`
- `batch_size`
- `reasoning_effort`

명명 규칙은 아래처럼 고정한다.

- `feature_name`
  - `backoffice_copilot`
  - `policy_optimizer`
  - `challenge_analysis`
  - `experiment_runner`
- `agent_step_name`
  - `review_session`
  - `summarize_window`
  - `evaluate_policy_effect`
  - `offline_batch_judge`

---

## 8. E2E 작업 순서

## 8.1 Step 0. env 계약 확정

최소 env는 아래다.

- `LANGSMITH_API_KEY`
- `LANGSMITH_TRACING=true`
- `LANGSMITH_PROJECT=tm-ai`
- `LANGSMITH_WORKSPACE_ID=1`
- `TM_AI_ENV=dev|staging|prod`

체크 포인트:

- `.env.ai.example`과 실제 사용 env 이름이 충돌하지 않는지 확인
- LangSmith 관련 값이 OpenAI key와 섞이지 않는지 확인

## 8.2 Step 1. 공통 tracing helper 설계

원칙:

- OpenAI Python SDK 공통 의존을 전제로 하지 않는다.
- 현재 저장소의 `urllib` 직접 호출 패턴에 맞춘다.
- LangSmith 비활성 시 기존 동작을 바꾸지 않는다.

결과물:

- 공통 helper 또는 thin wrapper 1개
- 공통 metadata 주입 규칙
- 성공, 실패, latency 기록 방식

## 8.3 Step 2. Backoffice Copilot 1차 적용

대상:

- `build_openai_review_adapter`
- `build_openai_summary_adapter`

확인 포인트:

- `feature_name=backoffice_copilot`
- `agent_step_name=review_session|summarize_window`
- `session_id`, `match_id`, `environment` 기록
- 기존 테스트 계약을 깨지 않을 것

## 8.4 Step 3. LangSmith UI 기본 검증

최소 검증:

1. trace 생성
2. token 표시
3. cost 표시
4. metadata 표시
5. error run 표시

이 단계가 통과되기 전에는 다음 경로 확장으로 넘어가지 않는다.

## 8.5 Step 4. Effect Evaluator 확장

대상:

- `OpenAICompatibleLLMCaller.call`

확인 포인트:

- `feature_name=policy_optimizer` 또는 `experiment_runner`
- retry, timeout, http error를 trace에 반영
- `policy_version` 또는 evaluation run 식별자 연결

## 8.6 Step 5. Offline Batch Pipeline 확장

대상:

- `offline/pipeline.py`의 batch judge 호출

확인 포인트:

- batch root 기준 trace 생성
- `thread_id`, `batch_size`, `reasoning_effort` 기록
- 단건 `session_id`가 부정확하면 억지로 넣지 않음

## 8.7 Step 6. observability 연결 여부 판단

최소안에서는 필수는 아니다.
다만 아래가 맞으면 후속 task로 넘긴다.

- `langsmith.runId`
- `langsmith.traceUrl`

원칙:

- 운영 콘솔의 1차 SSOT는 기존 observability 구조다.
- LangSmith는 drill-down 링크 역할만 한다.
- trace 본문은 LangSmith UI에서 본다.

---

## 9. 검증 계획

## 9.1 문서 검증

- `agent.md` 체크리스트와 충돌이 없는지 확인
- `38-langsmith-minimum-adoption-work-plan.md`와 역할이 겹치지 않는지 확인

## 9.2 코드 적용 후 검증 예정 명령

- `PYTHONPATH=src python3 -m unittest discover -s tests/defense -p 'test_backoffice_copilot_openai.py'`
- 필요 시 관련 smoke 실행

## 9.3 UI 검증

- LangSmith project에서 trace 확인
- feature 검색 확인
- metadata 검색 확인
- token/cost 확인

---

## 10. 완료 조건

이번 문서 task의 완료 조건은 아래다.

1. LangSmith 최소 도입의 E2E 작업 순서가 문서로 고정된다.
2. 현재 코드와 목표 상태의 차이가 문서에 명시된다.
3. 다음 코드 task에서 건드릴 파일과 건드리면 안 되는 범위가 분리된다.
4. 검증 계획이 문서에 포함된다.
5. 작업 로그에 이번 문서 task가 append된다.

---

## 11. 다음 코드 task에 넘길 입력

다음 task는 아래 한 문장으로 시작하면 된다.

`Backoffice Copilot OpenAI adapter에 LangSmith 최소 tracing helper를 붙이고, 기존 request/response 계약과 테스트를 유지하라.`

다음 task의 시작 입력은 아래다.

- 첫 구현 대상은 `backoffice_copilot/adapters/openai.py`
- tracing 방식은 `urllib` 직접 호출에 맞는 수동 helper 기준
- 최소 metadata는 `session_id`, `feature_name`, `agent_step_name`, `environment`
- env는 `.env.ai.example`의 LangSmith 항목을 기준으로 사용
- 기존 테스트 파일은 `tests/defense/test_backoffice_copilot_openai.py`

---

## 12. 한 줄 결론

이번 문서는 LangSmith 도입 방향을 다시 설명하는 문서가 아니라,
코드 작업에 들어가기 전 E2E 작업 순서와 범위를 잠그는 실행 문서다.
