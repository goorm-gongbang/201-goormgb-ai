# LangSmith to Grafana Minimum Shared Observability Plan

## 목차

1. 한 줄 결정
2. 문서 목적
3. 이번 문서의 출발점
4. 핵심 결정
5. 범위와 제외 범위
6. 현재 코드 기준 전제
7. 목표 구조
8. 데이터 계약
9. 저장 모델
10. 수집 및 동기화 전략
11. Grafana 대시보드 최소 구성
12. 구현 작업 묶음
13. 검증 계획
14. 완료 기준
15. 리스크와 후속 판단 포인트

## 1. 한 줄 결정

LangSmith는 원천 trace 저장소와 상세 디버깅 화면으로 유지하고,
팀 공유용 비용과 토큰 집계는 별도 최소 적재 테이블을 통해 Grafana에서 본다.

## 2. 문서 목적

이 문서는 38번 LangSmith 최소 도입 계획서와
후속 LangSmith 실행 로그를 바탕으로,
팀 공용 비용과 토큰 관제를 prod 단계까지 연결하는 최소 구현 계획을 고정하기 위한 문서다.

이번 문서의 목적은 아래 4가지다.

1. LangSmith 이후 후속 작업의 목표 구조를 고정한다.
2. LangSmith와 Grafana의 역할 분리를 명확히 한다.
3. exporter, 저장 테이블, dashboard까지의 구현 순서를 묶음 단위로 정리한다.
4. 후속 코드 task가 바로 들어갈 수 있게 계약과 완료 기준을 잠근다.

## 3. 이번 문서의 출발점

이 문서는 아래 작업을 선행 입력으로 본다.

- [38-langsmith-minimum-adoption-work-plan.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/30-ops-and-check/38-langsmith-minimum-adoption-work-plan.md)
- [15-langsmith-minimum-adoption-e2e-plan.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/15-langsmith-minimum-adoption-e2e-plan.md)
- [task-execution-log-langsmith.md](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/specs/40-db-build-agent-pack/task-execution-log-langsmith.md)

특히 이미 확인된 사실은 아래와 같다.

- LangSmith tracing helper와 metadata 주입은 이미 붙어 있다.
- `backoffice_copilot.review_session`
- `backoffice_copilot.summarize_window`
- `policy_optimizer.evaluate_policy_effect`
- `policy_optimizer.audit_summary`
  경로는 실제 trace와 usage metadata 검증이 끝나 있다.
- observability payload에는 `langsmith.runId`, `langsmith.traceUrl`를 담을 수 있는 구조가 이미 있다.
- 지금의 부족한 점은 tracing 자체가 아니라 팀 공유용 집계와 시각화 계층이다.

## 4. 핵심 결정

## 4.1 역할 분리

- LangSmith:
  - 원천 trace 저장
  - run 상세 조회
  - 실패와 디버깅 drill-down
- Grafana:
  - 팀 공용 비용과 토큰 집계판
  - 기능별, 단계별, 일별 추세 시각화
- 집계 exporter:
  - LangSmith runs 조회
  - 최소 필드 추출
  - 적재 테이블 upsert

## 4.2 최소 구현 방향

- 새로운 tracing 시스템은 만들지 않는다.
- LangSmith를 버리거나 대체하지 않는다.
- warehouse 전면 재설계는 하지 않는다.
- 기존 팀 DB가 있으면 재사용하고, 없으면 Postgres를 우선한다.
- 배치는 주기적 pull 방식으로 시작한다.

## 4.3 prod 기준 보강 원칙

이번 문서는 “PoC처럼 보이지만 운영에서 안 깨지는 최소안”을 목표로 한다.

그래서 아래 항목은 처음부터 포함한다.

- `run_id` 기준 upsert
- overlap 조회
- repair backfill
- nullable token과 cost
- `scope_type` 분리
- 수집 freshness 확인 패널

## 5. 범위와 제외 범위

## 5.1 이번 단계에서 하는 것

- LangSmith runs를 SDK 또는 API로 조회하는 exporter 설계
- 최소 적재 테이블 설계
- Grafana 공유 dashboard 최소 구성 정의
- env 계약과 운영 절차 정의
- backfill과 중복 방지 기준 정의

## 5.2 이번 단계에서 하지 않는 것

- LangSmith 대체 tracing 시스템 구축
- OTel, Prometheus, warehouse 전면 개편
- 실시간 stream 파이프라인
- 조직 공통 데이터 플랫폼 연동
- ROI 최종 계산 자동화
- 프록시, 브라우저, 인건비를 포함한 총원가 모델링

## 6. 현재 코드 기준 전제

현재 코드에서 이미 확보된 전제는 아래와 같다.

- [langsmith_support.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/langsmith_support.py)
  - `runId`, `traceUrl` 생성 helper가 있다.
- [openai.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/backoffice_copilot/adapters/openai.py)
  - `feature_name`, `agent_step_name`, `environment`, `session_id`, `match_id`, `thread_id`, `owner_team` metadata가 기록된다.
- [effect_evaluator.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/optimizer/effect_evaluator.py)
  - `policy_version`, `metrics_snapshot_id`, `thread_id`, token usage가 기록된다.
- [audit_summarizer.py](/Users/shadowmoon/201-goormgb-ai-1/src/traffic_master_ai/defense/d0_mvp/optimizer/audit_summarizer.py)
  - `audit_summary` run이 `policy_version`, `window_start_ms`, `window_end_ms`와 함께 기록된다.

이 전제를 보면 집계 계층에서 가장 중요한 일은
trace 전체를 다시 해석하는 것이 아니라,
이미 남고 있는 metadata를 안정적으로 꺼내와서 팀이 공유 가능한 형태로 저장하는 것이다.

## 7. 목표 구조

최소 목표 구조는 아래와 같다.

1. TM AI 서비스가 LangSmith에 trace를 기록한다.
2. exporter가 주기적으로 LangSmith runs를 조회한다.
3. exporter가 최소 집계 테이블에 upsert한다.
4. Grafana가 이 테이블을 읽어 팀 공용 화면을 만든다.
5. 상세 디버깅은 `trace_url`을 통해 LangSmith로 이동한다.

구조를 한 줄로 쓰면 아래와 같다.

TM AI runtime
-> LangSmith tracing
-> LangSmith run exporter
-> Postgres aggregate table
-> Grafana shared dashboard

## 8. 데이터 계약

## 8.1 핵심 설계 원칙

- 모든 run이 `session_id`를 가지는 것은 아니다.
- token과 cost는 `0`과 `미수집`을 구분해야 한다.
- 나중 fallback 분석을 위해 raw metadata 일부는 JSON으로 같이 저장한다.

## 8.2 집계 단위

이번 exporter의 집계 단위는 “run 1건 = row 1건”이다.

아직 rollup table을 여러 개 만들지 않는다.
첫 단계는 run-level fact table 1개로 충분하다.

## 8.3 `scope_type` 규칙

세션 중심 경로와 window 중심 경로를 섞지 않기 위해 `scope_type`을 둔다.

- `session`
  - 개별 세션 판단 run
- `window`
  - 운영 window summary run
- `policy`
  - 정책 평가 또는 proposal run
- `job`
  - 세션이나 window보다 큰 배치성 run
- `unknown`
  - 규칙으로 분류 불가한 run

권장 매핑은 아래와 같다.

- `review_session` -> `session`
- `summarize_window` -> `window`
- `evaluate_policy_effect` -> `policy`
- `audit_summary` -> `window`

## 8.4 최소 컬럼

테이블명 예시는 `langsmith_run_metrics`로 둔다.

필수 컬럼:

- `run_id`
- `project_name`
- `run_name`
- `run_type`
- `trace_id`
- `parent_run_id`
- `trace_url`
- `start_time`
- `end_time`
- `latency_ms`
- `status`
- `error_message`
- `scope_type`
- `feature_name`
- `agent_step_name`
- `environment`
- `owner_team`
- `session_id`
- `thread_id`
- `match_id`
- `metrics_snapshot_id`
- `policy_version`
- `model_name`
- `ls_provider`
- `input_tokens`
- `output_tokens`
- `total_tokens`
- `total_cost`
- `metadata_json`
- `usage_json`
- `synced_at`

## 8.5 nullable 규칙

아래 컬럼은 `NULL` 허용이 맞다.

- `session_id`
- `match_id`
- `metrics_snapshot_id`
- `policy_version`
- `input_tokens`
- `output_tokens`
- `total_tokens`
- `total_cost`
- `error_message`

이유는 아래와 같다.

- `summarize_window`, `audit_summary`, `evaluate_policy_effect`는 `session_id`가 비어도 정상이다.
- LangSmith에서 usage가 늦게 계산되거나 제공되지 않는 경우가 있다.
- `0`과 `없음`은 운영 해석이 다르다.

## 8.6 raw 보존 규칙

`metadata_json`과 `usage_json`은 escape hatch 용도다.

원칙:

- dashboard는 가능한 한 정규 컬럼만 본다.
- exporter 변경 없이 새 패널을 급히 만들 수 있게 raw 일부를 남긴다.
- metadata 규칙이 바뀌었을 때 원본 재해석이 가능해야 한다.

## 9. 저장 모델

## 9.1 저장소 우선순위

최소 공수 기준 우선순위는 아래다.

1. 기존 Grafana 연결 Postgres
2. 기존 팀 공용 운영 DB
3. 새 Postgres

이번 단계에서는 ClickHouse를 기본값으로 두지 않는다.

이유:

- 현재 목적은 고속 대용량 분석보다 팀 공유 대시보드다.
- upsert와 운영 단순성이 더 중요하다.
- SQL 기반 Grafana panel 구성이 빠르다.

## 9.2 필요한 테이블

최소 테이블은 2개다.

1. `langsmith_run_metrics`
2. `langsmith_sync_state`

`langsmith_sync_state`는 exporter 상태 기록용이다.

필수 필드 예시:

- `job_name`
- `last_success_at`
- `last_window_start`
- `last_window_end`
- `last_error`

## 9.3 인덱스 최소안

- PK: `run_id`
- index: `start_time`
- index: `(feature_name, start_time)`
- index: `(agent_step_name, start_time)`
- index: `(environment, start_time)`
- index: `(scope_type, start_time)`

## 10. 수집 및 동기화 전략

## 10.1 조회 범위

초기 배치 기준은 아래를 권장한다.

- 5분마다 실행
- 최근 2시간 runs 조회
- `run_type=llm`
- `project_name=tm-ai`
- `run_id` 기준 upsert

## 10.2 overlap 조회를 두는 이유

LangSmith usage 계산이나 run 최종 상태 반영이 지연될 수 있다.
그래서 “직전 5분치만” 읽으면 누락이나 stale row가 생길 수 있다.

이번 최소안에서는 overlap 조회를 기본으로 둔다.

## 10.3 repair backfill

별도 보정 배치를 둔다.

- 하루 1회
- 최근 3일 재조회
- 동일 upsert 규칙 사용

이 배치는 아래 문제를 복구한다.

- 늦게 계산된 token과 cost
- 지연 반영된 error status
- 임시 장애로 건너뛴 수집 구간

## 10.4 exporter 조회 필터

조회 우선 필터는 아래다.

- `project_name='tm-ai'`
- `run_type='llm'`
- 시간 범위 필터

필요 시 2차 필터로 아래를 둔다.

- `environment`
- `feature_name`

## 10.5 token과 cost fallback

exporter는 아래 순서로 읽는다.

1. run top-level usage 또는 cost
2. `outputs.usage_metadata`
3. metadata fallback

원칙:

- 필드가 없으면 `0`으로 덮지 않는다.
- 숫자 변환 불가 시 `NULL`로 저장한다.
- exporter는 해석 실패를 debug log에 남긴다.

## 10.6 trace URL 처리

가능하면 LangSmith가 제공하는 URL을 우선 사용한다.

그래도 아래 env는 exporter에 같이 둔다.

- `LANGSMITH_ENDPOINT`
- `LANGSMITH_WORKSPACE_ID`
- `LANGSMITH_PROJECT`

이유:

- 일부 row에서 `trace_url`이 비어도 fallback 재구성이 가능해야 한다.
- 운영 환경별 base URL 차이를 흡수해야 한다.

## 11. Grafana 대시보드 최소 구성

초기 dashboard는 8개 패널이 적당하다.

1. 일별 총 비용
   - `sum(total_cost)`
2. 일별 총 토큰
   - `sum(total_tokens)`
3. 기능별 총 비용
   - `group by feature_name`
4. 단계별 평균 비용
   - `group by agent_step_name`
5. 에러율
   - `count(status='error') / count(*)`
6. 평균 latency
   - `avg(latency_ms)`
7. 수집 freshness
   - `max(synced_at)` 또는 `last_success_at`
8. 고비용 run table
   - `run_name`, `feature_name`, `total_cost`, `total_tokens`, `trace_url`

이 구성이 필요한 이유는 아래와 같다.

- 비용 추세
- 토큰 추세
- 기능별 분해
- 단계별 이상치
- 실패율
- 속도
- 수집기 생존 여부
- 상세 drill-down

## 12. 구현 작업 묶음

작업은 잘게 10개 이상으로 나누지 않고 아래 6묶음으로 간다.

## 12.1 묶음 1. 계약과 스키마 고정

산출물:

- 계획 문서 확정
- DDL 초안 1개
- exporter env 계약 초안

작업:

- `scope_type` 규칙 고정
- 최소 컬럼과 nullable 규칙 고정
- `langsmith_sync_state` 테이블 필요성 확정
- Postgres 우선 저장 원칙 확정

## 12.2 묶음 2. exporter 뼈대 구현

산출물:

- exporter module 1개
- 얇은 script entrypoint 1개

작업:

- LangSmith client 초기화
- runs 조회
- run row normalize
- dry-run 출력

권장 파일:

- `src/traffic_master_ai/defense/langsmith_exporter.py`
- `scripts/export_langsmith_runs.py`

## 12.3 묶음 3. DB 적재와 upsert 구현

산출물:

- DDL 1개
- upsert SQL 1개
- sync state update 로직

작업:

- `run_id` 기준 upsert
- `synced_at` 기록
- `last_success_at`, `last_error` 갱신
- overlap 조회와 repair backfill entry 분리

## 12.4 묶음 4. 운영 배치와 env 정리

산출물:

- 실행 방법 문서
- env 설명
- 기본 cron 또는 job 실행 예시

작업:

- 5분 배치 기준 문서화
- 1일 repair batch 기준 문서화
- prod 필수 env 목록 정리
- 수집 실패 시 운영 대응 절차 정리

## 12.5 묶음 5. 테스트와 샘플 검증

산출물:

- 단위 테스트
- 수동 검증 체크리스트

작업:

- metadata fallback 테스트
- nullable token과 cost 테스트
- 중복 upsert 테스트
- `scope_type` 분류 테스트
- 샘플 run 10건 LangSmith 대조

## 12.6 묶음 6. Grafana dashboard와 handoff

산출물:

- dashboard 1개
- panel 설명 문서
- 신규 feature metadata 체크리스트

작업:

- 8개 패널 생성
- `trace_url` 링크 확인
- 팀 공유 시나리오 점검
- 신규 feature 추가 규칙 명문화

## 13. 검증 계획

## 13.1 문서 검증

- 38번 문서와 역할이 겹치지 않는지 확인
- 이번 문서는 “LangSmith 이후 Grafana 공유 단계”만 다루는지 확인

## 13.2 코드 검증

- 현재 tracing 경로의 metadata key와 exporter 기대 필드가 맞는지 확인
- `session_id`가 없는 정상 run을 exporter가 깨지지 않고 처리하는지 확인

## 13.3 테스트 검증

- unit test:
  - extractor fallback
  - nullable field 처리
  - scope 분류
  - duplicate upsert
- integration test:
  - 같은 시간 구간 재실행 시 row 수가 불필요하게 증가하지 않는지 확인

## 13.4 수동 검증

아래를 실제로 확인해야 한다.

1. exporter가 최근 run을 가져온다.
2. `review_session`, `summarize_window`, `evaluate_policy_effect`, `audit_summary`가 모두 적재된다.
3. `session`과 `window` run이 같은 방식으로 잘못 뭉치지 않는다.
4. Grafana 집계 수치와 LangSmith 샘플 조회가 해석 가능한 수준으로 맞는다.
5. Grafana에서 `trace_url` 클릭 시 LangSmith 상세로 이동한다.

## 14. 완료 기준

이번 작업은 아래를 만족하면 닫는다.

1. 팀 2명이 같은 Grafana 비용과 토큰 화면을 볼 수 있다.
2. `tm-ai` project의 주요 LLM run이 최소 테이블에 누락 없이 적재된다.
3. run 재조회 시 중복 row가 생기지 않는다.
4. `scope_type` 때문에 session과 window, policy run이 섞여 해석되지 않는다.
5. token과 cost 미수집 row가 `0`이 아니라 `NULL`로 구분된다.
6. 수집 freshness를 확인할 수 있다.
7. Grafana에서 LangSmith 상세로 drill-down 가능하다.

## 15. 리스크와 후속 판단 포인트

## 15.1 immediate risk

- LangSmith run schema는 일부 필드 위치가 다를 수 있다.
- usage와 cost는 지연 계산될 수 있다.
- 새 feature가 metadata 규칙 없이 들어오면 dashboard 품질이 깨진다.

## 15.2 후속 판단 포인트

- 장기적으로는 ClickHouse raw fact와 연결할지 판단이 필요하다.
- `owner_team`, `environment`, `scope_type`는 enum화할지 후속 검토가 필요하다.
- exporter를 script로 둘지 application module + job runner로 둘지 구현 시점에 결정해야 한다.
- dashboard를 직접 SQL panel로 만들지 view를 한 겹 둘지는 DB 운영팀 기준에 맞춰 최종 결정한다.

## 15.3 이번 단계의 결론

지금 단계에서 가장 현실적인 구조는 아래다.

- LangSmith는 그대로 둔다.
- exporter 하나를 추가한다.
- Postgres fact table 1개와 sync state 1개를 둔다.
- Grafana shared dashboard 1개를 만든다.

이 구조가 현재 코드베이스, 현재 tracing 상태, 현재 팀 규모 기준으로
가장 작은 공수로 가장 큰 공유 효과를 낸다.
