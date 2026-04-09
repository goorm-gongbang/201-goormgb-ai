# DB Build Task Execution Log

## Task 22

### 1. task 번호와 제목

- Task 22. LangSmith to Grafana 최소 공유 관제 계획서 작성

### 2. 작업 일시

- 2026-04-09 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/17-langsmith-grafana-minimum-shared-observability-plan.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `17-langsmith-grafana-minimum-shared-observability-plan.md`: 38번 LangSmith 최소 도입 문서의 후속으로, LangSmith를 원천 trace 저장소로 유지하면서 Grafana 공유 집계를 붙이는 최소 운영 계획을 정리했다. 핵심 보강점은 `scope_type`, nullable token/cost, overlap 조회, repair backfill, sync state, Grafana freshness 패널, 6개 작업 묶음이다.
- `task-execution-log.md`: 이번 문서 작성 작업을 후속 task로 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 관련 문서 확인
  - 명령: `sed -n '1,260p' src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/38-langsmith-minimum-adoption-work-plan.md`
  - 결과: 기존 LangSmith 최소 도입 범위와 용어를 확인했다.
  - 명령: `sed -n '1,260p' src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/15-langsmith-minimum-adoption-e2e-plan.md`
  - 결과: 15번 문서가 코드 착수 직전 E2E 체크리스트 성격임을 확인했다.
  - 명령: `sed -n '1,260p' src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log-langsmith.md`
  - 결과: LangSmith tracing helper, usage metadata, trace link, 실제 run 검증이 이미 끝난 상태임을 확인했다.
- 작업 로그 규칙 확인
  - 명령: `sed -n '1,260p' src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/agent.md`
  - 결과: 문서 task도 `task-execution-log.md`에 append해야 하는 규칙을 재확인했다.
- 번호 체계 확인
  - 명령: `find src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack -maxdepth 1 -type f | sort`
  - 결과: 다음 문서 번호로 `17-...`이 자연스럽다는 점을 확인했다.
- 현재 코드 전제 확인
  - 명령: `sed -n '1,260p' src/traffic_master_ai/defense/langsmith_support.py`
  - 결과: `runId`, `traceUrl`, project/workspace 기반 URL 조립 helper가 있음을 확인했다.
  - 명령: `sed -n '1,260p' src/traffic_master_ai/defense/backoffice_copilot/adapters/openai.py`
  - 결과: `feature_name`, `agent_step_name`, `environment`, `session_id`, `match_id`, `thread_id`, `owner_team` metadata가 이미 기록되고 있음을 확인했다.
  - 명령: `sed -n '1,260p' src/traffic_master_ai/defense/d0_mvp/optimizer/audit_summarizer.py`
  - 결과: `audit_summary` run이 `policy_version`, `window_start_ms`, `window_end_ms`와 함께 기록됨을 확인했다.
  - 명령: `sed -n '1,360p' src/traffic_master_ai/defense/d0_mvp/optimizer/effect_evaluator.py`
  - 결과: `evaluate_policy_effect` run에 `metrics_snapshot_id`, `policy_version`, token usage가 기록됨을 확인했다.

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - 이번 작업은 계획 문서만 추가한 상태라 exporter, DDL, dashboard는 아직 구현되지 않았다.
  - LangSmith run schema는 실제 exporter 구현 시 SDK 응답 기준으로 다시 맞춰야 한다.
- 다음 task에 넘길 입력
  - 후속 구현은 `DDL + exporter module + script entrypoint + 테스트`를 한 묶음으로 시작하는 것이 안전하다.
  - 첫 구현 우선순위는 `scope_type 계약 고정 -> run row normalize -> Postgres upsert -> dry-run 검증` 순서가 적절하다.

## Task 24

### 1. task 번호와 제목

- Task 24. Archive Interval 운영값 정리 및 즉시성 개선

### 2. 작업 일시

- 2026-04-09 10:50:11 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/storage_env.py`
- `src/traffic_master_ai/defense/api/archive_runtime.py`
- `src/traffic_master_ai/defense/api/main.py`
- `tests/defense/test_storage_env_config.py`
- `tests/defense/test_archive_loop_interval.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/09-env-failure-handling-test-plan.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. archive interval 변경 요약

- `TM_S3_ARCHIVE_INTERVAL_SECONDS` 기본값을 `3600`에서 `300`으로 낮췄다.
- staging 권장값은 `60`, prod 권장값은 `300`으로 문서화했다.
- `storage_env.py` loader가 `TM_S3_ARCHIVE_INTERVAL_SECONDS`를 positive int로 검증하도록 바꿨다.
- `main.py`는 더 이상 별도 `3600` 하드코드를 읽지 않고 shared env loader 기반 archive loop를 쓰도록 정리했다.
- archive loop 구현을 `api/archive_runtime.py`로 분리해 실제 sleep interval이 env 값을 따르는지 테스트로 잠갔다.

### 5. 검증에 사용한 명령과 결과 요약

- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/storage_env.py src/traffic_master_ai/defense/api/archive_runtime.py src/traffic_master_ai/defense/api/main.py tests/defense/test_storage_env_config.py tests/defense/test_archive_loop_interval.py`
  - 결과: 문법 오류 없음
- archive interval env / loop 회귀
  - 명령: `.venv/bin/pytest -q tests/defense/test_storage_env_config.py tests/defense/test_archive_loop_interval.py`
  - 결과: `16 passed`
- 문서 충돌 점검
  - 명령: `rg -n "3600|TM_S3_ARCHIVE_INTERVAL_SECONDS|archive interval" src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack src/traffic_master_ai/defense/storage_env.py tests/defense/test_storage_env_config.py tests/defense/test_archive_loop_interval.py src/traffic_master_ai/defense/api/main.py src/traffic_master_ai/defense/api/archive_runtime.py`
  - 결과: 관련 문서와 코드에서 새 기본값/권장값만 남고, 남은 `3600` 표기는 “권장하지 않음” 설명 용도뿐임을 확인했다.

### 6. 남은 리스크

- archive loop interval을 줄여도 ETL 주기 자체는 별도라 ClickHouse 반영 지연이 완전히 사라지는 것은 아니다.
- 너무 짧은 값은 S3 object 수 증가와 rotate/upload 빈도 증가를 만든다. 그래서 상시 운영값은 `staging 60`, `prod 300` 이상이 안전하다.
- 현재 loop는 단순 sleep 기반이라 scheduler, processed-key ledger, queueing은 여전히 운영 hardening backlog다.

### 7. 다음 task 입력

- 다음 우선순위는 archive -> ETL -> ClickHouse 반영 freshness를 실제 측정할 수 있게 freshness metric 또는 lag 확인 surface를 추가하는 것이다.
- 그 다음 단계로 ETL replay/processed 상태 hardening을 따로 분리해 `processed-key ledger` 또는 mark-processed orchestration을 설계하면 된다.

## Task 21

### 1. task 번호와 제목

- Task 21. Offline optimizer 정책 경계 리팩토링 계획서 작성

### 2. 작업 일시

- 2026-04-08 23:06:26 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/16-offline-optimizer-policy-boundary-refactor-plan.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `16-offline-optimizer-policy-boundary-refactor-plan.md`: optimizer 허용 범위와 금지 범위를 다시 나누는 리팩토링 계획서를 추가했다. 핵심 결정은 `risk/tier/throttle`만 optimizer 대상에 두고 `challenge.*`는 사용자 체감 플로우 보호를 위해 제외하는 것이다.
- `task-execution-log.md`: 이번 계획 문서 작성 작업을 기록했다.

### 5. 검증에 사용한 명령과 결과 요약

- 관련 문서/코드 탐색
  - 명령: `ls -1 src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack`
  - 결과: 기존 계획 문서와 작업 로그 위치를 확인했다.
  - 명령: `sed -n '1,220p' .../agent.md`
  - 결과: 문서 우선순위, 작업 로그 append 규칙, 최소 범위 원칙을 확인했다.
  - 명령: `sed -n '1,220p' src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_policy_optimization_ssot.yaml`
  - 결과: 현재 SSOT가 `challenge.*`를 optimizer tuning path로 포함하고 있음을 확인했다.
  - 명령: `sed -n '1,220p' src/traffic_master_ai/defense/d0_mvp/optimizer/validator.py`
  - 결과: validator allowlist, baseline, bounds가 `challenge.*`를 허용하고 있음을 확인했다.
  - 명령: `rg -n "challenge\\.max_attempts|challenge\\.cooldown_ms\\.first|challenge\\.cooldown_ms\\.second|challenge\\.halt_seconds" src/traffic_master_ai/defense/d0_mvp src/traffic_master_ai/defense/backoffice_copilot/specs`
  - 결과: 프롬프트, validator, SSOT, rule-based proposal까지 모두 같은 path를 열어 둔 상태임을 확인했다.

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - 지금은 계획 문서만 추가된 상태라 실제 코드와 SSOT는 아직 기존 경계를 유지한다.
  - `risk.probation_seconds`와 `planner.throttle_delay_ms.*`는 후속 task에서 제품 체감 관점 재검토가 필요할 수 있다.
- 다음 task에 넘길 입력
  - 후속 구현 task는 `effect_evaluator.py`, `validator.py`, `defense_policy_optimization_ssot.yaml`, `defense_llm_ssot.yaml`를 한 묶음으로 수정해야 한다.
  - 구현 우선순위는 `프롬프트 축소 -> validator allowlist 축소 -> rule-based proposal 제거 -> 테스트 보강` 순서가 안전하다.

## Task 20

### 1. task 번호와 제목

- Task 20. LangSmith E2E 후속 검증 완료: summary 성공, effect_evaluator timeout 해소

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

## Task 19

### 1. task 번호와 제목

- Task 19. OpenAI key 교체 후 LangSmith 성공 run 검증 완료

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

## Task 18

### 1. task 번호와 제목

- Task 18. LangSmith workspace / OpenAI key 원인 분리 및 설정 보정

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

## Task 17

### 1. task 번호와 제목

- Task 17. LangSmith 최소 도입 실제 검증 수행

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
  - 명령: `python3 -m pip install -e .`
  - 결과: PEP 668 `externally-managed-environment`로 차단
- 검증용 venv 생성 및 설치
  - 명령: `python3 -m venv .venv-langsmith-check`
  - 명령: `./.venv-langsmith-check/bin/python -m pip install -e .`
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

## Task 16

### 1. task 번호와 제목

- Task 16. Backoffice Copilot OpenAI adapter LangSmith 최소 tracing 1차 적용

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

## Task 15

### 1. task 번호와 제목

- Task 15. LangSmith 최소 도입 E2E 작업 문서 작성

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

## Task 1

### 1. task 번호와 제목

- Task 1. canonical audit 최소 필드 확정

### 2. 작업 일시

- backfill from user-reported result after Task 1 completion

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/04-canonical-audit-minimum-contract.md`

### 4. 파일별 수정 요약

- `04-canonical-audit-minimum-contract.md`: 현재 코드와 목표 구조의 충돌을 먼저 드러내고, 최소 typed field 목록, JSON 보존 컬럼 후보, 현재 코드와의 gap 메모, 현재 기준 안전한 join 관점, privacy 및 undocumented 금지 필드만 최소 범위로 고정했다.

### 5. 검증에 사용한 명령과 결과 요약

- 수동 문서 대조
  - 기준 문서: `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `31-observability-merge-strategy.md`, `defense_observability_ssot.yaml`, `audit.py`, `main.py`
  - 결과: 문서 간 목표 구조와 현재 코드 공백을 숨기지 않고 정리했으며, Task 2 입력으로 사용할 최소 계약과 모순이 없도록 확인했다.
- 관련 테스트 파일 탐색
  - 결과: canonical audit payload 계약을 직접 잠그는 관련 테스트 파일은 찾지 못했다.

### 6. 남은 리스크 또는 다음 task에 넘길 입력

- 남은 리스크
  - `event_type` taxonomy가 SSOT와 현재 코드 사이에서 다르다.
  - `action` enum이 target 의미와 완전히 정렬되지 않았다.
  - `match_id`가 canonical audit top-level typed field로 안정적으로 보장되지 않는다.
- Task 2에 넘길 입력
  - non-null typed field: `ts_ms`, `session_id`, `event_type`
  - nullable typed field: `trace_id`, `challenge_id`, `flow_state`, `risk_tier`, `action`, `reason_code`, `policy_version`
  - JSON preservation: `raw_payload_json`
  - 기본 join guidance: `session_id + ts_ms window`
  - explicit gap: `match_id`, `http_status`, `dedup_is_duplicate`, rollout fields, VQA typed fields

## Task 2

### 1. task 번호와 제목

- Task 2. ClickHouse `defense_audit_events` 최소 DDL 초안 작성

### 2. 작업 일시

- 2026-04-06 02:01:45 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/05-defense-audit-events-minimum-ddl.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `05-defense-audit-events-minimum-ddl.md`: Task 1 최소 계약을 입력으로 받아 `defense_audit_events` 최소 raw fact DDL 초안을 문서화했다. non-null typed column, nullable typed column, `raw_payload_json` 보존 컬럼, partition key, order key, 현재 코드 매핑 여부, explicit gap, 적재 가정, Task 3 입력을 함께 고정했다.
- `task-execution-log.md`: Task 2 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 입력 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `04-canonical-audit-minimum-contract.md`, `31-observability-merge-strategy.md`, `defense_observability_ssot.yaml`, `audit.py`, `main.py`
  - 결과: Task 1 최소 계약과 일관된 최소 DDL만 남기고, `match_id`/dedup/VQA/rollout 계열은 explicit gap으로 분리했다.
- 민감 필드 위치 확인
  - 명령: `rg -n "active_challenge_token|user_id|challenge_token|Authorization|headers" src/traffic_master_ai/defense/api/models.py src/traffic_master_ai/defense/api/main.py src/traffic_master_ai/defense/api/audit.py`
  - 결과: `runtime_state` blind copy는 privacy 규칙과 충돌하므로 `raw_payload_json`은 sanitation 후 보존해야 한다는 메모를 DDL 문서에 반영했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:01:45 KST`

### 6. 남은 리스크 또는 Task 3에 넘길 입력

- 남은 리스크
  - 현재 `event_type` taxonomy가 SSOT authoritative catalog와 다르다.
  - `action` enum 의미가 target semantics와 완전히 정렬되지 않았다.
  - `raw_payload_json`은 blind raw copy가 아니라 sanitation 전제가 필요하다.
  - `match_id`가 top-level typed field로 보장되지 않아 match-centric rollup은 후속 보강이 필요하다.
- Task 3에 넘길 입력
  - raw fact stable columns: `ts_ms`, `session_id`, `event_type`, `trace_id`, `challenge_id`, `flow_state`, `risk_tier`, `action`, `reason_code`, `policy_version`
  - JSON preservation: `raw_payload_json`
  - 기본 join guidance: `session_id + ts_ms window`
  - weak axes kept as gap: `match_id`, dedup, challenge typed result, VQA typed fields, rollout fields

## Task 3

### 1. task 번호와 제목

- Task 3. session rollup / match rollup / candidate view 최소 계약 확정

### 2. 작업 일시

- 2026-04-06 02:06:36 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/06-rollup-candidate-minimum-contract.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `06-rollup-candidate-minimum-contract.md`: Task 1/2 raw fact 계약을 입력으로 받아 `defense_session_rollups`, `defense_match_rollups`, `defense_post_review_candidates_v1`의 최소 컬럼/selection/consumer boundary를 문서로 고정했다. raw fact / session rollup / match rollup / candidate / final result store의 역할 분리, 기본 join 방식, 현재 코드 gap, Task 4 경계를 함께 기록했다.
- `task-execution-log.md`: Task 3 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 문서 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `04-canonical-audit-minimum-contract.md`, `05-defense-audit-events-minimum-ddl.md`, `31-observability-merge-strategy.md`, `defense_observability_ssot.yaml`, `audit.py`, `main.py`
  - 결과: session rollup은 Backoffice 1차 입력, match rollup은 운영 요약, candidate view는 selection layer로만 고정했고 final result 저장 책임과 섞지 않았다.
- 관련 섹션 탐색
  - 명령: `rg -n "Session rollup table|Match rollup table|candidate view|defense_session_rollups|defense_match_rollups|defense_post_review_candidates_v1|session_id \\+ 시간 구간|Backoffice Copilot|Grafana|운영 배치" src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/32-storage-architecture.md src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/31-observability-merge-strategy.md`
  - 결과: `32`의 역할 분리와 `31`의 소비자/조인 원칙을 직접 확인해 문서에 반영했다.
- 현재 코드 필드 위치 확인
  - 명령: `rg -n "match_id|matchId|session_id|sessionId|challenge_id|challengeId|reasonCodes|vqaAttemptScore|flow_state|telemetry_features" src/traffic_master_ai/defense/api/main.py src/traffic_master_ai/defense/api/audit.py`
  - 결과: `match_id`는 일부 payload/state key 수준에 머물고, `session_id`도 일부 경로에서 `sid:matchId` alias를 쓰므로 session/window 기준 계약이 더 안전하다는 점을 gap으로 명시했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:06:36 KST`

### 6. 남은 리스크 또는 Task 4에 넘길 입력

- 남은 리스크
  - `match_id`가 raw fact typed column으로 아직 잠기지 않아 `defense_match_rollups`는 target-direction contract에 가깝다.
  - 일부 challenge/VQA row의 `session_id`가 state-key alias를 쓰므로 session identity canonicalization이 후속 과제다.
  - challenge result / VQA result / dedup 집계는 현재 최소 계약에서 제외했다.
- Task 4에 넘길 입력
  - observability read contract boundary: raw fact / session rollup / match rollup / candidate / final result store 역할 분리
  - 기본 join guidance: `session_id + 시간 구간`
  - Backoffice primary input: `defense_session_rollups`, `defense_post_review_candidates_v1`
  - ops summary input: `defense_match_rollups`
  - explicit gap to keep out of control-plane DDL: `match_id`, dedup, challenge/VQA typed aggregation, rollout/policy comparison fields

## Task 4

### 1. task 번호와 제목

- Task 4. PostgreSQL policy control-plane 최소 DDL 초안 작성

### 2. 작업 일시

- 2026-04-06 02:10:10 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/07-policy-control-plane-minimum-ddl.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `07-policy-control-plane-minimum-ddl.md`: `policy_versions`, `policy_rollout_state`, `policy_rollout_events`, `policy_optimization_runs`의 최소 PostgreSQL DDL 초안을 문서화했다. authoritative control-plane과 Redis runtime projection 책임 분리, 현재 코드 매핑 여부, naming mismatch, Task 5 projection 입력을 함께 고정했다.
- `task-execution-log.md`: Task 4 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `06-rollup-candidate-minimum-contract.md`, `policy_v1.yaml`, `defense_policy_optimization_ssot.yaml`, `runtime.py`, `loader.py`, `keyspace.py`, `rollout.py`
  - 결과: observability 축과 섞지 않고 policy control-plane 4테이블 최소 계약만 남겼다.
- 현재 policy/runtime 흐름 확인
  - 명령: `rg -n "policy|rollout|projection|redis|policy_version|candidate|base_policy|rollout_state|tm:decision-policy|assign" src/traffic_master_ai/defense/d0_mvp/api/runtime.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/state/keyspace.py src/traffic_master_ai/defense/d0_mvp/optimizer/rollout.py`
  - 결과: runtime authority는 Redis-first이고 PostgreSQL control-plane은 아직 미구현이라는 점을 gap으로 기록했다.
- 추가 세부 확인
  - 명령: `sed -n '200,240p' src/traffic_master_ai/defense/d0_mvp/api/runtime.py`
  - 결과: bootstrap 시 Redis policy authority와 file fallback만 사용하는 점을 확인했다.
  - 명령: `sed -n '340,430p' src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
  - 결과: policy 문서 직렬화 구조와 rollout state 저장 shape를 확인했다.
  - 명령: `sed -n '90,220p' src/traffic_master_ai/defense/d0_mvp/optimizer/pipeline.py`
  - 결과: optimization run / canary / rollback audit payload에서 `metrics_snapshot_id`, `result`, `new_policy_version` 등의 최소 메타 필드를 확인했다.
- 구현 공백 탐색
  - 명령: `rg -n "policy_versions|policy_rollout_state|policy_rollout_events|policy_optimization_runs" src/traffic_master_ai/defense -g '!**/.venv/**'`
  - 결과: current code에는 PostgreSQL control-plane 4테이블 구현이 없고, 문서/loader 수준 계약만 존재함을 확인했다.
- 테스트 파일 탐색
  - 명령: `rg --files src/traffic_master_ai/defense | rg "test|tests"`
  - 결과: 관련 테스트 파일을 찾지 못했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:10:10 KST`

### 6. 남은 리스크 또는 Task 5에 넘길 입력

- 남은 리스크
  - current runtime은 PostgreSQL control-plane을 전혀 읽지 않고 Redis/file store를 사용한다.
  - `tm:policy:*` vs `tm:decision-policy:*` naming mismatch가 문서와 코드 사이에 남아 있다.
  - DB용 `run_id` / `rollout_id` / `event_id`는 current code에 없어 projection/ingest 설계가 후속 과제다.
- Task 5에 넘길 입력
  - authoritative source tables: `policy_versions`, `policy_rollout_state`, `policy_rollout_events`, `policy_optimization_runs`
  - Redis projection targets: `tm:decision-policy:version:{policyVersion}`, `tm:decision-policy:rollout-state`, `tm:decision-policy:version-index`
  - runtime read rule: PostgreSQL direct read 금지, Redis projection만 사용
  - explicit gap: key naming mismatch, DB identity fields 신규 도입, bootstrap rollout state vs DB authoritative state shape 차이

## Task 5

### 1. task 번호와 제목

- Task 5. PostgreSQL -> Redis projection 계약 문서화

### 2. 작업 일시

- 2026-04-06 02:14:51 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/08-postgresql-to-redis-projection-contract.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `08-postgresql-to-redis-projection-contract.md`: PostgreSQL authoritative control-plane에서 Redis runtime projection으로 내려가는 최소 계약을 문서화했다. projection 대상 key 3종, 각 key의 최소 payload, source mapping, apply ordering, projection failure 규칙, runtime read path와 projection worker 경계를 함께 고정했다.
- `task-execution-log.md`: Task 5 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `07-policy-control-plane-minimum-ddl.md`, `policy_v1.yaml`, `defense_policy_optimization_ssot.yaml`, `runtime.py`, `loader.py`, `keyspace.py`, `rollout.py`
  - 결과: PostgreSQL authoritative source와 Redis projection 책임을 분리하고, request path direct PostgreSQL 금지 원칙을 유지한 최소 계약만 남겼다.
- 현재 Redis keyspace / read path 확인
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/state/keyspace.py | sed -n '1,220p'`
  - 결과: 현재 코드 keyspace가 `tm:decision-policy:version:{policyVersion}`, `tm:decision-policy:rollout-state`, `tm:decision-policy:version-index`임을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/policy/loader.py | sed -n '1,220p'`
  - 결과: Redis policy store가 version doc JSON, rollout state JSON, version index JSON array를 읽고 쓴다는 점을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/policy/loader.py | sed -n '220,360p'`
  - 결과: runtime selection이 `stage`, `base_policy_version`, `candidate_policy_version`, `ratio`에 의존하고 `current_version` 키를 읽지 않는다는 점을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/api/runtime.py | sed -n '200,280p'`
  - 결과: bootstrap이 Redis-first + file fallback이며 PostgreSQL direct read가 없다는 점을 확인했다.
- rollout state shape 확인
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/optimizer/rollout.py | sed -n '1,240p'`
  - 결과: authoritative rollout state에는 더 많은 필드가 있지만 runtime minimum payload는 더 작게 유지할 수 있음을 확인했다.
- SSOT key naming / contract 확인
  - 명령: `rg -n "tm:policy|tm:decision-policy|rollout_state|policyVersion|version-index|projection|baseline|fallback" src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/policy_v1.yaml src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_policy_optimization_ssot.yaml`
  - 결과: `tm:policy:*` vs `tm:decision-policy:*` naming mismatch와 runtime authority/fallback 의미를 명시적 gap으로 기록했다.
- 테스트 파일 탐색
  - 명령: `rg --files src/traffic_master_ai/defense | rg "test|tests"`
  - 결과: 관련 테스트 파일을 찾지 못했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:14:51 KST`

### 6. 남은 리스크 또는 Task 6에 넘길 입력

- 남은 리스크
  - 현재 코드에는 PostgreSQL -> Redis projection worker와 retry/reconcile 구현이 없다.
  - `policy_v1.yaml`의 `tm:policy:*` 예시와 current code `tm:decision-policy:*` keyspace가 아직 다르다.
  - current bootstrap baseline write는 prod projection contract와 다르다.
- Task 6에 넘길 입력
  - authoritative source: `policy_versions.document_json`, `policy_rollout_state` current authoritative row
  - Redis target keys: `tm:decision-policy:version:{policyVersion}`, `tm:decision-policy:rollout-state`, `tm:decision-policy:version-index`
  - minimum payload: version doc `schemaVersion + parameters + flags`, rollout state `stage + base_policy_version + candidate_policy_version + ratio + updated_at_ms`, version index string array
  - apply ordering: PostgreSQL commit -> referenced version docs -> rollout-state -> version-index
  - failure scenarios: PostgreSQL write fail, Redis projection fail after PG success, Redis eviction, runtime direct PostgreSQL read 금지 유지

## Task 6

### 1. task 번호와 제목

- Task 6. env / failure handling / test plan 정리

### 2. 작업 일시

- 2026-04-06 02:20:06 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/09-env-failure-handling-test-plan.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `09-env-failure-handling-test-plan.md`: 최소 env 변수 목록, env 누락 시 계층별 기대 동작, audit/S3/warehouse/control-plane/projection/runtime failure 규칙, replay/retry/backfill 지점, unit/contract/integration/smoke test 최소 계획, Task 7 구현 검증 기준을 문서로 고정했다.
- `task-execution-log.md`: Task 6 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `31-observability-merge-strategy.md`, `task-execution-log.md`, `08-postgresql-to-redis-projection-contract.md`, `defense_observability_ssot.yaml`, `policy_v1.yaml`, `defense_policy_optimization_ssot.yaml`, `audit.py`, `etl_worker.py`, `runtime.py`, `loader.py`, `keyspace.py`
  - 결과: storage/projection 계약과 충돌하지 않도록 운영 준비용 최소 env/failure/test 규칙만 남겼다.
- 현재 env / adapter 의존성 확인
  - 명령: `rg -n "TM_[A-Z0-9_]+|DATABASE_URL|POSTGRES|CLICKHOUSE|REDIS|S3_BUCKET|S3_REGION|boto3|create_engine|redis\\.from_url|from_env\\(" src/traffic_master_ai/defense -g '!**/.venv/**'`
  - 결과: 현재 코드에 존재하는 `TM_PG_URL`, `TM_REDIS_URL`, `TM_S3_*`, `TM_DEFENSE_AUDIT_LOG_PATH`, `TM_ROLLOUT_SALT`, `TM_POLICY_CACHE_SECONDS`와 ClickHouse 미구현 공백을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/api/database.py | sed -n '1,220p'`
  - 결과: current PostgreSQL 연결 관례가 `TM_PG_URL`임을 확인했다.
- failure path 확인
  - 명령: `nl -ba src/traffic_master_ai/defense/api/audit.py | sed -n '1,360p'`
  - 결과: rotate/upload 실패 시 rotated local file이 남고, `TM_DEFENSE_AUDIT_LOG_PATH` default가 존재함을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/api/etl_worker.py | sed -n '1,360p'`
  - 결과: current ETL이 S3 -> PostgreSQL prototype이며 `TM_S3_BUCKET` 없으면 실행하지 않는다는 점을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/api/runtime.py | sed -n '1110,1205p'`
  - 결과: audit append 실패가 request path를 즉시 중단시키지 않고 exception log로만 드러난다는 점을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/api/state.py | sed -n '80,150p'`
  - 결과: non-CI에서 `TM_REDIS_URL` 누락 시 fail-fast, CI에서만 memory fallback이라는 점을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/state/redis_client.py | sed -n '140,210p'`
  - 결과: d0_mvp Redis backend도 같은 fail-fast 정책을 유지함을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/policy/loader.py | sed -n '74,155p'`
  - 결과: policy runtime authority는 Redis-first이고 file fallback이 남아 있음을 확인했다.
- 테스트 파일 탐색
  - 명령: `rg --files src/traffic_master_ai/defense | rg "test|tests"`
  - 결과: 관련 테스트 파일을 찾지 못했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:20:06 KST`

### 6. 남은 리스크 또는 Task 7에 넘길 입력

- 남은 리스크
  - ClickHouse adapter / ETL / rollup 구현이 아직 없어 warehouse env와 retry 정책은 planned contract 상태다.
  - PostgreSQL control-plane과 projection worker가 아직 없어 projection failure handling은 설계 단계다.
  - 현재 audit append failure는 log에만 드러나며 별도 metric/alert contract는 없다.
- Task 7에 넘길 입력
  - minimum env surface: `TM_DEFENSE_AUDIT_LOG_PATH`, `TM_S3_BUCKET`, `TM_S3_REGION`, `TM_S3_PREFIX`, `TM_S3_ARCHIVE_INTERVAL_SECONDS`, `TM_PG_URL`, `TM_REDIS_URL`, `TM_ROLLOUT_SALT`, `TM_POLICY_CACHE_SECONDS`, planned `TM_CLICKHOUSE_*`
  - fail-fast rules: non-CI `TM_REDIS_URL` 누락, PostgreSQL write 실패 시 projection 금지, ClickHouse env 누락 시 ingest worker 시작 금지
  - fail-safe rules: S3 archive 비활성 허용, audit append failure는 request path 지속 + log 노출, Redis stale-read 후 reconcile
  - replay/backfill source: rotated local files / S3 archive / PostgreSQL authoritative tables
  - test slices: unit env parsing, contract schema mapping, integration ingest/projection/runtime read, smoke startup/env enforcement

## Task 7

### 1. task 번호와 제목

- Task 7. repository / adapter 경계 정리

### 2. 작업 일시

- 2026-04-06 02:42:44 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/10-repository-adapter-boundary.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `10-repository-adapter-boundary.md`: ClickHouse raw fact, session rollup/candidate read model, PostgreSQL control-plane, PostgreSQL -> Redis projection, runtime read path, S3 archive/replay source의 repository / adapter 경계를 문서로 고정했다. 각 계층의 책임, 입출력, 금지 책임, 최소 호출 관계, 구현 순서를 함께 정리했다.
- `task-execution-log.md`: Task 7 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/산출물 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `05-defense-audit-events-minimum-ddl.md`, `06-rollup-candidate-minimum-contract.md`, `07-policy-control-plane-minimum-ddl.md`, `08-postgresql-to-redis-projection-contract.md`, `09-env-failure-handling-test-plan.md`
  - 결과: raw fact / read model / control-plane / projection / runtime read 경계가 앞선 계약과 모순되지 않도록 정리했다.
- 현재 코드 흐름 확인
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py | sed -n '1,360p'`
  - 결과: `AuditWarehouse`가 ClickHouse repository가 아니라 local JSONL warehouse adapter임을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/api/etl_worker.py | sed -n '1,360p'`
  - 결과: current ETL이 S3 -> PostgreSQL prototype insert를 직접 수행하고 있음을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/policy/loader.py | sed -n '74,155p'`
  - 결과: Redis key read/write, version index 관리, file fallback이 loader에 섞여 있음을 확인했다.
  - 명령: `nl -ba src/traffic_master_ai/defense/d0_mvp/state/keyspace.py | sed -n '1,220p'`
  - 결과: Redis projection keyspace가 `tm:decision-policy:*`로 고정돼 있음을 확인했다.
- 테스트 파일 탐색
  - 명령: `rg --files src/traffic_master_ai/defense | rg "test|tests"`
  - 결과: 관련 테스트 파일을 찾지 못했다.
- 작업 일시 기록
  - 명령: `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S %Z'`
  - 결과: `2026-04-06 02:42:44 KST`

### 6. 남은 리스크 또는 구현 단계(Task 8+)에 넘길 입력

- 남은 리스크
  - current code에는 ClickHouse repository, PostgreSQL control-plane repository, Redis projection repository가 전혀 구현돼 있지 않다.
  - `PolicyLoader`와 `AuditWarehouse`가 아직 storage concern과 adapter concern을 함께 가진다.
  - S3 -> ClickHouse ingest와 projection worker 호출 경계는 문서 계약만 있고 실행 코드는 없다.
- Task 8+에 넘길 입력
  - ClickHouse raw fact writer/reader repo 분리
  - session rollup / candidate read repository 분리
  - PostgreSQL control-plane repository 4종
  - Redis projection repository + projection adapter
  - runtime read adapter에서 PostgreSQL direct read 금지 유지
  - S3 archive repo + replay source adapter 분리

## Task 8

### 1. task 번호와 제목

- Task 8. ClickHouse / PostgreSQL 최소 DDL을 실제 SQL 파일로 반영

### 2. 작업 일시

- 2026-04-06 09:44:48 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/storage/sql/002_postgresql_policy_control_plane_tables.sql`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `002_postgresql_policy_control_plane_tables.sql`: Task 4 최소 DDL 초안을 실제 PostgreSQL SQL 파일로 옮겼다. `policy_versions`, `policy_rollout_state`, `policy_rollout_events`, `policy_optimization_runs` 4테이블만 반영했고, 상단 주석에 canonical source와 runtime direct PostgreSQL read 금지 메모를 남겼다.
- `003_clickhouse_defense_audit_events.sql`: Task 2 최소 DDL 초안을 실제 ClickHouse SQL 파일로 옮겼다. `defense_audit_events` raw fact 최소 컬럼, day partition, `(session_id, ts_ms, event_type)` order key만 반영했고, 상단 주석에 canonical source와 current `etl_worker.py` PostgreSQL prototype gap 메모를 남겼다.
- `task-execution-log.md`: Task 8 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `05-defense-audit-events-minimum-ddl.md`, `07-policy-control-plane-minimum-ddl.md`, `10-repository-adapter-boundary.md`, `001_post_review_tables.sql`, `etl_worker.py`, `warehouse.py`
  - 결과: Task 2/4 최소 계약만 실제 SQL로 옮겼고, current code의 `etl_worker.py` PostgreSQL prototype / `AuditWarehouse` JSONL MVP gap을 숨기지 않도록 파일 주석과 결과 메모에 반영했다.
- SQL 파일 배치 확인
  - 명령: `rg --files src/traffic_master_ai/defense/backoffice_copilot/storage/sql`
  - 결과: `001_post_review_tables.sql`, `002_postgresql_policy_control_plane_tables.sql`, `003_clickhouse_defense_audit_events.sql` 3개 파일이 같은 디렉터리에 정리됐고, 새 파일명에서 엔진 책임이 바로 드러난다.
- canonical source / DDL shape 확인
  - 명령: `rg -n "Canonical source|CREATE TABLE IF NOT EXISTS|policy_versions|policy_rollout_state|policy_rollout_events|policy_optimization_runs|defense_audit_events|ENGINE = MergeTree|PARTITION BY|ORDER BY" src/traffic_master_ai/defense/backoffice_copilot/storage/sql/002_postgresql_policy_control_plane_tables.sql src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql`
  - 결과: PostgreSQL 4테이블, ClickHouse 1테이블, 상단 canonical source 주석, MergeTree / partition / order key가 기대한 위치에 존재함을 확인했다.
- ClickHouse 최소 컬럼 범위 확인
  - 명령: `rg -n "match_id|http_status|dedup_is_duplicate|requested_policy_version|rollout_stage|challenge_result|challenge_reason_code|vqa_attempt_score|vqa_terminal" src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql`
  - 결과: 매치 없음. Task 2에서 explicit gap으로 남긴 out-of-scope typed field가 실제 SQL에 추가되지 않았다.
- CREATE TABLE 개수 확인
  - 명령: `python3 - <<'PY' ...`
  - 결과: `002_postgresql_policy_control_plane_tables.sql: create_table_count=4`, `003_clickhouse_defense_audit_events.sql: create_table_count=1`
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/backoffice_copilot/storage/sql/002_postgresql_policy_control_plane_tables.sql src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크 또는 Task 9에 넘길 입력

- 남은 리스크
  - current `etl_worker.py`는 여전히 S3 -> PostgreSQL `defense_audit_events` prototype이라 새 ClickHouse DDL과 실행 경로가 연결돼 있지 않다.
  - `storage/sql` 루트에 PostgreSQL과 ClickHouse SQL이 함께 있으므로 실제 apply 단계에서는 엔진별 선택 실행 규칙이 필요하다.
  - repository / adapter / projection worker 구현은 아직 없어 이번 산출물은 DDL 고정 단계에 머문다.
- Task 9에 넘길 입력
  - ClickHouse raw fact target SQL: `src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql`
  - PostgreSQL control-plane target SQL: `src/traffic_master_ai/defense/backoffice_copilot/storage/sql/002_postgresql_policy_control_plane_tables.sql`
  - current code conflict memo: `src/traffic_master_ai/defense/api/etl_worker.py`는 PostgreSQL prototype, `src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py`는 JSONL MVP이므로 Task 9는 repository/adapter wiring 시 이 과도기 경로를 정리해야 한다.

## Task 9

### 1. task 번호와 제목

- Task 9. ClickHouse raw fact writer / repository skeleton 작성

### 2. 작업 일시

- 2026-04-06 09:49:55 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_validators.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py`
- `tests/defense/test_backoffice_copilot_clickhouse_storage.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `clickhouse_connection.py`: 실제 네트워크 연결 구현 대신 `ClickHouseBatchWriteClient` protocol, `ClickHouseWriteConfig`, `TM_CLICKHOUSE_AUDIT_TABLE` 기반 최소 table-name env surface만 추가했다.
- `clickhouse_validators.py`: Task 2 DDL과 동일한 최소 typed column만 담는 `ClickHouseAuditEventInsertRow` DTO와 validator / serializer를 추가했다. `match_id`, `http_status`, dedup, rollout, VQA typed field는 넣지 않았다.
- `clickhouse_repository.py`: `ClickHouseAuditEventWriterRepository` skeleton, `ClickHouseAuditEventWriteRepository` protocol, `ClickHouseBatchWriteRequest`, batch insert SQL surface, `write_batch` / `write_batch_request` entrypoint를 추가했다. real client build, retry, async insert, sanitation adapter는 explicit gap으로 남겼다.
- `storage/__init__.py`: 새 ClickHouse writer / contract surface를 외부 import 가능하게 export했다.
- `test_backoffice_copilot_clickhouse_storage.py`: DTO 최소 계약, invalid row rejection, batch write SQL surface, empty batch semantics, env table-name override를 검증하는 `unittest` smoke를 추가했다.
- `task-execution-log.md`: Task 9 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `10-repository-adapter-boundary.md`, `05-defense-audit-events-minimum-ddl.md`, `003_clickhouse_defense_audit_events.sql`, `etl_worker.py`, `warehouse.py`, `audit.py`, 기존 `storage/repository.py`
  - 결과: writer skeleton 범위를 raw fact write 경계로만 제한했고, current `etl_worker.py` PostgreSQL prototype / `AuditWarehouse` JSONL MVP와 직접 충돌하지 않도록 별도 ClickHouse surface로 추가했다.
- writer / DTO 정의 위치 확인
  - 명령: `rg -n "ClickHouseAuditEventWriterRepository|ClickHouseAuditEventWriteRepository|ClickHouseBatchWriteRequest|write_batch|write_batch_request|INSERT INTO" src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_repository.py`
  - 결과: boundary 문서 이름과 맞는 repository skeleton, explicit batch request DTO, batch entrypoint, fixed insert SQL surface가 존재함을 확인했다.
  - 명령: `rg -n "ClickHouseAuditEventInsertRow|ts_ms|session_id|event_type|trace_id|challenge_id|flow_state|risk_tier|action|reason_code|policy_version|raw_payload_json" src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_validators.py`
  - 결과: Task 2 최소 DDL 컬럼과 동일한 insert DTO/serializer만 존재하고 out-of-scope typed field가 추가되지 않았음을 확인했다.
- 단위 테스트 / smoke
  - 명령: `python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage`
  - 결과: 실패. `PYTHONPATH=src` 없이 실행되어 `ModuleNotFoundError: No module named 'traffic_master_ai'` 발생
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage`
  - 결과: `Ran 5 tests in 0.001s`, `OK`
  - 명령: `PYTHONPATH=src python3 - <<'PY' ...`
  - 결과: `clickhouse-writer-smoke-ok`
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_validators.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py tests/defense/test_backoffice_copilot_clickhouse_storage.py`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크 또는 Task 10에 넘길 입력

- 남은 리스크
  - repository skeleton은 injected client의 `execute(sql_text, rows)` contract만 잠갔고, 실제 ClickHouse driver 선택 / auth / retry / async insert / partial failure 해석은 아직 미구현이다.
  - `raw_payload_json` sanitation과 `risk_tier <- defense_tier` rename은 writer가 아니라 future `CanonicalAuditRowAdapter` 책임으로 남겨 두었다.
  - current `etl_worker.py`는 여전히 PostgreSQL prototype이고, 새 repository와 연결하는 collector/ETL orchestration은 아직 없다.
- Task 10에 넘길 입력
  - writer contract: `ClickHouseAuditEventWriterRepository.write_batch()`와 `write_batch_request()`를 raw fact write surface로 사용
  - insert DTO: `ClickHouseAuditEventInsertRow`
  - serializer output columns: `ts_ms`, `session_id`, `event_type`, `trace_id`, `challenge_id`, `flow_state`, `risk_tier`, `action`, `reason_code`, `policy_version`, `raw_payload_json`
  - injected client contract: `ClickHouseBatchWriteClient.execute(sql_text, rows)`
  - explicit future adapter work: `audit.py` row -> sanitized insert DTO mapping, privacy-safe `raw_payload_json`, evaluate/challenge row split handling
  - reader task guardrail: session/window drill-down read만 구현하고 rollup / candidate / policy logic를 reader에 섞지 말 것

## Task 10

### 1. task 번호와 제목

- Task 10. ClickHouse session rollup / candidate read model reader 구현

### 2. 작업 일시

- 2026-04-06 09:55:59 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py`
- `tests/defense/test_backoffice_copilot_clickhouse_read_models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `clickhouse_read_models.py`: Task 3 최소 계약 그대로 `ClickHouseSessionRollupQuery`, `ClickHousePostReviewCandidateQuery`, `ClickHouseSessionRollupRow`, `ClickHousePostReviewCandidateRow`, `BackofficeClickHouseReadModelInput`을 추가했다. read contract를 window-centric으로 유지했고 `match_id` 중심 계약은 넣지 않았다.
- `clickhouse_read_repository.py`: `ClickHouseSessionRollupReadRepository`, `ClickHousePostReviewCandidateReadRepository`, 두 concrete reader skeleton, 그리고 raw fact를 거치지 않는 `load_backoffice_clickhouse_read_model_input()` surface를 추가했다. rollup 계산, candidate scoring, final decision, control-plane logic는 넣지 않았다.
- `clickhouse_connection.py`: reader skeleton이 요구하는 `ClickHouseSelectClient` protocol과 `ClickHouseReadModelConfig`, default table/view name 상수를 추가했다. 실제 driver/auth wiring은 여전히 후속 과제로 남겨 두었다.
- `storage/__init__.py`: 새 reader / DTO / bundle surface를 외부 import 가능하게 export했다.
- `test_backoffice_copilot_clickhouse_read_models.py`: session rollup read contract, candidate read contract, reader 책임 분리, Backoffice bundle이 raw fact를 직접 읽지 않는 점을 검증하는 `unittest` smoke를 추가했다.
- `task-execution-log.md`: Task 10 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `06-rollup-candidate-minimum-contract.md`, `10-repository-adapter-boundary.md`, `003_clickhouse_defense_audit_events.sql`, `clickhouse_repository.py`, `warehouse.py`, `etl_worker.py`, `workflow/nodes.py`
  - 결과: reader 범위를 session rollup / candidate read model 경계로만 제한했고, current workflow가 아직 JSONL raw fact를 읽는 현실을 숨기지 않은 채 later wiring용 surface를 별도 추가했다.
- read contract / reader surface 확인
  - 명령: `rg -n "ClickHouseSessionRollupQuery|ClickHousePostReviewCandidateQuery|ClickHouseSessionRollupRow|ClickHousePostReviewCandidateRow|BackofficeClickHouseReadModelInput" src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py`
  - 결과: session rollup read contract, candidate read contract, Backoffice bundle surface가 각각 고정돼 있음을 확인했다.
  - 명령: `rg -n "ClickHouseSessionRollupReadRepository|ClickHousePostReviewCandidateReadRepository|ClickHouseSessionRollupReaderRepository|ClickHousePostReviewCandidateReaderRepository|load_backoffice_clickhouse_read_model_input" src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_repository.py`
  - 결과: reader 책임이 session rollup과 candidate view로 분리돼 있고 raw fact reader / control-plane logic와 섞이지 않음을 확인했다.
- 단위 테스트 / smoke
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models`
  - 결과: `Ran 10 tests`, `OK`
  - 명령: `PYTHONPATH=src python3 - <<'PY' ...`
  - 결과: `clickhouse-read-model-smoke-ok`
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py tests/defense/test_backoffice_copilot_clickhouse_read_models.py`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크 또는 Task 11에 넘길 입력

- 남은 리스크
  - `defense_session_rollups`와 `defense_post_review_candidates_v1` 자체는 아직 SQL/MV로 materialize되지 않았고, 이번 작업은 reader contract만 고정했다.
  - current workflow `node_1_input_collection`은 여전히 JSONL raw fact `load_analysis_input()`를 사용하므로 새 read-model bundle과 실제 연결은 후속 wiring task가 필요하다.
  - query placeholder syntax와 actual ClickHouse driver binding 방식은 아직 미구현이다.
- Task 11에 넘길 입력
  - observability read-model contracts: `ClickHouseSessionRollupQuery`, `ClickHousePostReviewCandidateQuery`, `ClickHouseSessionRollupRow`, `ClickHousePostReviewCandidateRow`
  - Backoffice input surface: `load_backoffice_clickhouse_read_model_input() -> BackofficeClickHouseReadModelInput`
  - reader repositories: `ClickHouseSessionRollupReaderRepository`, `ClickHousePostReviewCandidateReaderRepository`
  - control-plane non-conflict memo: 이번 reader 구현은 ClickHouse observability read model만 다루며 PostgreSQL `policy_versions` / `policy_rollout_state` / `policy_rollout_events` / `policy_optimization_runs` repository 범위와 겹치지 않는다.
  - future wiring gap: workflow entrypoint를 raw fact JSONL 대신 read-model bundle로 전환하는 adapter가 아직 없다.

## Task 11

### 1. task 번호와 제목

- Task 11. PostgreSQL policy control-plane repository 구현

### 2. 작업 일시

- 2026-04-06 10:02:14 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py`
- `tests/defense/test_backoffice_copilot_policy_control_plane_storage.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `policy_control_plane_models.py`: Task 4 최소 DDL에 맞는 `PolicyVersionRecord`, `PolicyRolloutStateRecord`, `PolicyRolloutEventRecord`, `PolicyOptimizationRunRecord`와 serializer/parser/validator를 추가했다. ratio 범위, timestamp/window 순서, JSON mapping shape만 검증하고 rollout business logic이나 projection logic은 넣지 않았다.
- `policy_control_plane_repository.py`: `PolicyVersionRepository`, `PolicyRolloutStateRepository`, `PolicyRolloutEventRepository`, `PolicyOptimizationRunRepository` protocol과 PostgreSQL concrete repository를 추가했다. `policy_rollout_events`는 append-only insert만 허용하고, 나머지는 authoritative state upsert/read 경계만 제공한다.
- `storage/__init__.py`: Task 12 projection 구현과 후속 wiring이 바로 import할 수 있도록 control-plane DTO / parser / serializer / repository surface를 export했다.
- `test_backoffice_copilot_policy_control_plane_storage.py`: policy document persistence contract, rollout state/event 분리, optimization run write/read, invalid ratio/window rejection을 검증하는 `unittest` smoke를 추가했다.
- `task-execution-log.md`: Task 11 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `10-repository-adapter-boundary.md`, `07-policy-control-plane-minimum-ddl.md`, `loader.py`, `runtime.py`, `rollout.py`, `keyspace.py`
  - 결과: PostgreSQL control-plane authoritative repository 방향과 현재 `RedisPolicyStore + FilePolicyStore fallback` runtime authority 충돌을 숨기지 않았고, runtime direct read 경로는 추가하지 않았다.
- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_models.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py tests/defense/test_backoffice_copilot_policy_control_plane_storage.py`
  - 결과: 문법 오류 없음
- 단위 테스트
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_policy_control_plane_storage`
  - 결과: `Ran 6 tests`, `OK`
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage`
  - 결과: `Ran 16 tests`, `OK`
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_policy_control_plane_storage` 실행 전 테스트 초안
  - 결과: `d0_mvp` import chain에서 `httpx` optional dependency가 없어 import error 발생. 테스트 fixture를 runtime app import 비의존 형태로 낮춰 해결했다.
- smoke
  - 명령: `PYTHONPATH=src python3 - <<'PY' ...`
  - 결과: `policy-control-plane-smoke-ok`
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_models.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py tests/defense/test_backoffice_copilot_policy_control_plane_storage.py`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크 또는 Task 12에 넘길 입력

- 남은 리스크
  - 현재 runtime authority는 여전히 `RedisPolicyStore + FilePolicyStore fallback`이며, 이번 repository는 아직 application wiring에 연결되지 않았다.
  - `policy_rollout_state`의 single-active-row enforcement, foreign key, projection transaction sequencing은 이번 task 범위 밖이라 구현하지 않았다.
  - `d0_mvp` 패키지 import chain은 optional dependency에 민감하므로 후속 projection wiring에서는 runtime app import를 직접 끌어오지 않는 분리가 필요하다.
- Task 12에 넘길 입력
  - authoritative repository surface: `PostgresPolicyVersionRepository`, `PostgresPolicyRolloutStateRepository`, `PostgresPolicyRolloutEventRepository`, `PostgresPolicyOptimizationRunRepository`
  - persistence contracts: `PolicyVersionRecord`, `PolicyRolloutStateRecord`, `PolicyRolloutEventRecord`, `PolicyOptimizationRunRecord`
  - append-only guardrail: `policy_rollout_events`는 `append_event()`와 `list_events()`만 제공하며 update/delete surface가 없다.
  - projection input source: Redis projection worker는 `get_version(policy_version)`, `get_state(rollout_id)`, `list_events(rollout_id)`를 사용해 authoritative PostgreSQL row를 읽고 projection payload로 변환하면 된다.
  - non-conflict memo: 이번 repository 구현은 PostgreSQL authoritative control-plane만 다루며 ClickHouse reader/writer, runtime direct read, rollout assignment business logic와 겹치지 않는다.

## Task 12

### 1. task 번호와 제목

- Task 12. PostgreSQL -> Redis projection 구현

### 2. 작업 일시

- 2026-04-06 10:07:36 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py`
- `tests/defense/test_backoffice_copilot_policy_projection.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `policy_projection_models.py`: projection input contract `PolicyRuntimeProjectionInput`, Redis payload contract `RedisProjectedPolicyDocument` / `RedisProjectedRolloutState`, apply result `PolicyProjectionApplyResult`, payload serializer와 version-index derive helper를 추가했다. Redis에 복제하면 안 되는 control-plane 메타는 payload 단계에서 제외했다.
- `policy_projection_repository.py`: `RedisPolicyProjectionRepository`, concrete `RedisRuntimePolicyProjectionRepository`, `project_policy_version_activation()`, `project_rollout_state_change()`, `reconcile_policy_runtime_projection()`를 추가했다. apply ordering은 version doc -> rollout-state -> version-index 순서로 고정했고, runtime direct PostgreSQL read는 여기에 넣지 않았다.
- `storage/__init__.py`: Task 13 runtime read adapter와 후속 wiring이 바로 import할 수 있도록 projection DTO / repository / entrypoint surface를 export했다.
- `test_backoffice_copilot_policy_projection.py`: projection payload 최소화, apply ordering, version activation trigger, reconcile helper, authoritative row missing 시 fail-fast를 검증하는 `unittest` smoke를 추가했다.
- `task-execution-log.md`: Task 12 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `08-postgresql-to-redis-projection-contract.md`, `10-repository-adapter-boundary.md`, `runtime.py`, `loader.py`, `keyspace.py`, `rollout.py`, `policy_control_plane_repository.py`
  - 결과: PostgreSQL authoritative source -> Redis runtime projection 분리 원칙과 `tm:decision-policy:*` keyspace를 유지했고, runtime direct PostgreSQL read 경로는 추가하지 않았다.
- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_models.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py tests/defense/test_backoffice_copilot_policy_projection.py`
  - 결과: 문법 오류 없음
- 단위 테스트
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_policy_projection`
  - 결과: `Ran 5 tests`, `OK`
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection`
  - 결과: `Ran 21 tests`, `OK`
- smoke
  - 명령: `PYTHONPATH=src python3 - <<'PY' ...`
  - 결과: `policy-projection-smoke-ok {"versions": ["policy-v1", "policy-v2"], "index": ["policy-v1", "policy-v2"], "wrote_rollout_state": true}`
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_models.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py tests/defense/test_backoffice_copilot_policy_projection.py`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크 또는 Task 13에 넘길 입력

- 남은 리스크
  - 현재 runtime bootstrap은 여전히 `DefenseRuntime._bootstrap_policy_authority()`에서 Redis baseline을 직접 채우므로, 후속 wiring 전까지는 new projection worker가 runtime bootstrap을 대체하지 않는다.
  - `policy_rollout_state`의 current row 조회는 아직 `rollout_id`를 호출자가 알고 있다는 전제 위에 있다. single-active-row discovery나 scheduler/orchestration은 이번 범위 밖이다.
  - projection repository는 `keyspace.py`와 같은 문자열을 storage 계층에 고정했다. `d0_mvp` import chain의 optional dependency 문제를 피하기 위한 선택이지만, 후속 task에서 drift 검증이 필요하다.
- Task 13에 넘길 입력
  - projection input contract: `PolicyRuntimeProjectionInput`
  - Redis payload contract: `RedisProjectedPolicyDocument`, `RedisProjectedRolloutState`
  - runtime-facing keyspace: `POLICY_VERSION_KEY_PREFIX`, `POLICY_ROLLOUT_STATE_KEY`, `POLICY_VERSION_INDEX_KEY`
  - projection entrypoints: `project_policy_version_activation()`, `project_rollout_state_change()`, `reconcile_policy_runtime_projection()`
  - runtime read adapter guardrail: Task 13은 PostgreSQL을 읽지 말고 위 Redis key 3종만 읽는 thin adapter로 제한할 것

## Task 13

### 1. task 번호와 제목

- Task 13. runtime read adapter 정리 및 Redis projection 연결

### 2. 작업 일시

- 2026-04-06 10:12:09 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/__init__.py`
- `src/traffic_master_ai/defense/d0_mvp/__init__.py`
- `tests/defense/test_runtime_policy_read_adapter.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `runtime_read_adapter.py`: `RuntimePolicyReadAdapter`, `RuntimeProjectedPolicyDocument`, `RuntimeProjectedRolloutState`, decode/serialize helper를 추가했다. runtime read contract는 Redis projection key에서 policy doc / rollout state를 primary-only로 읽고 decode하는 thin adapter로 제한했다.
- `loader.py`: `PolicyLoader`가 direct store read 대신 `RuntimePolicyReadAdapter`를 통해 projection payload를 읽도록 바꿨다. `RedisPolicyStore.fetch_primary_policy_by_version()`를 추가했고, missing/invalid projection일 때는 warning 후 default baseline policy로만 fallback한다.
- `policy/__init__.py`: runtime read adapter surface를 export했다.
- `d0_mvp/__init__.py`: `DefenseRuntime` eager import를 lazy export로 바꿔 policy/loader 단위 import가 optional dependency에 막히지 않도록 정리했다.
- `test_runtime_policy_read_adapter.py`: projection payload decode contract, primary Redis projection read, broad fallback 금지, invalid projection 시 baseline fallback을 검증하는 `unittest`를 추가했다.
- `task-execution-log.md`: Task 13 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `10-repository-adapter-boundary.md`, `08-postgresql-to-redis-projection-contract.md`, `runtime.py`, `loader.py`, `keyspace.py`, `session_state.py`, `policy_projection_repository.py`
  - 결과: request path가 PostgreSQL repository를 직접 읽지 않고 Redis projection만 읽도록 유지하면서 기존 `PolicyLoader` 흐름을 최소 범위로 정리했다.
- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/d0_mvp/__init__.py src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/policy/__init__.py tests/defense/test_runtime_policy_read_adapter.py`
  - 결과: 문법 오류 없음
- 단위 테스트
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_runtime_policy_read_adapter`
  - 결과: `Ran 4 tests`, `OK`
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter`
  - 결과: `Ran 25 tests`, `OK`
  - 메모: invalid/missing projection fallback 경로에서 warning log 2건이 출력됐고, 의도한 명시적 fallback 동작임을 확인했다.
- smoke
  - 명령: `python3 - <<'PY' ... import traffic_master_ai.defense.d0_mvp.policy.loader ...`
  - 결과: `runtime-policy-loader-import-ok PolicyLoader`
  - 명령: `PYTHONPATH=src python3 - <<'PY' ...`
  - 결과: `runtime-policy-read-smoke-ok policy-v2`
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/d0_mvp/__init__.py src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/policy/__init__.py tests/defense/test_runtime_policy_read_adapter.py`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크 또는 Task 14에 넘길 입력

- 남은 리스크
  - `DefenseRuntime._bootstrap_policy_authority()`는 여전히 baseline Redis write를 직접 수행하므로, prod projection worker가 붙기 전까지 bootstrap path와 projection path가 공존한다.
  - missing/invalid projection fallback은 현재 baseline default policy로만 내려가며, stale projection 감지 timestamp 정책이나 reconcile 호출 orchestration은 아직 없다.
  - full runtime stack 테스트는 optional dependency가 남아 있어 이번 task에서는 loader/read adapter 단위까지만 잠갔다.
- Task 14에 넘길 입력
  - runtime read contract: `RuntimePolicyReadAdapter.fetch_projected_policy_document()` + `get_projected_rollout_state()`
  - projection payload decoding contract: `decode_runtime_projected_policy_document()`, `decode_runtime_projected_rollout_state()`
  - loader connection point: `PolicyLoader(..., read_adapter=...)`
  - explicit fallback rule: invalid/missing Redis projection -> warning log + default baseline policy, PostgreSQL direct read 금지 유지
  - env/config wiring point: runtime Redis backend 구성은 `build_runtime_redis_from_env()`, projection write orchestration env는 Task 12 entrypoint와 별도로 wiring 필요

## Task 14

### 1. task 번호와 제목

- Task 14. env / config wiring 구현

### 2. 작업 일시

- 2026-04-06 10:21:14 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/storage_env.py`
- `src/traffic_master_ai/defense/api/audit.py`
- `src/traffic_master_ai/defense/api/database.py`
- `src/traffic_master_ai/defense/api/etl_worker.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/connection.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py`
- `src/traffic_master_ai/defense/d0_mvp/api/runtime.py`
- `src/traffic_master_ai/defense/d0_mvp/observability/audit_logger.py`
- `src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
- `src/traffic_master_ai/defense/d0_mvp/state/redis_client.py`
- `tests/defense/test_storage_env_config.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `storage_env.py`: Task 6 env 계약을 코드로 고정하는 최소 config schema를 추가했다. `AuditLogConfig`, `WarehouseFileConfig`, `RuntimePolicyConfig`, `RuntimeRedisConfig`, `S3ArchiveConfig`, `PostgresStorageConfig`, `ClickHouseStorageConfig`, `ETLWorkerConfig`와 각 env loader를 정의했다.
- `api/audit.py`: `DefenseDecisionAuditLogger.from_env()`와 `S3Uploader.from_env()`를 추가해 audit log path와 S3 archive 설정을 공통 loader에서 읽도록 정리했다.
- `api/database.py`: `TM_PG_URL` 직접 조회를 제거하고 shared PostgreSQL config loader를 사용하도록 맞췄다.
- `api/etl_worker.py`: ETL worker에 `ETLWorkerConfig` 주입 지점을 추가했다. `TM_S3_BUCKET` 누락 시 명시적 no-op, `TM_PG_URL` 누락 시 PostgreSQL prototype 불가 메시지, `TM_CLICKHOUSE_URL`만 있는 경우 ClickHouse ingest wiring 전까지 explicit no-op를 출력한다. `boto3` / `sqlalchemy`는 실제 worker 생성 시점까지 lazy import로 늦췄다.
- `clickhouse_connection.py`: ClickHouse writer/read model이 `TM_CLICKHOUSE_URL`, `TM_CLICKHOUSE_AUDIT_TABLE`, ingest batch/timeout env를 공통 config loader에서 읽도록 `build_clickhouse_write_config_from_env()`와 `build_clickhouse_read_model_config_from_env()`를 추가했다.
- `connection.py`: `TM_PG_URL` required contract를 `load_postgres_storage_config_from_env(required=True)`로 통일했다.
- `storage/__init__.py`: Task 9/10 ClickHouse skeleton이 env-driven config surface를 바로 import할 수 있도록 export를 보강했다.
- `runtime.py`: `PolicyLoader`를 직접 넘기지 않는 경우에만 runtime policy env를 읽어 `RedisPolicyStore + FilePolicyStore fallback`, `AuditLogger.from_env()`, `AuditWarehouse.from_env()`를 구성하도록 바꿨다.
- `audit_logger.py` / `warehouse.py`: local JSONL observability surface에 각각 `from_env()`를 추가했다. `TM_WAREHOUSE_FILENAME`은 current-code-only JSONL MVP path로 유지했다.
- `loader.py`: `PolicyLoader.from_env()`를 추가해 `TM_POLICY_STORE_PATH`, `TM_POLICY_CACHE_SECONDS`, `TM_ROLLOUT_SALT`를 shared config loader에서 읽도록 정리했다.
- `redis_client.py`: `TM_REDIS_URL` / `CI` 기준 runtime Redis backend 선택을 `load_runtime_redis_config_from_env()`로 통일했다. non-CI에서 `TM_REDIS_URL` 누락 시 fail-fast를 유지한다.
- `test_storage_env_config.py`: env default, required PostgreSQL fail-fast, ClickHouse config surface, runtime loader/audit/warehouse env path, ETL explicit no-op를 검증하는 최소 `unittest`를 추가했다.
- `task-execution-log.md`: Task 14 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `09-env-failure-handling-test-plan.md`, `etl_worker.py`, `runtime.py`, `loader.py`, `warehouse.py`
  - 결과: Task 6 env matrix와 현재 wiring을 대조했고, ClickHouse / PostgreSQL / Redis / S3 설정 책임을 분리했다. runtime direct PostgreSQL read는 추가하지 않았다.
- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/storage_env.py src/traffic_master_ai/defense/api/etl_worker.py src/traffic_master_ai/defense/api/audit.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/connection.py src/traffic_master_ai/defense/d0_mvp/state/redis_client.py src/traffic_master_ai/defense/d0_mvp/observability/audit_logger.py src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/api/runtime.py tests/defense/test_storage_env_config.py`
  - 결과: 문법 오류 없음
- 단위 테스트
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_storage_env_config`
  - 결과: `Ran 5 tests`, `OK`
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter tests.defense.test_storage_env_config`
  - 결과: `Ran 30 tests`, `OK`
  - 메모: runtime projection fallback warning 2건은 기존 Task 13의 explicit fallback 동작으로 의도된 출력이다.
- smoke
  - 명령: `PYTHONPATH=src python3 - <<'PY' ... run_etl() ... PolicyLoader.from_env() ... PY`
  - 결과: `etl-config-smoke-ok True`, `runtime-config-smoke-ok 11 task14-salt`
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/storage_env.py src/traffic_master_ai/defense/api/etl_worker.py src/traffic_master_ai/defense/api/audit.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py src/traffic_master_ai/defense/d0_mvp/state/redis_client.py src/traffic_master_ai/defense/d0_mvp/observability/audit_logger.py src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/api/runtime.py tests/defense/test_storage_env_config.py`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크 또는 Task 15에 넘길 입력

- 남은 리스크
  - `api/database.py`는 여전히 `sqlalchemy` import를 module import 시점에 요구한다. Task 14 범위에서는 env wiring만 연결했고, dependency failure handling 세분화는 Task 15로 넘긴다.
  - `TM_WAREHOUSE_FILENAME`은 Task 6 cross-store env matrix 밖의 current-code-only JSONL MVP path다. ClickHouse observability wiring이 끝나면 제거 또는 축소 여부를 다시 결정해야 한다.
  - `TM_ROLLOUT_SALT`는 여전히 빈 문자열 default를 허용한다. local/MVP 호환을 위한 선택이며, non-dev hard requirement enforcement는 failure handling task에서 명확히 다뤄야 한다.
- Task 15에 넘길 입력
  - config schema: `storage_env.py`의 8개 config dataclass와 env loader
  - 계층별 env 누락 동작
    - Redis runtime: non-CI에서 `TM_REDIS_URL` 누락 시 fail-fast
    - ETL worker: `TM_S3_BUCKET` 누락 시 no-op, `TM_PG_URL` 누락 시 explicit prototype no-op/fail-fast, `TM_CLICKHOUSE_URL` only 상태는 explicit no-op
    - PostgreSQL repository helpers: `TM_PG_URL` required surface는 fail-fast
    - ClickHouse skeleton: URL/table/batch/timeout만 주입되고 실제 network wiring은 후속 task
  - failure seam
    - lazy import된 `boto3` / `sqlalchemy` dependency failure를 user-facing error/log로 정리할 지점
    - runtime bootstrap과 projection fallback warning을 운영 신호로 승격할 지점

## Task 15

### 1. task 번호와 제목

- Task 15. failure handling 최소 구현

### 2. 작업 일시

- 2026-04-06 10:28:56 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/__init__.py`
- `tests/defense/test_backoffice_copilot_clickhouse_storage.py`
- `tests/defense/test_backoffice_copilot_policy_control_plane_storage.py`
- `tests/defense/test_backoffice_copilot_policy_projection.py`
- `tests/defense/test_runtime_policy_read_adapter.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `clickhouse_repository.py`: `ClickHouseBatchWriteError`, `ClickHouseBatchWriteRetryPolicy`, `write_batch_request_with_retry()`를 추가했다. ClickHouse raw fact batch write 실패 시 테이블명, row 수, replay hint가 담긴 typed 예외를 올리고, 최소 retry entrypoint를 노출했다.
- `policy_control_plane_repository.py`: `PostgresControlPlaneWriteError`를 추가했다. `policy_versions`, `policy_rollout_state`, `policy_rollout_events`, `policy_optimization_runs` write/append 실패를 authoritative PostgreSQL failure로 명시적으로 surfacing하고, Redis projection/rollout continuation 금지 recovery hint를 남긴다.
- `policy_projection_repository.py`: `RedisProjectionApplyError`, `ProjectionRetryPolicy`, `apply_policy_runtime_projection_with_retry()`를 추가했다. Redis `set()`이 `False`를 반환해도 실패로 간주하고, projection retry budget을 모두 소진하면 `reconcile_policy_runtime_projection(...)` resync hint가 포함된 typed 예외를 올린다.
- `runtime_read_adapter.py`: `RuntimeProjectionDecodeError`, `RuntimeProjectionStaleError`, `ensure_runtime_rollout_state_is_fresh()`, `get_projected_rollout_state_with_staleness_check()`를 추가했다. invalid payload뿐 아니라 explicit staleness guard 실패도 baseline fallback과 projection repair signal로 표면화한다.
- `loader.py`: runtime request path의 broad fallback은 늘리지 않고, missing/invalid projection과 stale rollout-state fallback log에 “projection repair 필요”를 명시했다. optional `projection_max_staleness_ms` 주입 지점도 추가했다.
- `policy/__init__.py` / `storage/__init__.py`: Task 16 test 강화와 후속 wiring이 새 typed 예외 / retry policy / staleness helper를 바로 import할 수 있도록 export surface를 보강했다.
- `test_backoffice_copilot_clickhouse_storage.py`: transient ClickHouse failure retry, retry budget 소진 시 typed error + replay hint를 검증했다.
- `test_backoffice_copilot_policy_control_plane_storage.py`: authoritative PostgreSQL write failure가 각 테이블별 `PostgresControlPlaneWriteError`로 surfacing되는지 검증했다.
- `test_backoffice_copilot_policy_projection.py`: Redis projection retry success, retry exhaustion 시 typed error + `reconcile_policy_runtime_projection` hint를 검증했다.
- `test_runtime_policy_read_adapter.py`: rollout-state staleness guard와 stale projection baseline fallback을 검증했다.
- `task-execution-log.md`: Task 15 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, `09-env-failure-handling-test-plan.md`, `etl_worker.py`, `runtime.py`, `loader.py`, `warehouse.py`
  - 결과: Task 6 failure 원칙과 대조했고, runtime direct PostgreSQL read 우회 경로 없이 ClickHouse write / PostgreSQL authoritative write / PostgreSQL->Redis projection / runtime projection read 경계별로 실패 surfacing을 분리했다.
- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/policy/__init__.py tests/defense/test_backoffice_copilot_clickhouse_storage.py tests/defense/test_backoffice_copilot_policy_control_plane_storage.py tests/defense/test_backoffice_copilot_policy_projection.py tests/defense/test_runtime_policy_read_adapter.py`
  - 결과: 문법 오류 없음
- 단위 테스트
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter`
  - 결과: `Ran 27 tests`, `OK`
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter tests.defense.test_storage_env_config`
  - 결과: `Ran 37 tests`, `OK`
  - 메모: failure-path 검증용 `logger.exception` 출력이 남았고, typed 예외 surfacing이 실제로 발생함을 확인했다.
- smoke
  - 명령: `PYTHONPATH=src python3 - <<'PY' ... ClickHouseBatchWriteError ... RedisProjectionApplyError ... PY`
  - 결과: `clickhouse-failure-smoke-ok 2 True`, `projection-failure-smoke-ok 2 True`
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/policy/__init__.py tests/defense/test_backoffice_copilot_clickhouse_storage.py tests/defense/test_backoffice_copilot_policy_control_plane_storage.py tests/defense/test_backoffice_copilot_policy_projection.py tests/defense/test_runtime_policy_read_adapter.py`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크 또는 Task 16에 넘길 입력

- 남은 리스크
  - retry는 minimal synchronous entrypoint만 있고, scheduler / async replay worker / dead-letter queue는 없다.
  - runtime stale projection guard는 optional injection point만 추가했고, production staleness threshold는 아직 env 또는 운영 정책으로 잠기지 않았다.
  - `etl_worker.py` current PostgreSQL prototype과 `warehouse.py` JSONL MVP는 이번 task 범위 밖이라 ClickHouse ingest replay orchestration까지는 연결하지 않았다.
- Task 16에 넘길 입력
  - ClickHouse failure contract: `ClickHouseBatchWriteError`, `ClickHouseBatchWriteRetryPolicy`, `write_batch_request_with_retry()`
  - PostgreSQL authoritative write failure contract: `PostgresControlPlaneWriteError`
  - Redis projection retry/resync contract: `ProjectionRetryPolicy`, `RedisProjectionApplyError`, `apply_policy_runtime_projection_with_retry()`, `reconcile_policy_runtime_projection()`
  - runtime projection read failure contract: `RuntimeProjectionDecodeError`, `RuntimeProjectionStaleError`, `ensure_runtime_rollout_state_is_fresh()`, `PolicyLoader(..., projection_max_staleness_ms=...)`
  - test 강화 포인트
    - logger/message contract assertion
    - retry attempt count/backoff branch assertion
    - projection partial-apply recovery integration test
    - stale threshold policy가 runtime wiring에 연결될 경우의 env/contract test

## Task 16

### 1. task 번호와 제목

- Task 16. unit / contract test 강화

### 2. 작업 일시

- 2026-04-06 10:31:39 KST

### 3. 실제로 수정한 파일 목록

- `tests/defense/test_backoffice_copilot_clickhouse_read_models.py`
- `tests/defense/test_backoffice_copilot_policy_control_plane_storage.py`
- `tests/defense/test_backoffice_copilot_policy_projection.py`
- `tests/defense/test_runtime_policy_read_adapter.py`
- `tests/defense/test_storage_env_config.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `test_backoffice_copilot_clickhouse_read_models.py`: session rollup / candidate reader의 SQL contract를 더 잠갔다. window filter 외에 optional `session_id IN :session_ids`, `LIMIT :limit`, custom table/view name 반영 여부를 검증한다.
- `test_backoffice_copilot_policy_control_plane_storage.py`: `PkConflictPolicy.FAIL_FAST`가 plain `INSERT`를 유지하는지 추가로 검증했다. authoritative repository가 몰래 upsert로 바뀌지 않게 잠갔다.
- `test_backoffice_copilot_policy_projection.py`: Redis projection payload minimum-field contract를 더 잠갔다. rollout payload가 runtime 최소 필드만 가지는지, version index가 dedupe + sorted shape를 유지하는지 검증한다.
- `test_runtime_policy_read_adapter.py`: invalid projection payload가 `RuntimeProjectionDecodeError`를 내는지, raw Redis payload parser가 JSON string/bytes를 안정적으로 받는지 검증했다.
- `test_storage_env_config.py`: non-CI `TM_REDIS_URL` fail-fast, CI memory fallback, invalid ClickHouse numeric env rejection을 추가로 검증했다.
- `task-execution-log.md`: Task 16 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, Task 9~15 산출물
  - 결과: 이번 task는 production code 변경 없이 기존 repository / adapter / projection / runtime read / config / failure handling 경계를 test로 더 촘촘히 잠그는 방향으로 유지했다.
- 문법 확인
  - 명령: `python3 -m py_compile tests/defense/test_backoffice_copilot_clickhouse_read_models.py tests/defense/test_backoffice_copilot_policy_control_plane_storage.py tests/defense/test_backoffice_copilot_policy_projection.py tests/defense/test_runtime_policy_read_adapter.py tests/defense/test_storage_env_config.py`
  - 결과: 문법 오류 없음
- 단위 테스트
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter tests.defense.test_storage_env_config`
  - 결과: `Ran 37 tests`, `OK`
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter tests.defense.test_storage_env_config`
  - 결과: `Ran 44 tests`, `OK`
  - 메모: failure-path tests 때문에 `logger.exception` 출력이 남았지만, expected failure surfacing 경로임을 확인했다.
- runner availability
  - 현재 환경에서는 `unittest` runner가 사용 가능하다.
  - 최소 실행 경로는 `PYTHONPATH=src python3 -m unittest ...` 이다.
- 포맷 확인
  - 명령: `git diff --check -- tests/defense/test_backoffice_copilot_clickhouse_read_models.py tests/defense/test_backoffice_copilot_policy_control_plane_storage.py tests/defense/test_backoffice_copilot_policy_projection.py tests/defense/test_runtime_policy_read_adapter.py tests/defense/test_storage_env_config.py`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크 또는 Task 17에 넘길 입력

- 남은 리스크
  - 아직 full integration test는 없다. PostgreSQL 실제 engine, Redis package, ClickHouse driver를 연결한 end-to-end contract는 잠기지 않았다.
  - failure-path logger message는 현재 출력 존재만 확인했고, structured log schema 자체를 assertion 하지는 않았다.
  - projection partial-apply 후 실제 reconcile recovery를 cross-layer로 검증하는 test는 아직 없다.
- Task 17에 넘길 입력
  - runner: `PYTHONPATH=src python3 -m unittest ...`
  - 강화된 unit/contract coverage
    - ClickHouse reader SQL surface: `test_backoffice_copilot_clickhouse_read_models.py`
    - PostgreSQL conflict policy contract: `test_backoffice_copilot_policy_control_plane_storage.py`
    - Redis projection payload serialization contract: `test_backoffice_copilot_policy_projection.py`
    - runtime decode/parser/staleness contract: `test_runtime_policy_read_adapter.py`
    - env fail-fast / CI fallback contract: `test_storage_env_config.py`
  - integration/smoke 우선 순위
    - real Redis package present/absent 경로
    - SQLAlchemy engine가 있는 실제 PostgreSQL repository smoke
    - projection apply -> runtime read -> reconcile recovery 순서 smoke

## Task 17

### 1. task 번호와 제목

- Task 17. integration / smoke test 추가

### 2. 작업 일시

- 2026-04-06 10:34:14 KST

### 3. 실제로 수정한 파일 목록

- `tests/defense/test_backoffice_copilot_db_smoke.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `test_backoffice_copilot_db_smoke.py`: DB-build 경계가 실제로 함께 붙는 최소 smoke 흐름 5개를 추가했다.
  - ingest / raw fact write smoke: env-driven ClickHouse writer config + raw fact writer + fake batch client
  - PostgreSQL control-plane -> Redis projection -> runtime loader smoke: fake authoritative repositories + `RedisRuntimePolicyProjectionRepository` + `RedisPolicyStore` + `PolicyLoader`
  - projection reconcile smoke: Redis key eviction 후 `reconcile_policy_runtime_projection()`으로 runtime read 복구
  - session rollup / candidate reader smoke: fake select client + 두 reader repository + `load_backoffice_clickhouse_read_model_input()`
  - bootstrap / config smoke: `build_runtime_redis_from_env()` CI memory fallback + `PolicyLoader.from_env()` wiring
- `task-execution-log.md`: Task 17 작업 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, Task 9~16 산출물
  - 결과: smoke 시나리오는 ingest/raw fact, control-plane/projection, runtime read, read model, config/bootstrap 연결만 검증하고, business logic 재정의나 full E2E 범위 확장은 피했다.
- 문법 확인
  - 명령: `python3 -m py_compile tests/defense/test_backoffice_copilot_db_smoke.py`
  - 결과: 문법 오류 없음
- smoke 테스트
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_db_smoke`
  - 결과: `Ran 5 tests`, `OK`
  - 메모: runtime baseline fallback warning 1건은 reconcile 전 baseline fallback 경로를 의도적으로 통과한 출력이다.
- 관련 suite 재실행
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter tests.defense.test_storage_env_config tests.defense.test_backoffice_copilot_db_smoke`
  - 결과: `Ran 49 tests`, `OK`
- runner availability
  - 현재 환경에서는 `unittest` runner 사용 가능
  - smoke 포함 DB-build suite count: `49`
  - 최소 실행 경로: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_db_smoke`
- 포맷 확인
  - 명령: `git diff --check -- tests/defense/test_backoffice_copilot_db_smoke.py`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크 또는 Task 18에 넘길 입력

- 남은 리스크
  - ClickHouse / PostgreSQL / Redis 실제 패키지와 연결한 true integration test는 아직 없다. 이번 smoke는 protocol-compatible fake와 `InMemoryRedis`를 쓴다.
  - `etl_worker.py` current PostgreSQL prototype -> real ClickHouse ingest wiring은 아직 없다. raw fact ingest smoke는 writer surface까지만 검증한다.
  - runtime bootstrap, projection repair, authoritative write를 하나의 실제 infra stack에서 묶는 end-to-end smoke는 아직 없다.
- Task 18에 넘길 입력
  - smoke coverage file: `tests/defense/test_backoffice_copilot_db_smoke.py`
  - fake/stub 사용 지점
    - ClickHouse batch client: `_FakeClickHouseBatchClient`
    - ClickHouse select client: `_FakeClickHouseSelectClient`
    - PostgreSQL authoritative repositories: `_FakePolicyVersionRepository`, `_FakePolicyRolloutStateRepository`
    - Redis backend: `InMemoryRedis`
  - 최종 drift 검토 포인트
    - Task 8 SQL DDL과 Task 9~17 code/test surface 이름 drift 여부
    - `TM_WAREHOUSE_FILENAME` JSONL MVP path 유지 여부
    - current PostgreSQL ETL prototype와 target ClickHouse architecture gap 재명시 여부

## Task 18

### 1. task 번호와 제목

- Task 18. 최종 drift 검토 / 마감 정리

### 2. 작업 일시

- 2026-04-06 10:36:51 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/01-doc-map.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. 파일별 수정 요약

- `11-final-drift-review-and-handoff.md`: Task 8~17 구현 상태를 축별로 정리하는 최종 문서를 추가했다. 완료된 구현 범위, 아직 미구현인 범위, 문서-코드 drift, 후속 backlog, handoff 주의사항을 한 곳에 모았다.
- `01-doc-map.md`: 최종 drift / handoff 문서를 최상위 컨텍스트 파일 섹션에 추가해 다음 phase가 바로 찾을 수 있게 했다.
- `task-execution-log.md`: Task 18 마감 기록을 append했다.

### 5. 검증에 사용한 명령과 결과 요약

- 문서/코드 수동 대조
  - 기준: `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `task-execution-log.md`, Task 8~17 산출물, `storage/sql/*.sql`, `etl_worker.py`, `warehouse.py`, `policy_control_plane_repository.py`, `policy_projection_repository.py`, `runtime_read_adapter.py`
  - 결과: 현재 구현은 최소 경계와 테스트는 확보했지만, ClickHouse actual warehouse/MV/ingest와 JSONL/PG prototype 과도기 요소는 여전히 남아 있음을 최종 문서에 명시했다.
- 테스트 실행 결과 재확인
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_db_smoke tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter tests.defense.test_storage_env_config`
  - 결과: `Ran 49 tests`, `OK`
  - 메모: failure-path / baseline fallback 검증 때문에 warning/log output은 남지만, 현재 문서 설명과 일치하는 expected behavior다.
- 문서 파일 존재 / 정합성 확인
  - 명령: `python3 - <<'PY' ... Path.exists() ... PY`
  - 결과: `11-final-drift-review-and-handoff.md`, `01-doc-map.md` 존재 확인
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/01-doc-map.md`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 최종 남은 리스크 또는 다음 phase 입력

- 최종 남은 리스크
  - 목표 아키텍처 대비 가장 큰 drift는 `etl_worker.py` PostgreSQL prototype, `AuditWarehouse` JSONL MVP, ClickHouse session/match rollup 및 candidate view의 actual SQL/MV 부재다.
  - runtime authority는 Redis projection read로 정리됐지만, bootstrap baseline direct write와 projection-first orchestration이 완전히 통합되지는 않았다.
  - true infra-backed integration은 아직 없고 현재 smoke는 fake/stub + `InMemoryRedis` 중심이다.
- 다음 phase 입력
  - 최종 상태 문서: `11-final-drift-review-and-handoff.md`
  - 실행 기록/연혁: `task-execution-log.md`
  - 목표 구조 문서: `32-storage-architecture.md`
  - 과도기 해설 문서: `33-docs-vs-current-code-gap-analysis.md`
  - 우선 backlog
    - ClickHouse actual ingest wiring
    - session/match rollup 및 candidate view SQL/MV
    - PostgreSQL control-plane -> Redis projection workflow orchestration
    - real infra-backed integration/smoke test

## Task A

### 1. task 이름과 작업 일시

- ClickHouse 실적재 경로 완성
- 2026-04-06 11:34:31 KST

### 2. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/api/etl_worker.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_ingest.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py`
- `src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `tests/defense/test_backoffice_copilot_clickhouse_storage.py`
- `tests/defense/test_backoffice_copilot_db_smoke.py`
- `tests/defense/test_storage_env_config.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 3. 파일별 수정 요약

- `etl_worker.py`: S3 archive `.jsonl` -> canonical audit parse -> ClickHouse raw fact batch insert 주경로로 교체했다. PostgreSQL prototype engine/table insert를 제거했고, `TM_CLICKHOUSE_URL` 누락 시 CLI가 fail-fast 하도록 바꿨다. per-run/per-object local dedupe와 batch flush/retry를 넣었다.
- `clickhouse_connection.py`: `HttpClickHouseBatchWriteClient`와 `build_clickhouse_batch_write_client()`를 추가했다. `clickhouse://`/`http://`/`https://` URL을 받아 `FORMAT JSONEachRow` HTTP insert를 실행하는 최소 실사용 client다.
- `clickhouse_ingest.py`: canonical audit payload를 Task 2/8 raw-fact DTO로 고정 매핑하는 helper와 stable dedup key helper를 추가했다. `defense_tier -> risk_tier` 정규화와 `raw_payload_json` serialization을 여기서 수행한다.
- `storage/__init__.py`: 새 ClickHouse ingest/client helper export를 추가했다.
- `warehouse.py`: JSONL warehouse가 더 이상 production ingest authority가 아니라는 점을 코드 메타데이터와 docstring에 명시했다.
- `11-final-drift-review-and-handoff.md`: 기존 “ClickHouse actual ingest 없음 / etl_worker PostgreSQL prototype” 서술을 현재 코드 상태에 맞게 최소 보정했다.
- `test_backoffice_copilot_clickhouse_storage.py`: canonical audit -> insert row mapping, dedup key stability, loopback HTTP client insert contract를 추가 검증했다.
- `test_backoffice_copilot_db_smoke.py`: fake S3 + real ETL path + real writer surface를 거쳐 archive source가 ClickHouse raw fact row로 들어가는 smoke를 추가했다.
- `test_storage_env_config.py`: ETL CLI contract를 새 production path에 맞게 갱신했다. `TM_CLICKHOUSE_URL` 누락 fail-fast와 ClickHouse worker entrypoint 실행을 검증한다.
- `task-execution-log.md`: Task A 작업 기록을 append했다.

### 4. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `task-execution-log.md`, `11-final-drift-review-and-handoff.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `04-canonical-audit-minimum-contract.md`, `003_clickhouse_defense_audit_events.sql`, `audit.py`, `etl_worker.py`, `clickhouse_connection.py`, `clickhouse_repository.py`
  - 결과: 현재 blocker였던 PostgreSQL prototype/no-op 경로와 canonical audit mapping gap을 분리했고, raw fact 최소 DDL과 동일한 typed column만 실제 ingest path에 반영했다.
- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/api/etl_worker.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_ingest.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py tests/defense/test_backoffice_copilot_clickhouse_storage.py tests/defense/test_backoffice_copilot_db_smoke.py tests/defense/test_storage_env_config.py`
  - 결과: 문법 오류 없음
- targeted test 실행
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_db_smoke tests.defense.test_storage_env_config`
  - 결과: `Ran 25 tests`, `OK`
- 관련 suite 재실행
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter tests.defense.test_storage_env_config tests.defense.test_backoffice_copilot_db_smoke`
  - 결과: `Ran 55 tests`, `OK`
- 최소 샘플 ingest smoke
  - 명령: `PYTHONPATH=src python3 - <<'PY' ... ETLWorker(...).run_once() ... PY`
  - 결과: `clickhouse-etl-smoke-ok 1 T2`
  - 메모: fake S3 body 한 줄이 실제 canonical mapping을 거쳐 `risk_tier=T2` raw fact row로 들어가는 것을 확인했다.
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/api/etl_worker.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_ingest.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py tests/defense/test_backoffice_copilot_clickhouse_storage.py tests/defense/test_backoffice_copilot_db_smoke.py tests/defense/test_storage_env_config.py`
  - 결과: whitespace / conflict marker 문제 없음

### 5. 남은 리스크

- ClickHouse auth/pool/async insert, processed-key ledger, background replay/scheduler는 아직 없다. 현재 duplicate/idempotency는 한 번의 ETL run / 한 S3 object 안에서 stable dedup key로만 막는다.
- `AuditWarehouse` JSONL local adapter는 production ingest authority에서 밀려났지만 코드 자체는 아직 남아 있다. 완전 제거는 read model 정리와 함께 후속 작업이 필요하다.
- real ClickHouse server를 붙인 infra-backed integration은 아직 없다. loopback HTTP contract test와 fake S3 smoke로 최소 실행 경로만 잠갔다.

### 6. Task B로 넘길 입력

- actual raw fact ingest surface
  - `src/traffic_master_ai/defense/api/etl_worker.py`
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_ingest.py`
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py`
- raw fact SQL contract
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql`
- canonical audit source
  - `src/traffic_master_ai/defense/api/audit.py`
  - mapping 기준: `ts_ms`, `session_id`, `event_type` required, `trace_id`, `challenge_id`, `flow_state`, `risk_tier<-defense_tier`, `action`, `reason_code`, `policy_version` optional, full object는 `raw_payload_json`
- duplicate/idempotency 기준
  - `compute_clickhouse_raw_fact_dedup_key()`는 object-local/per-run dedupe만 보장한다.
  - Task B는 이를 전제로 rollup/read model layer가 raw fact duplicate tolerance 또는 stronger processed-key policy 중 하나를 선택해야 한다.

## Task B

### 1. task 이름과 작업 일시

- ClickHouse read model 완성
- 2026-04-06 12:09:49 KST

### 2. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/sql/004_clickhouse_read_models.sql`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `tests/defense/test_backoffice_copilot_clickhouse_read_models.py`
- `tests/defense/test_backoffice_copilot_db_smoke.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 3. 파일별 수정 요약

- `003_clickhouse_defense_audit_events.sql`: 상단 note를 현재 상태에 맞게 고쳤다. raw fact ingest가 더 이상 PostgreSQL prototype이 아니라는 점과 read model SQL이 별도 파일에 있다는 점을 반영했다.
- `004_clickhouse_read_models.sql`: `defense_session_rollups`, `defense_match_rollups`, `defense_post_review_candidates_v1` 세 ClickHouse VIEW object를 추가했다. session rollup은 Backoffice 1차 입력, match rollup은 운영 요약, candidate view는 selection layer로 분리했다.
- `clickhouse_connection.py`: `DEFAULT_CLICKHOUSE_MATCH_ROLLUP_TABLE`, `HttpClickHouseSelectClient`, `build_clickhouse_select_client()`와 placeholder renderer를 추가했다. reader가 실제 ClickHouse HTTP query를 실행할 수 있게 했다.
- `clickhouse_read_models.py`: match rollup query/row DTO, serializer, parser를 추가했고 session/candidate 계약과 함께 실제 SQL object 컬럼 구성을 잠갔다.
- `clickhouse_read_repository.py`: match rollup reader를 추가하고, session/candidate reader가 실제 object 이름과 query contract를 그대로 읽도록 정렬했다.
- `storage/__init__.py`: 새 match rollup / select client surface export를 추가했다.
- `11-final-drift-review-and-handoff.md`: 이제 read-model actual object가 존재한다는 점을 기준으로 ClickHouse read-model 축과 남은 gap을 최소 보정했다.
- `test_backoffice_copilot_clickhouse_read_models.py`: match rollup parser/repository, HTTP select client query rendering, actual object name contract를 검증하는 테스트를 추가했다.
- `test_backoffice_copilot_db_smoke.py`: smoke 흐름에 match rollup reader를 포함해 session/match/candidate read model bundle이 함께 깨지지 않는지 확인했다.
- `task-execution-log.md`: Task B 작업 기록을 append했다.

### 4. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `task-execution-log.md`, `11-final-drift-review-and-handoff.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `04-canonical-audit-minimum-contract.md`, `06-rollup-candidate-minimum-contract.md`, `003_clickhouse_defense_audit_events.sql`, `clickhouse_ingest.py`, `etl_worker.py`, `clickhouse_read_repository.py`, `clickhouse_read_models.py`, `clickhouse_connection.py`
  - 결과: raw fact에서 안정적으로 파생 가능한 필드만 session/match/candidate object에 넣었고, `match_id` weak gap은 match rollup에서 conservative derivation + nullable/filtered axis로만 유지했다.
- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py tests/defense/test_backoffice_copilot_clickhouse_read_models.py tests/defense/test_backoffice_copilot_db_smoke.py`
  - 결과: 문법 오류 없음
- read-model test
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_db_smoke`
  - 결과: `Ran 13 tests`, `OK`
- 관련 suite 재실행
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter tests.defense.test_storage_env_config tests.defense.test_backoffice_copilot_db_smoke`
  - 결과: `Ran 56 tests`, `OK`
- 최소 HTTP select smoke
  - 명령: `PYTHONPATH=src python3 - <<'PY' ... HttpClickHouseSelectClient ... ClickHouseSessionRollupReaderRepository ... PY`
  - 결과: `clickhouse-read-model-smoke-ok sess-1 True True`
  - 메모: 실제 HTTP select client가 `defense_session_rollups` object 이름과 rendered query를 포함해 `FORMAT JSON` 조회를 수행하는 것을 loopback server로 확인했다.
- SQL object 존재 확인
  - 명령: `rg -n "CREATE VIEW IF NOT EXISTS defense_session_rollups|CREATE VIEW IF NOT EXISTS defense_match_rollups|CREATE VIEW IF NOT EXISTS defense_post_review_candidates_v1" src/traffic_master_ai/defense/backoffice_copilot/storage/sql/004_clickhouse_read_models.sql`
  - 결과: 세 read-model object definition 존재 확인
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/backoffice_copilot/storage/sql/003_clickhouse_defense_audit_events.sql src/traffic_master_ai/defense/backoffice_copilot/storage/sql/004_clickhouse_read_models.sql src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py tests/defense/test_backoffice_copilot_clickhouse_read_models.py tests/defense/test_backoffice_copilot_db_smoke.py`
  - 결과: whitespace / conflict marker 문제 없음

### 5. 남은 리스크

- read model은 현재 최소 VIEW object다. MV/backfill/scheduler가 없으므로 고부하 운영 환경에서는 query cost와 recompute 정책을 따로 정해야 한다.
- `defense_match_rollups`는 request path 또는 `sid:matchId` 패턴에서만 보수적으로 `match_id`를 추출한다. top-level typed `match_id`가 없기 때문에 match-centric authority는 아직 약하다.
- LangGraph Backoffice workflow 본체는 여전히 raw `AnalysisInput` 기반이다. `load_backoffice_clickhouse_read_model_input()` surface는 존재하지만 workflow-level full adoption은 후속 정리가 필요하다.

### 6. Task C로 넘길 입력

- actual read model SQL/object
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/sql/004_clickhouse_read_models.sql`
  - session rollup: Backoffice 1차 입력
  - match rollup: ops summary only
  - candidate view: selection layer only
- reader/runtime query surface
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py`
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py`
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_repository.py`
- strict authority 설계 시 고려할 current gap
  - `match_id`는 아직 top-level raw fact typed column이 아니다.
  - cross-run duplicate tolerance는 read model이 아니라 ingest/authority layer에서 더 강하게 잠가야 한다.
  - Backoffice workflow full adoption은 read model bundle과 기존 raw fallback contract를 어떻게 병행할지 결정이 필요하다.

## Task C

### 1. task 이름과 작업 일시

- PostgreSQL control-plane + strict authority 완성
- 2026-04-06 12:23:50 KST

### 2. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/storage_env.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/__init__.py`
- `src/traffic_master_ai/defense/d0_mvp/api/runtime.py`
- `src/traffic_master_ai/defense/d0_mvp/api/check.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `tests/defense/test_storage_env_config.py`
- `tests/defense/test_runtime_policy_read_adapter.py`
- `tests/defense/test_backoffice_copilot_policy_projection.py`
- `tests/defense/test_backoffice_copilot_db_smoke.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 3. 파일별 수정 요약

- `storage_env.py`: runtime policy config에 `TM_POLICY_ALLOW_LOCAL_FALLBACK`, `TM_POLICY_PROJECTION_MAX_STALENESS_MS`, `TM_ALLOW_IN_MEMORY_REDIS`를 반영했다. prod 기본값은 strict authority, local/dev/test는 explicit fallback만 허용하도록 정리했다.
- `runtime_read_adapter.py`: missing projection을 위한 `RuntimeProjectionNotFoundError`, strict read용 `require_projected_policy_document()`, `require_projected_rollout_state()`를 추가했다. lenient read path와 strict read path를 분리했다.
- `loader.py`: `RuntimePolicyAuthorityError`와 strict authority mode를 추가했다. strict mode에서는 Redis projection missing/invalid/stale를 baseline default policy로 숨기지 않고 typed error로 surfaced 한다.
- `policy/__init__.py`: strict authority 관련 typed error export를 추가했다.
- `runtime.py`: no-arg runtime이 prod에서 `build_runtime_redis_from_env()`를 사용하도록 바꿨다. `InMemoryRedis` implicit default와 file fallback/bootstrap은 local mode 또는 explicit in-memory test path에서만 허용한다. strict authority failure는 `RuntimeAPIError` 503으로 surfaced 되게 정리했다.
- `check.py`: `check_request_to_evaluate()`에서 올라오는 strict authority `RuntimeAPIError`를 adapter response로 전달하도록 보정했다.
- `policy_projection_repository.py`: `PostgresStrictPolicyAuthorityService`를 추가했다. `policy_versions`, `policy_rollout_state`, `policy_rollout_events`, `policy_optimization_runs` authoritative repository와 Redis projection repository를 하나의 thin service로 묶고, save -> sync/resync 경로를 제공한다.
- `storage/__init__.py`: `PostgresStrictPolicyAuthorityService` export를 추가했다.
- `11-final-drift-review-and-handoff.md`: control-plane / projection / runtime authority 축이 strict mode까지 반영된 상태로 갱신했다.
- `test_storage_env_config.py`: strict runtime policy default, explicit local fallback, explicit in-memory Redis opt-in 계약을 검증하도록 보강했다.
- `test_runtime_policy_read_adapter.py`: strict loader missing/stale projection 시 typed authority error가 올라오는지 검증했다.
- `test_backoffice_copilot_policy_projection.py`: strict authority service의 save+sync, resync 동작을 fake repository와 Redis projection repository 기준으로 검증했다.
- `test_backoffice_copilot_db_smoke.py`: PostgreSQL authoritative write -> Redis projection -> strict runtime read-only 경로 smoke를 추가했다.
- `task-execution-log.md`: Task C 작업 기록을 append했다.

### 4. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `task-execution-log.md`, `11-final-drift-review-and-handoff.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `002_postgresql_policy_control_plane_tables.sql`, `policy_control_plane_repository.py`, `policy_projection_repository.py`, `loader.py`, `runtime_read_adapter.py`, `runtime.py`, `keyspace.py`
  - 결과: `PostgreSQL = authoritative source`, `Redis = runtime projection`, `runtime = Redis read only` 원칙과 prod fallback 차단 지점을 코드에 대응시켰다.
- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/storage_env.py src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/policy/__init__.py src/traffic_master_ai/defense/d0_mvp/api/runtime.py src/traffic_master_ai/defense/d0_mvp/api/check.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py tests/defense/test_storage_env_config.py tests/defense/test_runtime_policy_read_adapter.py tests/defense/test_backoffice_copilot_policy_projection.py tests/defense/test_backoffice_copilot_db_smoke.py`
  - 결과: 문법 오류 없음
- targeted test 실행
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_storage_env_config tests.defense.test_runtime_policy_read_adapter tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_backoffice_copilot_db_smoke`
  - 결과: `Ran 37 tests`, `OK`
- 관련 suite 재실행
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter tests.defense.test_storage_env_config tests.defense.test_backoffice_copilot_db_smoke`
  - 결과: `Ran 63 tests`, `OK`
- 최소 strict authority smoke
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_backoffice_copilot_db_smoke`
  - 결과: `PostgresStrictPolicyAuthorityService` 기준으로 authoritative write -> Redis projection -> strict runtime read-only smoke가 통과했다.
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/storage_env.py src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/policy/__init__.py src/traffic_master_ai/defense/d0_mvp/api/runtime.py src/traffic_master_ai/defense/d0_mvp/api/check.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py tests/defense/test_storage_env_config.py tests/defense/test_runtime_policy_read_adapter.py tests/defense/test_backoffice_copilot_policy_projection.py tests/defense/test_backoffice_copilot_db_smoke.py src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
  - 결과: whitespace / conflict marker 문제 없음

### 5. 남은 리스크

- authoritative control-plane write를 실제 admin/optimizer workflow에서 호출하는 application wiring은 아직 없다.
- projection sync/resync는 thin service entrypoint까지만 있고, background worker / scheduler / lag alerting은 아직 없다.
- real PostgreSQL/Redis package와 실제 서버를 붙인 infra-backed integration은 아직 없다.

### 6. Task D로 넘길 입력

- strict authority entrypoint
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py`
  - `PostgresStrictPolicyAuthorityService.save_policy_version()`
  - `PostgresStrictPolicyAuthorityService.save_rollout_state()`
  - `PostgresStrictPolicyAuthorityService.sync_runtime_projection()`
  - `PostgresStrictPolicyAuthorityService.resync_runtime_projection()`
- runtime strict read path
  - `src/traffic_master_ai/defense/d0_mvp/policy/runtime_read_adapter.py`
  - `src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
  - `src/traffic_master_ai/defense/d0_mvp/api/runtime.py`
- prod fallback / config contract
  - `src/traffic_master_ai/defense/storage_env.py`
  - strict default: `TM_POLICY_ALLOW_LOCAL_FALLBACK=false`, `TM_ALLOW_IN_MEMORY_REDIS=false`
  - explicit local mode only: `TM_POLICY_ALLOW_LOCAL_FALLBACK=true`, `TM_ALLOW_IN_MEMORY_REDIS=true`
- 운영 안전장치 후속 입력
  - projection lag detection
  - background resync orchestration
  - real PostgreSQL/Redis integration smoke

## Task D

### 1. task 이름과 작업 일시

- 운영 안전장치 완성
- 2026-04-06 15:03:55 KST

### 2. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/storage_env.py`
- `src/traffic_master_ai/defense/api/etl_worker.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
- `src/traffic_master_ai/defense/d0_mvp/api/runtime.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `tests/defense/test_storage_env_config.py`
- `tests/defense/test_backoffice_copilot_policy_projection.py`
- `tests/defense/test_backoffice_copilot_db_smoke.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 3. 파일별 수정 요약

- `storage_env.py`: prod required env validator와 ClickHouse / projection retry env loader를 추가했다. `TM_ENV=prod` 기준으로 runtime, projection, ingest 경로의 fail-fast 규칙을 코드에 고정했다.
- `etl_worker.py`: prod ingest validator를 적용했고, ClickHouse write retry를 env 기반으로 읽도록 정리했다. 운영 replay 진입점으로 `replay_key()`, `replay_keys()`, `run_etl_replay_keys()`를 추가했다.
- `policy_projection_repository.py`: strict authority service의 `from_env()`가 prod validator와 projection retry env를 읽도록 보강했다. 운영 sync/resync 진입점으로 `run_runtime_projection_sync_from_env()`, `run_runtime_projection_resync_from_env()`를 추가했다.
- `loader.py`: strict runtime loader 생성 시 prod env validator를 먼저 통과하도록 보강했다.
- `runtime.py`: no-arg runtime 생성 시 prod strict authority env validator를 먼저 적용하게 정리했다.
- `storage/__init__.py`: 운영 projection sync/resync helper export를 추가했다.
- `12-production-operations-runbook.md`: prod required env, 계층별 failure handling, retry / replay / resync entrypoint, migration / bootstrap / cutover / rollback, 장애 triage 절차를 정리한 운영 runbook을 추가했다.
- `11-final-drift-review-and-handoff.md`: prod validator, operator replay/resync surface, 운영 runbook 반영 상태와 다음 phase handoff 입력을 현재 코드 기준으로 갱신했다.
- `test_storage_env_config.py`: prod required env fail-fast, retry env parsing, safe prod config pass 경로를 검증하도록 보강했다.
- `test_backoffice_copilot_policy_projection.py`: strict authority service가 projection retry env를 읽고 prod contract를 통과하는지 검증했다.
- `test_backoffice_copilot_db_smoke.py`: archive replay key 기반 재적재 smoke를 추가했다.
- `task-execution-log.md`: Task D 작업 기록을 append했다.

### 4. 검증에 사용한 명령과 결과 요약

- 필수 문서/코드 수동 대조
  - 기준: `agent.md`, `task-execution-log.md`, `11-final-drift-review-and-handoff.md`, `12-production-operations-runbook.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, `09-env-failure-handling-test-plan.md`, `storage_env.py`, `etl_worker.py`, `policy_projection_repository.py`, `loader.py`, `runtime.py`, `003_clickhouse_defense_audit_events.sql`
  - 결과: prod required env, strict authority 유지, replay/resync 운영 surface, runbook 절차가 현재 코드 구조와 모순 없음을 확인했다.
- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/storage_env.py src/traffic_master_ai/defense/api/etl_worker.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/api/runtime.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py tests/defense/test_storage_env_config.py tests/defense/test_backoffice_copilot_policy_projection.py tests/defense/test_backoffice_copilot_db_smoke.py`
  - 결과: 문법 오류 없음
- targeted test 실행
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_storage_env_config tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_backoffice_copilot_db_smoke`
  - 결과: `Ran 30 tests`, `OK`
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/storage_env.py src/traffic_master_ai/defense/api/etl_worker.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py src/traffic_master_ai/defense/d0_mvp/policy/loader.py src/traffic_master_ai/defense/d0_mvp/api/runtime.py src/traffic_master_ai/defense/backoffice_copilot/storage/__init__.py src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md tests/defense/test_storage_env_config.py tests/defense/test_backoffice_copilot_policy_projection.py tests/defense/test_backoffice_copilot_db_smoke.py`
  - 결과: whitespace / conflict marker 문제 없음

### 5. 남은 리스크

- admin/optimizer 실제 write path는 아직 strict authority service에 완전히 연결되지 않았다.
- projection sync/resync는 운영 entrypoint와 runbook까지는 있지만, background worker / scheduler / lag alerting은 아직 없다.
- real PostgreSQL/Redis/ClickHouse server를 붙인 infra-backed cutover rehearsal과 integration smoke는 아직 없다.

### 6. Task E로 넘길 입력

- prod env / fail-fast contract
  - `src/traffic_master_ai/defense/storage_env.py`
  - `validate_runtime_policy_env_for_prod()`
  - `validate_control_plane_projection_env_for_prod()`
  - `validate_clickhouse_ingest_env_for_prod()`
- 운영 replay / resync entrypoint
  - `src/traffic_master_ai/defense/api/etl_worker.py`
  - `ETLWorker.replay_key()`
  - `ETLWorker.replay_keys()`
  - `run_etl_replay_keys()`
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_projection_repository.py`
  - `run_runtime_projection_sync_from_env()`
  - `run_runtime_projection_resync_from_env()`
- 운영 절차 문서
  - `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md`
  - `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- 실제 저장소 기준 검증 우선순위
  - prod env matrix 검증
  - replay / resync / rollback dry-run
  - infra-backed PostgreSQL / Redis / ClickHouse smoke

## Task E

### 1. task 이름과 작업 일시

- 실제 저장소 기준 검증
- 2026-04-06 15:25:22 KST

### 2. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py`
- `tests/defense/infra/docker-compose.storage-smoke.yml`
- `tests/defense/test_storage_integration_real.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 3. 파일별 수정 요약

- `clickhouse_connection.py`: 인증 정보가 포함된 `TM_CLICKHOUSE_URL`에서도 HTTP endpoint host/port를 올바르게 분리하도록 보정했다. 실제 ClickHouse HTTP insert/select가 `default:password@host` URL에서 깨지지 않게 정리했다.
- `policy_control_plane_repository.py`: PostgreSQL JSONB 컬럼 write 시 `dict`/`list` payload를 psycopg `Jsonb`로 감싸 실제 PostgreSQL write/read smoke가 통과하도록 보정했다.
- `clickhouse_read_models.py`: ClickHouse HTTP JSON 응답에서 64-bit 정수가 문자열로 오는 실제 저장소 동작을 받아들이도록 int parser를 보강했다.
- `docker-compose.storage-smoke.yml`: local container 기반 PostgreSQL / Redis / ClickHouse smoke infra를 추가했다. ClickHouse는 explicit user/password와 healthcheck를 포함한다.
- `test_storage_integration_real.py`: 실제 PostgreSQL write/read, Redis projection + strict runtime read, ClickHouse raw fact ingest + session/match/candidate read model 조회를 검증하는 infra-backed integration smoke를 추가했다.
- `13-real-storage-smoke-guide.md`: local container 기반 실제 저장소 smoke 실행 절차, env 전제, venv 준비, teardown, 실패 해석 가이드를 문서화했다.
- `11-final-drift-review-and-handoff.md`: local container 기준 infra-backed smoke가 생긴 상태로 축별 상태와 남은 managed/service-level gap을 갱신했다.
- `task-execution-log.md`: Task E 작업 기록을 append했다.

### 4. 검증에 사용한 명령과 결과 요약

- infra 준비
  - 명령: `python3 -m venv .venv-storage-smoke && ./.venv-storage-smoke/bin/python -m pip install sqlalchemy redis 'psycopg[binary]'`
  - 결과: 실제 저장소 smoke 실행용 isolated Python 환경을 준비했다.
  - 명령: `docker compose -f tests/defense/infra/docker-compose.storage-smoke.yml up -d --wait`
  - 결과: PostgreSQL / Redis / ClickHouse local container가 모두 healthy 상태로 올라왔다.
- 실제 저장소 smoke 실행
  - 명령: `TM_REAL_STORAGE_SMOKE=1 TM_ENV=prod TM_PG_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:35432/postgres' TM_REDIS_URL='redis://127.0.0.1:36379/0' TM_CLICKHOUSE_URL='http://default:clickhouse@127.0.0.1:38123/default' TM_S3_BUCKET='storage-smoke-bucket' TM_ROLLOUT_SALT='storage-smoke-salt' TM_POLICY_ALLOW_LOCAL_FALLBACK=false TM_ALLOW_IN_MEMORY_REDIS=false PYTHONPATH=src ./.venv-storage-smoke/bin/python -m unittest -v tests.defense.test_storage_integration_real`
  - 결과: `Ran 2 tests`, `OK`
  - observability 흐름: fake archive body -> `ETLWorker.replay_key()` -> real ClickHouse `defense_audit_events` -> `defense_session_rollups` / `defense_match_rollups` / `defense_post_review_candidates_v1` 조회 통과
  - control-plane/runtime 흐름: real PostgreSQL write/read -> Redis projection sync -> strict `PolicyLoader.from_env()` read 통과
- 관련 contract 회귀 확인
  - 명령: `PYTHONPATH=src ./.venv-storage-smoke/bin/python -m unittest tests.defense.test_backoffice_copilot_clickhouse_storage tests.defense.test_backoffice_copilot_clickhouse_read_models tests.defense.test_backoffice_copilot_policy_control_plane_storage tests.defense.test_storage_env_config tests.defense.test_storage_integration_real`
  - 결과: `Ran 39 tests`, `OK (skipped=2)`
- 문법 / 포맷 확인
  - 명령: `PYTHONPATH=src ./.venv-storage-smoke/bin/python -m py_compile src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py tests/defense/test_storage_integration_real.py`
  - 결과: 문법 오류 없음
  - 명령: `git diff --check -- src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py tests/defense/infra/docker-compose.storage-smoke.yml tests/defense/test_storage_integration_real.py src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
  - 결과: whitespace / conflict marker 문제 없음
- infra 정리
  - 명령: `docker compose -f tests/defense/infra/docker-compose.storage-smoke.yml down -v`
  - 결과: local smoke container와 volume을 정리했다.

### 5. 남은 리스크

- 이번 smoke는 local container 기준이다. managed PostgreSQL / Redis / ClickHouse의 auth, TLS, network policy, resource limit는 아직 검증하지 않았다.
- observability 흐름은 real ClickHouse를 썼지만 archive source는 fake S3 body를 사용한다. 실제 object store 연동 smoke는 아직 없다.
- admin/optimizer 실제 application write path와 projection scheduler/orchestrator는 여전히 범위 밖이다.

### 6. Task F로 넘길 입력

- 실제 저장소 smoke entrypoint
  - `tests/defense/infra/docker-compose.storage-smoke.yml`
  - `tests/defense/test_storage_integration_real.py`
  - `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md`
- 실제 저장소 smoke에서 드러나 보정된 contract
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py`
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/policy_control_plane_repository.py`
  - `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_read_models.py`
- release gate에서 추가 확인할 항목
  - managed/service-level PostgreSQL / Redis / ClickHouse smoke
  - actual object store replay smoke
  - prod env matrix와 runbook cutover / rollback dry-run

## Task F

### 1. task 이름과 작업 일시

- 최종 release gate / prod v1 선언 점검
- 2026-04-06 15:32:34 KST

### 2. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/14-release-gate-prod-v1.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 3. 파일별 수정 요약

- `13-real-storage-smoke-guide.md`: 실제 smoke 실행 예시의 PostgreSQL URL을 `postgresql+psycopg://...`로 보정해 Task E 실행 결과와 문서가 일치하도록 정리했다.
- `14-release-gate-prod-v1.md`: Task A~E 결과를 종합한 최종 release gate 문서를 추가했다. prod v1 선언 가능 여부를 `제한적 선언 가능`으로 명시하고, 축별 상태, blocker / non-blocker, 운영 투입 전 추가 확인 항목, 후속 backlog, handoff 주의사항을 고정했다.
- `11-final-drift-review-and-handoff.md`: 최종 handoff 입력 목록에 release gate 문서를 추가했다.
- `task-execution-log.md`: Task F 최종 판정 기록을 append했다.

### 4. 검증에 사용한 명령과 결과 요약

- Task A~E 결과 수동 대조
  - 기준: `task-execution-log.md`, `11-final-drift-review-and-handoff.md`, `12-production-operations-runbook.md`, `13-real-storage-smoke-guide.md`, `32-storage-architecture.md`, `33-docs-vs-current-code-gap-analysis.md`, Task E infra-backed smoke 결과
  - 결과: local real-storage smoke 통과 범위와 managed infra 미검증 범위를 분리해도 문서/로그/코드 사이 모순이 없음을 확인했다.
- 실제 저장소 smoke 결과 재사용 확인
  - 기준 결과: `Ran 2 tests`, `OK`
  - 해석: observability 흐름과 control-plane/runtime 흐름은 local container 기준 real PostgreSQL / Redis / ClickHouse에서 통과한 상태다.
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/14-release-gate-prod-v1.md src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`
  - 결과: whitespace / conflict marker 문제 없음

### 5. 최종 남은 리스크

- managed PostgreSQL / Redis / ClickHouse auth, TLS, network policy는 아직 미검증이다.
- actual object store를 사용하는 observability replay smoke는 아직 없다.
- admin/optimizer 실제 application write path와 projection scheduler/orchestrator는 아직 미연결이다.

### 6. 다음 phase 또는 handoff 입력

- 최종 판정 문서
  - `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/14-release-gate-prod-v1.md`
- 운영 절차 / 실검증 문서
  - `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md`
  - `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md`
- 현재 상태 요약
  - `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
  - `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`
- release gate blocker
  - managed/service-level PostgreSQL / Redis / ClickHouse smoke
  - actual object store replay smoke
  - admin/optimizer write path 연결 여부

## Task G

### 1. task 이름과 작업 일시

- admin / optimizer write path를 strict authority service로 완전 통일
- 2026-04-06 16:07:48 KST

### 2. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/d0_mvp/optimizer/pipeline.py`
- `src/traffic_master_ai/defense/d0_mvp/api/runtime.py`
- `tests/defense/test_offline_optimizer_strict_authority.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/14-release-gate-prod-v1.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 3. 파일별 수정 요약

- `optimizer/pipeline.py`: `OfflineOptimizer`에 strict authority-aware write path를 추가했다. `run_once()`는 `policy_optimization_runs` authoritative row를 저장하고, `start_canary()` / `expand_rollout()` / `rollback()`은 local store write 대신 `PostgreSQL authoritative write -> Redis projection sync` 흐름으로 candidate policy, rollout state, rollout event를 기록한다. `current_rollout_state()`도 authority service가 있으면 PostgreSQL authoritative row를 읽는다.
- `api/runtime.py`: `DefenseRuntime`에 optional `policy_authority_service` 주입 지점을 추가하고, strict authority mode에서 `offline_optimizer_service()`가 `PostgresStrictPolicyAuthorityService`를 사용하도록 연결했다. runtime request path read authority는 바꾸지 않았다.
- `test_offline_optimizer_strict_authority.py`: optimizer write 경로가 authoritative policy version save, rollout event append, rollout state projection sync, optimization run save로 이어지는지 검증하는 테스트를 추가했다.
- `11-final-drift-review-and-handoff.md`: control-plane repository 축의 `admin/optimizer workflow 실연결` gap을 제거하고, 남은 gap을 managed/service-level 검증 중심으로 좁혔다.
- `12-production-operations-runbook.md`: authoritative write + sync surface에 `DefenseRuntime.offline_optimizer_service()`와 `OfflineOptimizer.run_once()/start_canary()/expand_rollout()/rollback()`를 추가하고, strict mode에서 local/direct write 우회가 아니라 authority service를 거쳐야 함을 명시했다.
- `14-release-gate-prod-v1.md`: release gate blocker에서 `admin/optimizer 실제 write path 미연결`을 제거하고, control-plane 축을 `optimizer/admin official write path` 기준으로 갱신했다.
- `task-execution-log.md`: 마지막 AI팀 blocker 해소 기록을 append했다.

### 4. 검증에 사용한 명령과 결과 요약

- 문법 확인
  - 명령: `PYTHONPATH=src python3 -m py_compile src/traffic_master_ai/defense/d0_mvp/optimizer/pipeline.py src/traffic_master_ai/defense/d0_mvp/api/runtime.py tests/defense/test_offline_optimizer_strict_authority.py`
  - 결과: 문법 오류 없음
- strict authority write path 회귀
  - 명령: `PYTHONPATH=src python3 -m unittest tests.defense.test_offline_optimizer_strict_authority tests.defense.test_backoffice_copilot_policy_projection tests.defense.test_runtime_policy_read_adapter tests.defense.test_backoffice_copilot_db_smoke`
  - 결과: `Ran 32 tests`, `OK`
  - 해석: optimizer/admin 성격의 write path가 authoritative service와 projection sync를 거쳐 strict runtime read와 충돌 없이 동작함을 확인했다.
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/d0_mvp/optimizer/pipeline.py src/traffic_master_ai/defense/d0_mvp/api/runtime.py tests/defense/test_offline_optimizer_strict_authority.py src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/14-release-gate-prod-v1.md`
  - 결과: whitespace / conflict marker 문제 없음

### 5. 남은 리스크

- 남은 blocker는 managed PostgreSQL / Redis / ClickHouse auth, TLS, network policy 검증과 actual object store replay smoke다.
- background scheduler/orchestrator, lag alerting, processed-key ledger는 여전히 운영 hardening backlog지만, AI팀 기준 공식 write path blocker는 아니다.

### 6. 인프라팀 연결 후 사용자가 직접 수행할 마지막 검증 입력

- managed infra 연결 뒤 아래 순서로 검증한다.
  - `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md` 기준으로 managed PostgreSQL / Redis / ClickHouse smoke 재실행
  - `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md` 기준으로 bootstrap / cutover / rollback dry-run
  - actual object store archive 1개 기준 `ETLWorker.replay_key()` 또는 `run_etl_replay_keys()` smoke
  - `DefenseRuntime.offline_optimizer_service()` 경유 `run_once()`, `start_canary()`, `expand_rollout()`, `rollback()` 순서의 operator dry-run

## Task 23

### 1. task 번호와 제목

- Task 23. Canonical Audit Contract 통일

### 2. 작업 일시

- 2026-04-09 10:42:43 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/audit_contract.py`
- `src/traffic_master_ai/defense/api/audit.py`
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/loader.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_ingest.py`
- `src/traffic_master_ai/defense/d0_mvp/api/runtime.py`
- `src/traffic_master_ai/defense/d0_mvp/observability/schemas.py`
- `src/traffic_master_ai/defense/d0_mvp/observability/audit_logger.py`
- `src/traffic_master_ai/defense/d0_mvp/observability/collector.py`
- `src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py`
- `src/traffic_master_ai/defense/d0_mvp/observability/jsonl_retention.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/04-canonical-audit-minimum-contract.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`
- `tests/defense/test_canonical_audit_contract.py`
- `tests/defense/test_backoffice_copilot_clickhouse_storage.py`
- `tests/defense/test_backoffice_copilot_db_smoke.py`
- `tests/defense/test_d0_runtime_policy_alignment.py`
- `tests/defense/test_storage_integration_real.py`
- `tests/defense/fixtures/backoffice_copilot/single_candidate_t2.jsonl`

### 4. contract 변경 요약

- canonical audit row를 flat `snake_case` + top-level fixed typed field + `raw_payload` object로 통일했다.
- `audit.py` evaluate/challenge row는 모두 canonical contract만 emit하도록 바꿨다.
- `d0_mvp/api/runtime.py` audit emission도 nested `camelCase` row 대신 canonical row를 직접 기록하도록 바꿨다.
- `risk_tier`를 canonical tier field로 고정하고 `defense_tier` 추측 정규화를 제거했다.
- `clickhouse_ingest.py`는 canonical top-level field만 읽고 `raw_payload_json`에는 `raw_payload`만 serialize 하도록 단순화했다.
- Backoffice raw loader는 canonical row를 기본으로 읽고 legacy row는 compatibility로만 허용한다.
- local `AuditWarehouse`는 canonical 입력을 받되 admin/dashboard 호환용 alias row를 내부에 저장하도록 정리했다.

### 5. 검증에 사용한 명령과 결과 요약

- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/audit_contract.py src/traffic_master_ai/defense/api/audit.py src/traffic_master_ai/defense/api/etl_worker.py src/traffic_master_ai/defense/backoffice_copilot/ingest/loader.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_ingest.py src/traffic_master_ai/defense/d0_mvp/api/runtime.py src/traffic_master_ai/defense/d0_mvp/observability/schemas.py src/traffic_master_ai/defense/d0_mvp/observability/audit_logger.py src/traffic_master_ai/defense/d0_mvp/observability/collector.py src/traffic_master_ai/defense/d0_mvp/observability/warehouse.py src/traffic_master_ai/defense/d0_mvp/observability/jsonl_retention.py tests/defense/test_canonical_audit_contract.py tests/defense/test_backoffice_copilot_clickhouse_storage.py tests/defense/test_backoffice_copilot_db_smoke.py tests/defense/test_d0_runtime_policy_alignment.py`
  - 결과: 문법 오류 없음
- canonical contract / ETL / raw loader 회귀
  - 명령: `.venv/bin/pytest -q tests/defense/test_canonical_audit_contract.py tests/defense/test_backoffice_copilot_clickhouse_storage.py tests/defense/test_backoffice_copilot_db_smoke.py tests/defense/test_d0_runtime_policy_alignment.py tests/defense/test_backoffice_copilot_ingest.py`
  - 결과: `31 passed`
- runtime / warehouse / Backoffice compatibility 추가 회귀
  - 명령: `.venv/bin/pytest -q tests/defense/test_d0_runtime_contract_validation.py tests/defense/test_d0_runtime_sync_api.py tests/defense/test_d0_runtime_auth_guard.py tests/defense/test_backoffice_copilot_candidates.py tests/defense/test_backoffice_copilot_session_analysis.py`
  - 결과: `16 passed`

### 6. 남은 리스크

- historical archive에 legacy mixed schema가 남아 있으면 새 ETL mapper는 그대로 거부한다.
- canonical top-level field는 통일됐지만 event taxonomy 자체는 아직 `EVALUATE`, `CHALLENGE_VERIFIED`, D0 runtime catalog가 함께 존재한다.
- `match_id`, `http_status`, `dedup_is_duplicate`, rollout field는 아직 top-level typed field로 승격되지 않았다.

### 7. 다음 task 입력

- 다음 우선순위는 event taxonomy 정규화 여부를 결정하고 `EVALUATE` / `CHALLENGE_*` / D0 runtime catalog를 하나의 운영 카탈로그로 맞추는 것이다.
- 그 다음 단계로 `match_id`, `http_status`, `dedup_is_duplicate` 중 실제 조회 빈도가 높은 필드부터 top-level typed 승격 task를 분리하는 것이 안전하다.

## Task 25

### 1. task 번호와 제목

- Task 25. ETL Batch / Flush / Retry 튜닝

### 2. 작업 일시

- 2026-04-09 10:53:01 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/storage_env.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py`
- `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_repository.py`
- `src/traffic_master_ai/defense/api/etl_worker.py`
- `tests/defense/test_storage_env_config.py`
- `tests/defense/test_backoffice_copilot_clickhouse_storage.py`
- `tests/defense/test_backoffice_copilot_db_smoke.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. tuning 변경 요약

- ClickHouse ingest 기본값을 short archive cadence 기준으로 조정했다. `TM_CLICKHOUSE_INGEST_BATCH_SIZE` 기본값은 `256`, `TM_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS` 기본값은 `3`, `TM_CLICKHOUSE_WRITE_RETRY_BACKOFF_MS` 기본값은 `200`으로 정리했다.
- staging/prod 운영 권장값도 함께 고정했다. staging은 `batch_size=128`, prod는 `batch_size=256`, 두 환경 모두 `retry_max_attempts=3`, `retry_backoff_ms=200`을 권장값으로 문서화했다.
- env loader는 `TM_CLICKHOUSE_INGEST_BATCH_SIZE`, `TM_CLICKHOUSE_INGEST_TIMEOUT_MS`, `TM_CLICKHOUSE_WRITE_RETRY_MAX_ATTEMPTS`를 positive integer로 검증하도록 강화했다.
- `ClickHouseBatchWriteError`는 `backoff_ms`, `last_error_message`를 보존하도록 바꿨고, retry 로그에 `attempt`, `row_count`, `backoff_ms`, `last_error`가 함께 남도록 정리했다.
- `ETLWorker`는 key 단위 ingest 결과에 `source_row_count`, `attempted_row_count`, `flush_count`, `batch_size`, `retry_*`를 포함하고, flush log와 object-level failure log에 `key`, `flush_index`, `retry_max_attempts`, `retry_backoff_ms`, `last_error`를 남기도록 보강했다.
- 짧은 주기 ingest를 가정한 multi-flush smoke와 retry exhaustion error surface 검증을 추가했다.

### 5. 검증에 사용한 명령과 결과 요약

- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/storage_env.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_repository.py src/traffic_master_ai/defense/api/etl_worker.py tests/defense/test_storage_env_config.py tests/defense/test_backoffice_copilot_clickhouse_storage.py tests/defense/test_backoffice_copilot_db_smoke.py`
  - 결과: 문법 오류 없음
- ETL tuning / retry / smoke 회귀
  - 명령: `.venv/bin/pytest -q tests/defense/test_storage_env_config.py tests/defense/test_backoffice_copilot_clickhouse_storage.py tests/defense/test_backoffice_copilot_db_smoke.py`
  - 결과: `35 passed`
- 포맷 확인
  - 명령: `git diff --check -- src/traffic_master_ai/defense/storage_env.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_connection.py src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_repository.py src/traffic_master_ai/defense/api/etl_worker.py tests/defense/test_storage_env_config.py tests/defense/test_backoffice_copilot_clickhouse_storage.py tests/defense/test_backoffice_copilot_db_smoke.py`
  - 결과: whitespace / conflict marker 문제 없음

### 6. 남은 리스크

- processed-key ledger가 아직 없어서 같은 S3 object replay 자체를 완전히 막지는 못한다. 현재 안정성은 row dedupe와 operator replay discipline에 의존한다.
- retry/backoff는 synchronous path만 튜닝한 상태라 장기 장애나 sustained backlog를 흡수하는 background queue 성격의 완충 계층은 여전히 없다.
- batch 기본값을 낮춰도 object 수 자체가 급증하면 ETL 실행 횟수와 ClickHouse write call 수는 함께 늘어난다.

### 7. 다음 task 입력

- 다음 우선순위는 processed-key ledger 또는 archive move/mark-processed 규칙을 정해 replay idempotency를 운영 절차가 아니라 코드 경계로 고정하는 것이다.
- 그 다음 단계로 scheduler/lag metric/alerting을 붙여 archive 주기 단축 이후 ETL freshness를 실제 운영 지표로 관측 가능하게 만드는 것이 자연스럽다.

## Task 26

### 1. task 번호와 제목

- Task 26. Redis Processed-Key Ledger 최소 도입

### 2. 작업 일시

- 2026-04-09 11:25:34 KST

### 3. 실제로 수정한 파일 목록

- `src/traffic_master_ai/defense/storage_env.py`
- `src/traffic_master_ai/defense/api/etl_worker.py`
- `src/traffic_master_ai/defense/d0_mvp/state/keyspace.py`
- `src/traffic_master_ai/defense/d0_mvp/state/etl_processed_ledger.py`
- `src/traffic_master_ai/defense/d0_mvp/state/__init__.py`
- `tests/defense/test_storage_env_config.py`
- `tests/defense/test_etl_processed_ledger.py`
- `tests/defense/test_backoffice_copilot_db_smoke.py`
- `tests/defense/test_storage_integration_real.py`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/11-final-drift-review-and-handoff.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/12-production-operations-runbook.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/13-real-storage-smoke-guide.md`
- `src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log.md`

### 4. Redis ledger 설계 요약

- Redis processed-key prefix로 `tm:etl:processed:s3:`를 추가했다.
- object identity는 `{bucket}\n{object_key}\n{etag_or_dash}` canonical string을 만들고, `sha256` hash를 써서 최종 Redis key를 `tm:etl:processed:s3:{bucket}:{object_identity_hash}` 형태로 고정했다.
- ledger value는 JSON string으로 저장하고 `status`, `bucket`, `object_key`, `etag`, `processed_at_ms`, `row_count`만 남긴다.
- `TM_ETL_PROCESSED_LEDGER_TTL_SECONDS` env를 추가했고 기본값과 권장값은 `2592000`(30일)로 고정했다.
- normal ingest는 processed ledger hit면 object를 skip하고, ClickHouse write 전체 성공 후에만 ledger를 기록한다.
- explicit replay는 `force=True`일 때만 ledger를 bypass한다. force replay 성공 시 ledger는 같은 key에 다시 overwrite 된다.
- ETag가 list/head metadata에서 있으면 identity에 포함하고, 없으면 bucket + object key + `-` fallback으로 동작한다. 이 fallback은 exact identity가 아니라 최소 운영 dedup cache 수준임을 문서에 명시했다.

### 5. 검증에 사용한 명령과 결과 요약

- 문법 확인
  - 명령: `python3 -m py_compile src/traffic_master_ai/defense/storage_env.py src/traffic_master_ai/defense/api/etl_worker.py src/traffic_master_ai/defense/d0_mvp/state/keyspace.py src/traffic_master_ai/defense/d0_mvp/state/etl_processed_ledger.py src/traffic_master_ai/defense/d0_mvp/state/__init__.py tests/defense/test_storage_env_config.py tests/defense/test_etl_processed_ledger.py tests/defense/test_backoffice_copilot_db_smoke.py tests/defense/test_storage_integration_real.py`
  - 결과: 문법 오류 없음
- Redis ledger / ETL skip / force replay / TTL 회귀
  - 명령: `.venv/bin/pytest -q tests/defense/test_storage_env_config.py tests/defense/test_etl_processed_ledger.py tests/defense/test_backoffice_copilot_db_smoke.py tests/defense/test_storage_integration_real.py`
  - 결과: `30 passed, 2 skipped`

### 6. 남은 리스크

- 이 구현은 inflight lock이나 distributed lease가 아니라 completed object TTL cache라서 동시에 같은 object를 잡는 race는 막지 못한다.
- explicit replay가 ETag를 얻지 못하는 환경에서는 bucket + object key + `-` fallback identity로 동작하므로 strict object version 구분은 약해질 수 있다.
- ledger mark 실패가 ClickHouse write 성공 뒤에 발생하면 다음 run에서 같은 object를 다시 ingest할 수 있다. 현재는 이 상태를 조용히 숨기지 않고 실패로 surface한다.

### 7. 다음 task 입력

- 다음 우선순위는 inflight lock 또는 archive move/mark-processed 규칙을 추가해 concurrent duplicate ingest risk를 더 줄이는 것이다.
- 그 다음 단계로 scheduler/lag metric/alerting을 붙여 processed-key ledger hit율과 ETL freshness를 운영 지표로 관측 가능하게 만드는 것이 자연스럽다.
