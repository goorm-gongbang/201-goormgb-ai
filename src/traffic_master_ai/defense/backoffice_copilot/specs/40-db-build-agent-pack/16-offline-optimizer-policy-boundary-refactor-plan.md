# Offline Optimizer Policy Boundary Work Log

## 목차

1. 목적
2. 현재 상태
3. 작업 로그
4. 위험 지점
5. 다음 작업

## 1. 목적

이 파일은 legacy defense 코드 수정과 offline optimizer 경계 수정의 작업 로그를 남기는 용도로 사용한다.

## 2. 현재 상태

- offline optimizer 코드 경계 수정은 반영됨
- L1/L2 SSOT 문서도 optimizer 허용 범위 기준으로 다시 맞춤
- admin console 제거 완료
- legacy action `CHALLENGE`와 legacy flow state `S*`는 backoffice ingest에서 정규화됨
- runtime Redis `flow_state`는 API 레이어 기준 `F*`로 저장되도록 수정 중이며, 이번 로그에 반영 내용과 위험 지점을 남김

## 3. 작업 로그

### 2026-04-10

- `fix/runtime-scoring-unification-devbase`의 `fix: persist runtime scoring across shortcut paths`를 `chore/legacy-defense-cleanup`에 통합
- `src/traffic_master_ai/defense/api/main.py`에서 soft action shortcut 이전에도 D0 evaluate를 먼저 실행해 `risk_score`, `defense_tier`, `last_step_risk`, `last_guard_ts_ms`가 runtime snapshot과 Redis state에 반영되도록 정리
- `src/traffic_master_ai/defense/api/models.py`에 `last_step_risk`, `last_guard_ts_ms` 노출 유지
- `tests/defense/test_defense_api_evaluate_contract.py`, `tests/defense/test_defense_api_challenge.py`를 legacy cleanup의 `F*` runtime state 기준과 runtime scoring persistence 기준이 함께 성립하도록 통합
- dev 운영 해석 메모: Grafana `THROTTLE`는 ClickHouse audit action 집계이고, Redis 관측은 `tm:sess:*` 또는 `tm:decision-state:session:*` 키를 직접 보는 경로라서 두 값이 바로 같다고 가정하면 안 됨
- dev Helm 값 기준 AI image tag는 아직 `a16e08e`라서, 클러스터가 이 수정 커밋을 실제로 배포받지 않았을 수 있음

### 2026-04-09

- `src/traffic_master_ai/defense/d0_mvp/api/admin_console.py` 제거
- `src/traffic_master_ai/defense/d0_mvp/api/app.py`에서 admin console 연결 제거
- `src/traffic_master_ai/defense/d0_mvp/optimizer/effect_evaluator.py`에서 `challenge.*` 제안 surface 제거
- `src/traffic_master_ai/defense/d0_mvp/optimizer/validator.py`에서 `challenge.*` allowlist, baseline, bounds 제거
- `src/traffic_master_ai/defense/d0_mvp/optimizer/pipeline.py`에서 `challenge.*` path 해석 제거
- `tests/defense/test_offline_optimizer_policy_boundary.py` 추가로 challenge path 거부 회귀 잠금
- `src/traffic_master_ai/defense/d0_mvp/ssot_specs/L1/llm/defense_llm_ssot.yaml`에서 `challenge.*`를 allowed path에서 제거하고 product-owned path로 이동
- `src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_policy_optimization_ssot.yaml`에서 optimizer tunable path와 product locked path를 분리
- `src/traffic_master_ai/defense/backoffice_copilot/legacy_normalization.py` 추가
- `src/traffic_master_ai/defense/backoffice_copilot/ingest/semantic_mapping.py`와 `src/traffic_master_ai/defense/backoffice_copilot/storage/clickhouse_ingest.py`에서 legacy `S*`/`CHALLENGE` 입력 정규화 반영
- `src/traffic_master_ai/defense/api/runtime_flow_state.py` 추가
- `src/traffic_master_ai/defense/api/models.py`에서 runtime flow state 입력을 `F*` 기준으로 정규화하도록 수정
- `src/traffic_master_ai/defense/api/main.py`에서 target event 기준 flow state를 `F1/F2/F3R/F3M/F4R/F4M`로 저장하도록 수정
- `src/traffic_master_ai/defense/api/challenge_runtime.py`에서 challenge pass 시 임의 `S4` 승격을 제거하고 현재 `F*` 상태를 유지하도록 수정
- `src/traffic_master_ai/defense/api/main.py`에서 `d0_mvp` 호출 직전에는 `F* -> S*` 변환, 결과를 runtime/audit로 기록할 때는 `S* -> F*` 역변환하도록 수정
- `tests/defense/test_canonical_audit_contract.py`
- `tests/defense/test_defense_api_policy.py`
- `tests/defense/test_defense_api_evaluate_contract.py`
- `tests/defense/test_defense_api_challenge.py`
  - runtime/audit expectation을 `F*` 기준으로 수정

## 4. 위험 지점

- `d0_mvp` 내부 상태기계는 아직 `S*` enum을 직접 사용한다. 이번 수정은 API/Redis/audit 경계만 `F*`로 바꾼 것이고, 내부 엔진은 변환 어댑터에 의존한다.
- `d0_mvp` 결과를 `F*`로 되돌릴 때 `S4 -> F3`, `S5 -> F4`처럼 generic 상태로만 복원되는 경우가 있다. 추천 모드와 일반 모드 구분이 필요한 순간에는 `F3R/F3M`, `F4R/F4M`이 아니라 `F3/F4`로 남을 수 있다.
- 외부 호출자가 아직 `S*`를 보내는 경우는 이번 수정에서 허용하고 내부에서 `F*`로 정규화한다. 호출자 수정이 늦어도 깨지지는 않지만, 완전한 계약 통일은 아직 아니다.
- `pytest`가 없는 환경에서는 전체 테스트를 바로 돌릴 수 없다. 최소 검증은 `compileall`과 부분 smoke로만 확인한다.

## 5. 다음 작업

- `d0_mvp` 내부 state machine 자체를 `F*` 기준으로 바꿀지 별도 task로 분리해서 판단
- `S4/S5`에서 recommendation/manual 모드를 잃는 지점을 줄이기 위해 runtime state에 mode 힌트를 추가할지 검토
- 브랜치 정리 후 `chore/legacy-defense-cleanup`를 `origin/dev` 기준 단일 작업 커밋 체인으로 force-push
