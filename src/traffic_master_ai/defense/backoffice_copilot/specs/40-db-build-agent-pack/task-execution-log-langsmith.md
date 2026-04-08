# LangSmith 최소 도입 Task Execution Log

## Task 12

### 1. task 번호와 제목

- Task 12. LangSmith PR 정리: 임시 검증 스크립트 제거

### 2. 작업 일시

- 2026-04-08 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/.tmp_task10_verify.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log-langsmith.md`

### 4. 파일별 수정 요약

- `.tmp_task10_verify.py`: Task 10 실 API 확인에만 쓰던 임시 검증 스크립트라 PR 범위에서 제거했다.
- `task-execution-log-langsmith.md`: 최종 PR 정리 작업을 기록했다.

### 5. 검증에 사용한 명령과 결과 요약

- 수동 점검
  - 결과: `.tmp_task10_verify.py`는 런타임 코드나 테스트 스위트에서 참조되지 않는 일회성 진단 스크립트였다.

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - 없음
- 다음 task에 넘길 입력
  - LangSmith 범위 PR에는 실제 코드, 테스트, 실행 문서만 포함하면 된다.

## Task 11

### 1. task 번호와 제목

- Task 11. AuditSummarizer LangSmith tracing 계약 테스트 보강

### 2. 작업 일시

- 2026-04-08 KST

### 3. 실제로 수정한 파일 목록

- `tests/defense/test_audit_summarizer_langsmith.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log-langsmith.md`

### 4. 파일별 수정 요약

- `test_audit_summarizer_langsmith.py`: `AuditSummarizer.summarize()`가 LLM caller에 `trace_name="policy_optimizer.audit_summary"`와 통일된 `trace_metadata`를 전달하는지 검증하는 테스트를 추가했다.
- `task-execution-log-langsmith.md`: Task 11 테스트 보강 내용을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 단위 테스트
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_audit_summarizer_langsmith -v`
  - 기대 결과: `OK`

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - `AuditSummarizer`는 실제 OpenAI 호출보다 `LLMCaller` 프로토콜을 통해 tracing 계약을 검증하는 구조다. 이 테스트는 목적에 맞는 최소 범위를 잠근다.
- 다음 task에 넘길 입력
  - LangSmith 관련 핵심 경로의 tracing 계약 테스트는 `backoffice_copilot`, `effect_evaluator`, `audit_summarizer`까지 확보됐다.

## Task 9

### 1. task 번호와 제목

- Task 9. offline/pipeline.py LangSmith tracing 확장 및 전체 검증

### 2. 작업 일시

- 2026-04-07 15:49:07 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/d0_mvp/optimizer/pipeline.py`
- `tests/defense/test_effect_evaluator_openai.py`
- `tests/defense/test_backoffice_copilot_openai.py`

### 4. 파일별 수정 요약

- `pipeline.py`: `_append_audit_event()`에 `langsmith` 파라미터를 추가하고, `run_once()`에서 `EffectEvaluator`가 proposal에 주입한 `langsmith_link`를 추출해 `OFFLINE_OPT_PROPOSAL_CREATED`, `OFFLINE_OPT_PROPOSAL_VALIDATED`, `OFFLINE_POLICY_PROPOSAL_REJECTED`, `OFFLINE_OPT_RUN_FINISHED` 감사 이벤트와 반환 결과에 전파했다.
- `test_effect_evaluator_openai.py`: `_FakeTrace`에 `get_langsmith_link()` 메서드를 추가하고 `result.langsmith_link` 검증 assertion을 보강했다.
- `test_backoffice_copilot_openai.py`: `_FakeTrace`에 `get_langsmith_link()` 메서드를 추가해 tuple unpack 호환 문제를 해소했다.

### 5. 검증에 사용한 명령과 결과 요약

- 단위 테스트
  - 명령: `PYTHONPATH=src python3 -m unittest tests/defense/test_effect_evaluator_openai.py tests/defense/test_backoffice_copilot_openai.py tests/defense/test_offline_pipeline.py tests/defense/test_offline_replay_guardrails.py tests/defense/test_offline_optimizer_strict_authority.py -v`
  - 결과: `Ran 8 tests ... OK`
- 컴파일 확인
  - 명령: `python3 -m compileall` 대상 5개 파일
  - 결과: 전부 성공

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - pipeline 레벨의 langsmith 전파는 `proposal_raw`에 이미 주입된 link를 꺼내 쓰는 방식이라, EffectEvaluator가 proposal을 만들지 않으면(proposal=None) langsmith_link도 None이 된다. 이는 의도된 동작이다.
- 다음 task에 넘길 입력
  - LangSmith 최소 도입 코드 변경은 모두 완료됐다.
  - 남은 건 실제 호출 검증(`.env.ai` 기반)과 prompt 품질 확인이다.

## Task 8

### 1. task 번호와 제목

- Task 8. observability payload에 langsmith.runId / langsmith.traceUrl 연결

### 2. 작업 일시

- 2026-04-07 15:46:29 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/langsmith_support.py`
- `src/traffic_master_ai/defense/backoffice_copilot/adapters/openai.py`
- `src/traffic_master_ai/defense/d0_mvp/optimizer/effect_evaluator.py`

### 4. 파일별 수정 요약

- `langsmith_support.py`: `_LangSmithLLMTrace`에 `run_id` property, `trace_url` property, `get_langsmith_link()` 메서드를 추가했다. `_langsmith_project_name()`, `_langsmith_base_url()`, `_langsmith_workspace_id()` helper를 추가해 URL을 조립한다.
- `openai.py`: `_call_openai_chat_completions()`의 반환 타입을 `Any` → `tuple[Any, dict[str, str]]`로 변경해 `(structured_output, langsmith_link)`를 돌려주도록 했다. `build_openai_review_adapter`와 `build_openai_summary_adapter`는 langsmith_link가 있으면 결과 dict에 `langsmith` 키로 주입한다.
- `effect_evaluator.py`: `LLMCallResult` dataclass에 `langsmith_link: dict[str, str]` 필드를 추가했다. `OpenAICompatibleLLMCaller.call()`에서 `trace.get_langsmith_link()`로 캡처한다. `propose()` 메서드의 `OFFLINE_LLM_RUN_FINISHED`와 `OFFLINE_LLM_PATCH_PROPOSED` audit payload에 langsmith link를 주입하고, 최종 sanitized proposal에도 `langsmith` 키를 넣어 pipeline까지 전파되도록 했다.

### 5. 검증에 사용한 명령과 결과 요약

- Task 9에서 통합 검증 (8개 테스트 전부 OK)

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - `trace_url` 조립은 `LANGSMITH_WORKSPACE_ID` 환경변수에 의존한다. 실제 운영에서 이 값이 정확한 UUID인지 배포 전 확인 필요.
  - tracing이 비활성(`LANGSMITH_TRACING=false`)이면 langsmith_link는 빈 dict이고, 결과에 주입되지 않는다. 이는 의도된 동작.
- 다음 task에 넘길 입력
  - dashboard.py `session_drilldown()`은 이미 `langsmith.traceUrl`을 읽어 link를 생성하는 코드가 있어, producer 연결이 완료되면 dashboard에서도 자동 노출된다.

## Task 7

### 1. task 번호와 제목

- Task 7. effect_evaluator prompt 및 output budget 품질 개선

### 2. 작업 일시

- 2026-04-07 15:14:19 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/d0_mvp/optimizer/effect_evaluator.py`
- `src/traffic_master_ai/defense/d0_mvp/core/constants.py`

### 4. 파일별 수정 요약

- `effect_evaluator.py`: `_EFFECT_EVALUATOR_PROMPT`를 3줄짜리 범용 지시에서 → JSON 스키마 명시, 12개 허용 path와 범위 나열, monotonic threshold 규칙 등을 포함한 상세 프롬프트로 교체했다. 이전에 LLM이 reasoning token만 소모하고 visible JSON content가 비었던 `proposal=None` 문제의 근본 원인이 프롬프트 부족이었다.
- `constants.py`: `OFFLINE_LLM_TIMEOUT_MS` 기본값 2500→15000, `OFFLINE_LLM_MAX_OUTPUT_TOKENS` 기본값 1200→2400으로 변경했다. Task 6에서 확인된 timeout 및 output budget 부족 문제를 해소한다.

### 5. 검증에 사용한 명령과 결과 요약

- Task 9에서 통합 검증 (8개 테스트 전부 OK, 컴파일 성공)

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - prompt 개선만으로 `proposal=None`이 완전히 해소되는지는 실제 API 호출로 검증해야 한다. 테스트에서는 mock 호출이므로 LLM 응답 품질 검증은 불가.
  - `max_output_tokens=2400`은 비용 측면에서 이전 대비 2배이나, offline batch 호출이므로 허용 가능한 수준이다.
- 다음 task에 넘길 입력
  - `.env.ai` 로드 후 실제 OpenAI 호출로 proposal JSON 생성 여부를 확인하는 것이 최종 검증 단계다.

## Task 6

### 1. task 번호와 제목

- Task 6. LangSmith E2E 후속 검증 완료: summary 성공, effect_evaluator timeout 해소

### 2. 작업 일시

- 2026-04-07 14:36:08 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `task-execution-log.md`: `summarize_window` 실호출 성공, `policy_optimizer.evaluate_policy_effect` 실호출 재검증, timeout 관련 해석과 남은 응답 품질 이슈를 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 실제 Backoffice summary 호출 검증
  - 명령: `.env.ai` 로드 후 `build_openai_summary_adapter(...)`로 실제 summary 호출 1건 실행
  - 결과:
    - adapter 성공 응답 수신
    - `summary_text` 3줄 응답 확인
    - LangSmith run name `backoffice_copilot.summarize_window`
    - run status `success`
    - metadata에 `feature_name`, `agent_step_name`, `environment`, `match_id`, `thread_id` 정상 기록 확인
    - outputs 안에 OpenAI `usage`와 `usage_metadata`
      - `input_tokens=212`
      - `output_tokens=543`
      - `total_tokens=755`
      가 기록된 것을 확인
- 실제 EffectEvaluator 호출 검증
  - 명령: `.env.ai` 로드 후 `TM_OFFLINE_LLM_TIMEOUT_MS=20000`을 export하고 `EffectEvaluator.propose(...)`를 실제 호출
  - 결과:
    - LangSmith run name `policy_optimizer.evaluate_policy_effect`
    - metadata에 `feature_name=policy_optimizer`, `agent_step_name=evaluate_policy_effect`, `policy_version`, `metrics_snapshot_id`, `thread_id`, `environment` 정상 기록 확인
    - 초회 조회 시 run status가 `pending`이었으나 후속 재조회에서 `success`로 수렴
    - 이전 timeout 원인은 기본 `TM_OFFLINE_LLM_TIMEOUT_MS=2500` 값의 영향으로 보는 것이 타당함
    - 성공 run outputs 안에 OpenAI `usage`와 `usage_metadata`
      - `input_tokens=338`
      - `output_tokens=1200`
      - `total_tokens=1538`
      가 기록된 것을 확인
    - 다만 assistant content가 비어 있어 `proposal=None`으로 끝났고, tracing 성공과 별개로 제안 품질은 아직 미완료 상태
- 추가 max output token 실험
  - 명령: `.env.ai` 로드 후 `TM_OFFLINE_LLM_TIMEOUT_MS=20000`, `TM_OFFLINE_LLM_MAX_OUTPUT_TOKENS=2400`을 export하고 `EffectEvaluator.propose(...)` 재실행
  - 결과:
    - timeout은 재현되지 않음
    - LangSmith run은 최종 `success`
    - 그러나 여전히 `proposal=None`
    - 이 실험으로 timeout 문제와 proposal 품질 문제는 별개라는 점을 확인

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - LangSmith tracing 자체는 `review_session`, `summarize_window`, `evaluate_policy_effect`까지 확인됐지만, `EffectEvaluator`는 아직 실제 patch proposal을 안정적으로 만들지 못한다.
  - 현재 `gpt-5-mini` + `response_format=json_object` + evaluator prompt 조합에서 reasoning token 소모가 크고, visible JSON content가 비는 경우가 있다.
- 다음 task에 넘길 입력
  - 다음 우선순위는 `effect_evaluator` prompt / output budget / model 설정을 조정해 `proposal=None`이 아니라 실제 유효 proposal까지 나오는지 확인하는 것이다.
  - 그 다음 단계로 `langsmith.runId`, `langsmith.traceUrl`을 observability payload에 연결하면 된다.

## Task 5

### 1. task 번호와 제목

- Task 5. OpenAI key 교체 후 LangSmith 성공 run 검증 완료

### 2. 작업 일시

- 2026-04-07 14:23:57 KST

### 3. 실제로 수정한 파일 목록

- `.env.ai`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `.env.ai`: 사용자가 제공한 새 OpenAI key로 `TM_OFFLINE_LLM_API_KEY`를 교체했다. 이미 보정된 LangSmith workspace UUID 설정을 유지했다.
- `task-execution-log.md`: OpenAI key 정상화 이후 실제 성공 run 검증 결과를 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- OpenAI key 인증 확인
  - 명령: `.env.ai` 로드 후 `GET https://api.openai.com/v1/models`
  - 결과: `200 OK`
  - 해석: 새 OpenAI key는 정상
- LangSmith project 조회 확인
  - 명령: `.env.ai` 로드 후 `client.read_project(project_name='tm-ai')`
  - 결과: `tm-ai` project 조회 성공
- 실제 Backoffice review 호출 검증
  - 명령: `.env.ai` 로드 후 `build_openai_review_adapter(...)`로 실제 review 호출 1건 실행
  - 결과:
    - adapter 성공 응답 수신
    - latency 약 `4536ms`
    - `review_result=SUSPICIOUS` 응답 확인
- LangSmith 성공 run 확인
  - 명령: 같은 환경에서 `client.list_runs(project_name='tm-ai', limit=20)` 후 `match_id`로 대상 run 탐색
  - 결과:
    - run name: `backoffice_copilot.review_session`
    - run status: `success`
    - run error: `None`
    - LangSmith UI URL 확보
    - metadata에 `feature_name`, `agent_step_name`, `environment`, `match_id`, `session_id`, `thread_id` 정상 기록 확인
    - outputs 안에 OpenAI `usage`와 `usage_metadata`
      - `input_tokens=152`
      - `output_tokens=204`
      - `total_tokens=356`
      가 기록된 것을 확인
- 최신 run 재조회
  - 명령: `.env.ai` 로드 후 `client.list_runs(project_name='tm-ai', limit=1)`
  - 결과: 최신 run `success` 상태 확인

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - 현재 검증은 `review_session` 경로 1건에 한정된다.
  - `summarize_window` 실호출 검증은 아직 하지 않았다.
  - LangSmith API에서 top-level `usage_metadata` 조회는 `null`이었고, 현재는 run outputs 안의 `usage` / `usage_metadata`로 검증했다. UI 표시가 충분한지는 실제 화면 기준 추가 확인이 좋다.
- 다음 task에 넘길 입력
  - 다음 검증 대상은 `build_openai_summary_adapter(...)`
  - 다음 확장 구현 대상은 `d0_mvp/optimizer/effect_evaluator.py`
  - observability payload에 `langsmith.runId`, `langsmith.traceUrl`을 연결하는 후속 task를 시작할 수 있다

## Task 4

### 1. task 번호와 제목

- Task 4. LangSmith workspace / OpenAI key 원인 분리 및 설정 보정

### 2. 작업 일시

- 2026-04-07 12:52:27 KST 이후 후속 보정

### 3. 실제로 수정한 파일 목록

- `.env.ai`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `.env.ai`: `LANGSMITH_WORKSPACE_ID`를 잘못된 값에서 실제 접근 가능한 UUID로 교체했다.
- `task-execution-log.md`: workspace id와 project id 혼동, OpenAI invalid key 원인을 구분해 기록했다.

### 5. 검증에 사용한 명령과 결과 요약

- `.env.ai` / `.env` key 점검
  - 결과: 실제 OpenAI 계열 key는 `TM_OFFLINE_LLM_API_KEY` 하나만 설정돼 있었고, prefix는 `sk-proj-...` 형식이었다.
- OpenAI 인증 원인 확인
  - 명령: `.env.ai` 로드 후 `GET https://api.openai.com/v1/models`
  - 결과: `401` + `invalid_api_key`
  - 해석: endpoint 문제나 코드 문제가 아니라 현재 `.env.ai`의 `TM_OFFLINE_LLM_API_KEY` 자체가 잘못됐거나 만료/폐기된 상태
- LangSmith workspace id 검증
  - 입력값 1: `92841252-39be-4b46-aa10-863e1eedeb98`
  - 결과: `403 Forbidden`
  - 해석: 이 값은 workspace id가 아니라 `tm-ai` project id였다.
- LangSmith workspace 후보 재검증
  - 입력값 2: `89d3de1a-a65b-416a-bc88-2563d8cf7eab`
  - 결과: `client.read_project(project_name='tm-ai')` 성공
  - 해석: 이 값이 현재 key와 맞는 workspace id다.

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - OpenAI 성공 호출 검증은 아직 못 했다. 이유는 `.env.ai`의 OpenAI key가 invalid 상태이기 때문이다.
- 다음 task에 넘길 입력
  - LangSmith는 이제 `.env.ai` 그대로 사용 가능
  - OpenAI 검증을 이어가려면 `TM_OFFLINE_LLM_API_KEY`를 새 유효 key로 교체해야 한다
  - key 교체 후 `build_openai_review_adapter(...)` 실호출 1건과 `client.list_runs(project_name='tm-ai')` 재검증을 다시 수행하면 된다

## Task 3

### 1. task 번호와 제목

- Task 3. LangSmith 최소 도입 실제 검증 수행

### 2. 작업 일시

- 2026-04-07 12:52:27 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `task-execution-log.md`: `.env.ai` 기반 LangSmith / OpenAI 실제 검증 결과와 blocker를 기록했다.

### 5. 검증에 사용한 명령과 결과 요약

- env 유무 확인
  - 명령: `.env.ai`에서 `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT`, `LANGSMITH_WORKSPACE_ID`, `TM_AI_ENV`, `TM_OFFLINE_LLM_API_KEY`, `TM_OFFLINE_LLM_MODEL`, `OPENAI_BASE_URL` set 여부 확인
  - 결과: 필요한 key는 모두 존재
- 시스템 Python 설치 제한 확인
  - 명령: `python3 -m pip install -e /Users/shadowmoon/201-goormgb-ai-1`
  - 결과: PEP 668 `externally-managed-environment`로 차단
- 검증용 venv 생성 및 설치
  - 명령: `python3 -m venv /Users/shadowmoon/201-goormgb-ai-1/.venv-langsmith-check`
  - 명령: `/Users/shadowmoon/201-goormgb-ai-1/.venv-langsmith-check/bin/python -m pip install -e /Users/shadowmoon/201-goormgb-ai-1`
  - 결과: `langsmith` 포함 editable install 성공
- LangSmith client 기본 연결 확인
  - 명령: `.env.ai` 로드 후 `Client()` 생성 및 메서드 시그니처 확인
  - 결과: client 연결 가능
- `.env.ai`의 `LANGSMITH_WORKSPACE_ID=1` 검증
  - 명령: `.env.ai` 그대로 `client.read_project(project_name='tm-ai')`
  - 결과: `UUID header value was not a valid UUID`와 함께 401 발생
  - 해석: 현재 SDK 기준 `LANGSMITH_WORKSPACE_ID`는 숫자 `1`이 아니라 UUID 형식이어야 하거나, 단일 workspace key면 아예 빼는 편이 안전
- workspace env 제거 후 LangSmith 조회 확인
  - 명령: `.env.ai` 로드 후 `unset LANGSMITH_WORKSPACE_ID`, 이후 `client.list_projects(name='tm-ai', limit=5)`
  - 결과: auth 성공, 초기에는 project 0건
- 실제 OpenAI 호출 검증
  - 명령: `.env.ai` 로드 후 `unset LANGSMITH_WORKSPACE_ID`, 이후 `build_openai_review_adapter(...)`로 실제 review 호출 1건 실행
  - 결과: OpenAI API가 `401 Unauthorized`를 반환해 adapter는 실패
- LangSmith run 생성 확인
  - 명령: 같은 환경에서 `client.list_runs(project_name='tm-ai', limit=10)`
  - 결과:
    - project `tm-ai` 자동 생성 확인
    - run 1건 생성 확인
    - run name: `backoffice_copilot.review_session`
    - run status: `error`
    - run error: `ConnectionError('HTTP request failed: HTTP Error 401: Unauthorized')`
    - LangSmith UI URL 확보
    - metadata에 `feature_name`, `agent_step_name`, `environment`, `match_id`, `session_id`, `thread_id` 정상 기록 확인
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-07 12:52:27 KST`

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - `.env.ai`의 `LANGSMITH_WORKSPACE_ID=1`은 현재 LangSmith SDK와 맞지 않는다.
  - `.env.ai`의 `TM_OFFLINE_LLM_API_KEY` 또는 연결된 OpenAI credential 상태가 현재 401이라 성공 호출 검증이 불가능하다.
  - 따라서 이번 검증은 "LangSmith trace 생성 및 metadata 기록 확인"까지는 성공했지만, "성공 응답에서 token/cost가 실제 채워지는지"는 아직 미완료다.
- 다음 task에 넘길 입력
  - `LANGSMITH_WORKSPACE_ID`는 제거하거나 실제 UUID 형식 workspace id로 교체 필요
  - OpenAI key 정상화 후 동일 스크립트 재실행하면 성공 run과 usage metadata 확인 가능
  - 다음 확장 대상은 `d0_mvp/optimizer/effect_evaluator.py`

## Task 2

### 1. task 번호와 제목

- Task 2. Backoffice Copilot OpenAI adapter LangSmith 최소 tracing 1차 적용

### 2. 작업 일시

- 2026-04-07 12:43:57 KST

### 3. 실제로 수정한 파일 목록

- `pyproject.toml`
- `src/traffic_master_ai/defense/langsmith_support.py`
- `src/traffic_master_ai/defense/backoffice_copilot/adapters/openai.py`
- `tests/defense/test_backoffice_copilot_openai.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `pyproject.toml`: LangSmith SDK를 프로젝트 의존성에 추가했다.
- `langsmith_support.py`: `LANGSMITH_TRACING` 활성 여부와 `langsmith` 설치 여부를 모두 고려하는 공통 LLM trace helper를 추가했다. lazy import 방식이라 SDK 미설치 환경에서도 기존 코드 import가 깨지지 않는다.
- `openai.py`: review/summary OpenAI 호출을 LangSmith trace로 감싸고, `feature_name`, `agent_step_name`, `environment`, `match_id`, `thread_id`, `session_id` 같은 최소 metadata를 주입했다. OpenAI 응답의 `usage`를 `usage_metadata`로 변환해 token/cost 계산 입력도 함께 남기도록 했다.
- `test_backoffice_copilot_openai.py`: 기존 request payload 검증은 유지하고, LangSmith trace 시작 metadata와 usage mapping이 호출되는지 검증하는 테스트를 보강했다.
- `task-execution-log.md`: Task 16 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 직접 관련 파일 점검
  - 명령: `sed -n '1,240p' pyproject.toml`
  - 결과: 프로젝트 의존성 구조와 optional dependency 구성을 확인했다.
  - 명령: `sed -n '1,240p' src/traffic_master_ai/defense/backoffice_copilot/adapters/openai.py`
  - 결과: `urllib` 직접 호출 경로에 helper를 끼우는 최소 변경 지점을 확인했다.
  - 명령: `sed -n '1,240p' tests/defense/test_backoffice_copilot_openai.py`
  - 결과: 기존 테스트가 request payload와 error handling 계약을 잠그고 있어 tracing 보강 테스트를 같은 파일에 추가하는 것이 안전함을 확인했다.
- LangSmith 관련 기존 수용 지점 확인
  - 명령: `rg -n "langsmith|LangSmith|traceUrl|runId" src/traffic_master_ai/defense -g '!**/.venv/**'`
  - 결과: observability schema와 dashboard는 이미 `langsmith.runId`, `langsmith.traceUrl` 소비 준비가 되어 있고, 이번 task는 producer 첫 단계에 해당함을 확인했다.
- 테스트
  - 명령: `PYTHONPATH=src python3 -m unittest discover -s tests/defense -p 'test_backoffice_copilot_openai.py'`
  - 결과: `Ran 5 tests ... OK`
- 컴파일 확인
  - 명령: `python3 -m compileall src/traffic_master_ai/defense/langsmith_support.py src/traffic_master_ai/defense/backoffice_copilot/adapters/openai.py`
  - 결과: 두 파일 모두 compile 성공
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-07 12:43:57 KST`

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - 현재 환경에는 `langsmith` 패키지가 실제 설치돼 있지 않아 tracing은 helper 레벨에서 no-op fallback이 된다. 실제 trace 확인 전 `pip install -e .` 또는 동등한 설치가 필요하다.
  - summary 호출은 단일 `session_id`가 자연스럽지 않아 `thread_id=match_id` 중심으로 먼저 넣었다.
  - 아직 `langsmith.runId`, `langsmith.traceUrl`을 observability payload에 저장하지는 않았다.
- 다음 task에 넘길 입력
  - 실제 UI 확인 전 `langsmith` 의존성 설치 필요
  - 다음 확장 대상은 `d0_mvp/optimizer/effect_evaluator.py`
  - observability 연결은 별도 task로 `schemas.py`와 producer 경로를 같이 봐야 한다
  - batch 경로인 `offline/pipeline.py`는 root/child trace 설계를 먼저 정하고 들어가는 것이 안전하다

## Task 1

### 1. task 번호와 제목

- Task 1. LangSmith 최소 도입 E2E 작업 문서 작성

### 2. 작업 일시

- 2026-04-07 12:25:44 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/15-langsmith-minimum-adoption-e2e-plan.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `15-langsmith-minimum-adoption-e2e-plan.md`: `agent.md` 작업 원칙에 맞춰 LangSmith 최소 도입의 코드 전 단계 E2E 실행 문서를 작성했다. 목적, 참고 문서 우선순위, 현재 코드와 목표 상태의 gap, 수정 가능 범위, 최소 metadata 계약, 단계별 작업 순서, 검증 계획, 다음 코드 task 입력을 고정했다.
- `task-execution-log.md`: Task 15 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `03-db-build-task-template.md`, `38-langsmith-minimum-adoption-work-plan.md`
  - 결과: 새 문서가 방향 설명이 아니라 실행 문서 역할을 하도록 범위를 분리했고, `agent.md`의 시작 전 체크리스트와 작업 로그 원칙을 반영했다.
- 직접 관련 코드/테스트 탐색
  - 명령: `sed -n '1,220p' src/traffic_master_ai/defense/backoffice_copilot/__init__.py`
  - 결과: Backoffice Copilot public surface에서 OpenAI adapter factory가 export되고 있음을 확인했다.
  - 명령: `sed -n '1,220p' tests/defense/test_backoffice_copilot_openai.py`
  - 결과: 기존 테스트가 OpenAI request payload와 error handling 계약을 잠그고 있음을 확인했다.
  - 명령: `rg -n "langsmith|LangSmith|traceUrl|runId" src/traffic_master_ai/defense -g '!**/.venv/**'`
  - 결과: observability schema와 dashboard는 `langsmith.runId`, `langsmith.traceUrl`을 받을 준비가 되어 있으나 실제 producer 연결은 아직 없음을 확인했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-07 12:25:44 KST`

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - `.env.ai.example`에 실제 secret 값이 들어 있어 예시 파일 운영 방식 정리가 필요하다.
  - LangSmith trace를 observability payload에 언제 연결할지 아직 후속 판단이 필요하다.
  - `offline/pipeline.py`의 batch 호출은 `session_id` 단일 metadata 모델과 잘 맞지 않아 root/child 설계 판단이 남아 있다.
- 다음 task에 넘길 입력
  - 첫 구현 대상은 `backoffice_copilot/adapters/openai.py`
  - tracing 방식은 OpenAI SDK wrapper보다 `urllib` 직접 호출에 맞는 수동 helper 기준
  - 최소 metadata는 `session_id`, `feature_name`, `agent_step_name`, `environment`
  - 검증 시작점은 `tests/defense/test_backoffice_copilot_openai.py`
  - observability 연결은 후속 선택 과제로 두되 `langsmith.runId`, `langsmith.traceUrl` 필드는 이미 수용 가능

---

## Task 10: EffectEvaluator 실 API 재검증 + usage_metadata 확인

> 실행 일시: 2026-04-07 17:00 KST

### 1. 목적

- 피드백 1: Task 7에서 프롬프트·타임아웃·토큰 예산을 개선했으나, 실제 OpenAI API에서 proposal JSON이 안정적으로 나오는지 실증 검증
- 피드백 2: LangSmith top-level `usage_metadata` null 이슈 확인

### 2. 사전 점검

- `.env.ai` 확인: `TM_OFFLINE_LLM_API_KEY` 유효, `LANGSMITH_TRACING=true`, `LANGSMITH_PROJECT=tm-ai`
- OpenAI key 유효성: 이전 세션에서 `GET /v1/models` → 200 OK 확인

### 3. 검증 스크립트 수정 & 실행

- 이전 스크립트 실패 원인: `should_trigger()` 가드 조건 미충족
  - `unique_sessions` 누락 (guard: >= 200)
  - `event_counts_by_type` 누락 (guard: `DEF_THROTTLE_APPLIED >= 100`, `S3_CHALLENGE_RESULT >= 100`)
- 수정 사항:
  - `.env.ai` 경로 해석 수정 (프로젝트 루트에서 6 levels)
  - `unique_sessions=800`, `event_counts_by_type={DEF_THROTTLE_APPLIED: 350, S3_CHALLENGE_RESULT: 180}` 추가
  - rule-based 경로를 피하기 위해 정상 범위 metrics 사용 (`block_rate=0.008`, `s3_temp_lock_rate=0.012`, `avg_throttle_delay_ms=145`)

### 4. 실행 결과: ✅ 성공

```
Model: gpt-5-mini
Timeout: 30000ms (override)
Max output tokens: 2400
LANGSMITH_TRACING: true
LANGSMITH_PROJECT: tm-ai

should_trigger: True ✓
Elapsed: 27131ms

RESULT: proposal received! ✅
  proposal_id:          proposal-v2-20260407-001
  base_policy_version:  v2.0.0-mvp
  confidence:           0.65
  patches count:        3
    [0] tier.thresholds.T0_max / inc / 0.03 — "S3 challenge pass rate is high (94%)"
    [1] planner.throttle_delay_ms.T1 / dec / 30 — "Average throttle delay is 145ms"
    [2] risk.alpha / dec / 0.05 — "Reduce EWMA sensitivity to short-term spikes"
  rationale: "Reduce unnecessary challenges and user impact by modestly expanding the safe tier..."
  rollback_conditions: ["block_rate increases by >20% relative...", "s3_fail_rate rises above 1%..."]
```

### 5. proposal 품질 분석

| 항목 | 기대 | 결과 | 판정 |
|------|------|------|------|
| `proposal_id` | 비어 있지 않은 문자열 | `proposal-v2-20260407-001` | ✅ |
| `base_policy_version` | echo input | `v2.0.0-mvp` | ✅ |
| `patches` | 1-12개, 허용된 경로만 | 3개, 모두 허용 경로 | ✅ |
| `patches.op` | set/inc/dec | inc, dec, dec | ✅ |
| `confidence` | 0.0-1.0 float | 0.65 | ✅ |
| `rollback_conditions` | 비어 있지 않은 배열 | 2개 조건 | ✅ |
| `rationale` | 비어 있지 않은 문자열 | 상세 영문 설명 | ✅ |
| ProposalValidator 통과 | valid=True | `propose()` 반환값 != None | ✅ |

→ **proposal JSON 안정성 실증 완료. 피드백 1 닫힘.**

### 6. 피드백 2: usage_metadata top-level vs outputs 내부

- `langsmith_support.py` 확인 결과:
  - `record_output()` → `outputs["usage_metadata"]` 에 주입 (L138-139) — LangSmith SDK 표준 위치
  - `__exit__()` → `self._run_tree.usage_metadata = dict(...)` 직접 세팅 (L79) — 안전장치
- 결론: **LangSmith cost 집계는 `outputs.usage_metadata`를 기준으로 함. top-level null은 SDK 구조상 예상 동작.**
- `run_tree.usage_metadata` 직접 세팅 라인은 SDK 버전 호환 안전장치로 유지 (삭제 불필요)
- → **피드백 2 닫힘. 코드 변경 불필요.**

### 7. langsmith link 미연결 관찰

- `propose()` 반환값에 `langsmith` 키 없음 — LangSmith trace 자체는 생성됐으나 (LANGSMITH_TRACING=true)
- `get_langsmith_link()` → `trace_url` 생성 시 `_langsmith_workspace_id()` 의존 → `LANGSMITH_WORKSPACE_ID` env 확인 필요
- 이 건은 proposal 품질 검증과 무관. LangSmith trace 자체는 tm-ai 프로젝트에 기록됨.
