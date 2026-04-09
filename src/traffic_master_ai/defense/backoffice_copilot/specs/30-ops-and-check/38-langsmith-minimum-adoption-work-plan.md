# TM AI Team LangSmith 최소 도입 작업 계획서

## 목차

1. 작업 한 줄 요약
2. 이번 작업의 목표
3. 현재 코드 기준 1차 적용 대상
4. 이번 단계에서 하지 않는 것
5. 단계별 작업 계획
6. 메타데이터 기준
7. 환경 변수 및 운영 기준
8. 검증 방법
9. 산출물
10. 완료 기준
11. 리스크와 주의사항

## 1. 작업 한 줄 요약

TM AI 팀에서 OpenAI API가 호출되는 핵심 경로에 LangSmith tracing을 붙여서,
기능별, 세션별, 단계별 token과 cost를 보이게 만드는 작업이다.

## 2. 이번 작업의 목표

이번 1차 목표는 복잡하지 않다.

1. LangSmith에 LLM 호출 trace가 남아야 한다.
2. 각 호출의 input tokens, output tokens, total tokens, total cost를 확인할 수 있어야 한다.
3. 최소한 `session_id`, `feature_name`, `agent_step_name`, `environment`로 구분할 수 있어야 한다.
4. 팀이 "어떤 기능이 얼마를 쓰는지" 기본 답변을 할 수 있어야 한다.

쉽게 말하면 이번 작업은
"우리 AI 호출이 어디서 얼마나 돈을 쓰는지 보이게 만드는 것"까지가 범위다.

## 3. 현재 코드 기준 1차 적용 대상

현재 저장소에서 OpenAI API 사용 지점은 아래 3축이 먼저 보인다.

### 3.1 Backoffice Copilot

- 파일: `src/traffic_master_ai/defense/backoffice_copilot/adapters/openai.py`
- 성격:
  - suspicious review 판단 호출
  - window summary 생성 호출
- 1차 적용 이유:
  - 운영 판단에 직접 연결된다.
  - `session_id`가 이미 입력에 들어온다.
  - 기능 이름을 `backoffice_copilot`으로 고정하기 쉽다.

### 3.2 Offline Policy / Effect Evaluator

- 파일: `src/traffic_master_ai/defense/d0_mvp/optimizer/effect_evaluator.py`
- 성격:
  - 정책 제안 또는 효과 평가용 OpenAI-compatible 호출
- 1차 적용 이유:
  - 실험/정책 비교 과정에서 비용이 커질 수 있다.
  - 향후 `policy_optimizer`, `experiment_runner` 축으로 보기 좋다.

### 3.3 Offline Batch Judge Pipeline

- 파일: `src/traffic_master_ai/defense/offline/pipeline.py`
- 성격:
  - batch 기반 세션 판별 호출
  - `/v1/responses` 경로 사용
- 1차 적용 이유:
  - batch size와 reasoning 설정에 따라 비용 차이가 크게 날 수 있다.
  - 세션 묶음 단위 비용 관측이 필요하다.

### 3.4 1차 우선순위

우선순위는 아래처럼 잡는다.

1. `backoffice_copilot`
2. `d0_mvp/optimizer/effect_evaluator.py`
3. `offline/pipeline.py`

이 순서가 맞는 이유는
운영 영향도가 높은 기능부터 먼저 보이게 해야 하고,
대표 경로를 먼저 붙여야 이후 공통 유틸로 정리하기 쉽기 때문이다.

## 4. 이번 단계에서 하지 않는 것

이번 계획에서 제외하는 항목은 아래와 같다.

- Grafana 연동
- Prometheus, OTel, warehouse 통합 관제
- 전 서비스 일괄 적용
- 비용 알람 자동화
- 조직 공통 대시보드 설계
- 정교한 evaluation 체계 구축
- 프록시 비용, 브라우저 비용, 인건비까지 합친 총원가 계산

즉 이번 단계는 LangSmith 자체 UI 기준으로
trace, token, cost가 보이면 성공이다.

## 5. 단계별 작업 계획

## 5.1 0단계. 이름과 운영 기준 먼저 고정

코드부터 붙이면 나중에 이름이 다 갈라진다.
그래서 먼저 아래를 고정한다.

- LangSmith project 이름
- `environment` 값 규칙
- `feature_name` 값 규칙
- `agent_step_name` 값 규칙
- 공통 metadata key 이름

권장 규칙은 아래처럼 단순하게 간다.

- project: `tm-ai`
- environment: `dev`, `staging`, `prod`
- owner_team: `TM_AI`
- feature_name:
  - `backoffice_copilot`
  - `policy_optimizer`
  - `challenge_analysis`
  - `experiment_runner`
- agent_step_name 예시:
  - `review_session`
  - `summarize_window`
  - `evaluate_policy_effect`
  - `offline_batch_judge`

## 5.2 1단계. LangSmith 연동 방식 공통화

여기서는 각 파일마다 제각각 심지 않고,
공통 tracing helper를 하나 두는 방향이 좋다.

현재 코드 기준으로는 OpenAI Python SDK를 공통 사용하지 않고
`urllib` 기반 직접 호출이 많다.
그래서 1차는 `wrap_openai` 같은 SDK 의존 방식보다
LangSmith SDK를 이용한 수동 tracing helper 방식이 더 안전하다.

작업 내용:

1. LangSmith 사용 여부를 제어하는 설정 추가
2. tracing wrapper 또는 helper 함수 추가
3. OpenAI 호출 전후에 run name, metadata, error status를 기록하는 공통 진입점 마련
4. LangSmith 비활성 시 기존 동작이 그대로 유지되게 처리

이 단계의 목적은
"LangSmith를 붙여도 기존 로직이 깨지지 않게 하는 뼈대 만들기"다.

## 5.3 2단계. Backoffice Copilot부터 연결

첫 적용 대상은 `backoffice_copilot/adapters/openai.py`가 맞다.

작업 내용:

1. review 호출에 trace 추가
2. summary 호출에 trace 추가
3. metadata에 `match_id`, `session_id`, `feature_name`, `agent_step_name`, `environment` 기록
4. 성공, 실패, latency, token, cost 확인

이 단계가 중요한 이유는
운영자가 실제로 보는 핵심 기능에서 바로 효과를 확인할 수 있기 때문이다.

## 5.4 3단계. Effect Evaluator 연결

두 번째는 `d0_mvp/optimizer/effect_evaluator.py`다.

작업 내용:

1. OpenAI-compatible caller의 호출 경로에 trace 추가
2. retry, timeout, http error 결과를 trace에 남기기
3. `policy_version` 또는 실험 식별자를 metadata에 연결
4. 기능 이름은 `policy_optimizer` 또는 `experiment_runner`로 고정

이 단계의 목적은
"정책 실험 경로에서 어디서 토큰과 비용이 커지는지"를 보이게 하는 것이다.

## 5.5 4단계. Offline Batch Pipeline 연결

세 번째는 `offline/pipeline.py`다.

작업 내용:

1. batch 요청 단위 trace 추가
2. batch 안에 포함된 세션 수를 metadata에 기록
3. `session_id` 단건 기준이 어려우면 batch root에 `thread_id` 또는 batch id를 둔다
4. reasoning 설정, batch size, model 이름을 metadata에 같이 남긴다

이 단계의 목적은
"배치가 커질수록 비용이 어떻게 바뀌는지"를 보는 것이다.

## 5.6 5단계. LangSmith UI 검증

코드 연결 후에는 실제 UI에서 아래를 확인한다.

1. trace 목록이 보이는가
2. feature_name으로 구분되는가
3. session_id 또는 thread_id로 검색 가능한가
4. token과 cost가 보이는가
5. 실패 run과 느린 run을 trace tree에서 찾을 수 있는가

이 검증이 끝나야 1차 도입 완료로 본다.

## 5.7 6단계. 팀 운영 정리

마지막으로 팀이 실제로 계속 쓸 수 있게 짧게 정리한다.

정리 항목:

- project 이름
- 필수 env 변수
- feature_name 규칙
- 필수 metadata 규칙
- "새 OpenAI 호출 추가 시 무엇을 넣어야 하는지" 체크리스트

## 6. 메타데이터 기준

## 6.1 최소 필수

이번 단계에서 최소 필수는 아래 4개다.

- `session_id`
- `feature_name`
- `agent_step_name`
- `environment`

## 6.2 권장 항목

가능하면 아래도 같이 넣는 것이 좋다.

- `thread_id`
- `policy_version`
- `source_event_id`
- `owner_team`
- `match_id`
- `model_name`
- `batch_size`
- `reasoning_effort`

## 6.3 기능별 권장 매핑

### Backoffice Copilot

- `feature_name`: `backoffice_copilot`
- `agent_step_name`:
  - `review_session`
  - `summarize_window`
- `session_id`: 개별 세션 id
- `thread_id`: `match_id` 또는 run id

### Effect Evaluator

- `feature_name`: `policy_optimizer`
- `agent_step_name`: `evaluate_policy_effect`
- `thread_id`: optimization run id 또는 evaluation run id
- `policy_version`: 현재 평가 대상 버전

### Offline Batch Pipeline

- `feature_name`: `challenge_analysis` 또는 `experiment_runner`
- `agent_step_name`: `offline_batch_judge`
- `thread_id`: batch id
- `session_id`: 단건이 아니면 batch root에서는 비우고 child 단위에서만 사용 검토

## 7. 환경 변수 및 운영 기준

이번 도입에서는 최소한 아래를 관리 대상으로 둔다.

- `LANGSMITH_API_KEY`
- `LANGSMITH_TRACING=true`
- `LANGSMITH_PROJECT=tm-ai`
- `TM_AI_ENV=dev|staging|prod`

선택 항목:

- `LANGSMITH_WORKSPACE_ID`
- `LANGSMITH_ENDPOINT`

정리:

- `LANGSMITH_WORKSPACE_ID`는 여러 workspace에 연결된 key일 때만 명시한다.
- 현재처럼 workspace 범위가 명확한 Service Key면 필수가 아닐 수 있다.
- `LANGSMITH_ENDPOINT`는 EU 또는 self-hosted 환경에서만 추가한다.

운영 원칙은 단순하게 간다.

1. 개인 키가 아니라 팀 공용 Service Key 기준으로 운영한다.
2. dev와 prod는 반드시 구분한다.
3. local 임시 실험은 기본적으로 공용 project를 오염시키지 않게 주의한다.
4. metadata 이름은 한번 정하면 바꾸지 않는다.

## 8. 검증 방법

검증은 기능 테스트보다 "관측이 실제로 남는가"에 초점을 둔다.

### 8.1 기본 검증

1. 대표 기능 1개 실행
2. LangSmith 프로젝트에서 trace 생성 확인
3. trace 상세에서 token, cost, latency 확인
4. metadata 값 확인

### 8.2 기능별 검증

- `backoffice_copilot`
  - review 호출 1건
  - summary 호출 1건
- `effect_evaluator`
  - 성공 호출 1건
  - timeout 또는 error 상황 1건
- `offline pipeline`
  - 소형 batch 1건

### 8.3 회귀 검증

아래는 깨지면 안 된다.

- LangSmith 비활성 상태에서 기존 호출이 정상 동작할 것
- 기존 테스트가 가능한 범위에서 유지될 것
- timeout, retry, invalid response 처리 로직이 변질되지 않을 것

## 9. 산출물

이번 작업이 끝나면 아래 산출물이 있어야 한다.

1. LangSmith 최소 연동 코드
2. OpenAI 호출 공통 tracing helper 또는 wrapper
3. 1차 적용 기능 연결 완료
4. env 설정 문서
5. 팀용 짧은 운영 체크리스트
6. 필요 시 기존 observability payload의 `langsmith` 필드에 `run_id`, `trace_url` 연결 방안 정리

## 10. 완료 기준

아래 5개를 만족하면 1차 완료다.

1. LangSmith 프로젝트에 TM AI 팀 호출 trace가 남는다.
2. `backoffice_copilot` 최소 1개 기능에서 token과 cost가 확인된다.
3. `session_id`, `feature_name`, `agent_step_name`, `environment`가 실제 metadata로 남는다.
4. `effect_evaluator` 또는 `offline pipeline` 중 최소 1개 추가 경로까지 trace가 연결된다.
5. 팀 내부에서 기능별 기본 비용 확인이 가능하다.

## 11. 리스크와 주의사항

### 11.1 가장 큰 리스크

trace는 남는데 metadata가 제각각이면 나중에 못 쓴다.
이번 작업에서 제일 먼저 막아야 할 문제다.

### 11.2 비용 해석 주의

총비용만 보면 의미가 약하다.
반드시 요청당, 세션당, 기능별 평균 비용 관점으로 같이 봐야 한다.

### 11.3 배치 호출 주의

batch 호출은 한 trace에 여러 세션이 섞일 수 있다.
이 경우 `session_id` 하나만 억지로 넣지 말고 `thread_id`, `batch_size`, `session_count`를 같이 남기는 편이 낫다.

### 11.4 개인정보 주의

LangSmith metadata와 input에는 세션 식별과 운영 분석에 필요한 최소 정보만 넣는다.
민감 원문, 불필요한 사용자 식별 정보는 넣지 않는다.

## 최종 정리

이번 LangSmith 최소 도입은
`backoffice_copilot`, `effect_evaluator`, `offline pipeline` 세 경로를 중심으로
OpenAI 호출 trace, token, cost를 기능별과 세션별로 보이게 만드는 작업이다.

핵심은 많이 붙이는 것이 아니라
운영 가치가 큰 경로부터 정확하게 보이게 만드는 것이다.
