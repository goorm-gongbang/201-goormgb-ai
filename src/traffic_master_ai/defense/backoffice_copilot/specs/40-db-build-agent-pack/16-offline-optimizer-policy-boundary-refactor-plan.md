# Offline Optimizer Policy Boundary Refactor Plan

## 목차

1. 한 줄 결정
2. 이번 리팩토링의 목적
3. 현재 문제
4. 경계 재정의
5. 목표 상태
6. 수정 대상 파일
7. 단계별 리팩토링 계획
8. 검증 계획
9. 완료 기준
10. 남은 판단 포인트

## 1. 한 줄 결정

Offline optimizer는 방어 강도와 민감도만 조정하고,
`challenge.*` 계열은 사용자 체감 플로우 보호를 위해 조정 대상에서 제외한다.

## 2. 이번 리팩토링의 목적

- optimizer 허용 범위를 제품 의도와 맞게 다시 고정한다.
- `challenge.*` 변경 가능성이 프롬프트, validator, rule-based proposal, SSOT에서 동시에 열려 있는 상태를 정리한다.
- “기술적으로 허용되지만 제품적으로 금지”인 상태를 제거한다.
- 이후 운영자가 proposal을 검토할 때 UX 정책과 탐지 민감도 정책을 구분해서 볼 수 있게 만든다.

## 3. 현재 문제

현재 구조는 아래 이유로 경계가 섞여 있다.

- `effect_evaluator.py` 프롬프트가 `challenge.max_attempts`, `challenge.cooldown_ms.*`, `challenge.halt_seconds`를 변경 가능 path로 안내한다.
- `validator.py`도 같은 path를 allowlist에 포함한다.
- rule-based proposal도 `challenge.halt_seconds`를 직접 변경할 수 있다.
- 정책 최적화 SSOT도 `challenge.*`를 “튜닝 가능한 path”로 열어두고 있다.

이 구조의 문제는 아래와 같다.

- optimizer가 탐지 성능 지표만 보고 챌린지 UX를 바꿀 수 있다.
- challenge는 티켓팅 핵심 플로우인데, offline proposal에서 조정되면 운영 의도와 제품 경험이 어긋날 수 있다.
- validator range check는 기술적 안전장치일 뿐이고, UX 의도 보호 장치는 아니다.

## 4. 경계 재정의

## 4.1 optimizer가 건드려도 되는 것

- `risk.alpha`
- `tier.thresholds.T0_max`
- `tier.thresholds.T1_max`
- `tier.thresholds.T2_max`
- `tier.hysteresis.margin`
- `planner.throttle_delay_ms.T1`
- `planner.throttle_delay_ms.T2`

성격:

- 방어 강도
- 탐지 민감도
- 티어 분포 조정
- throttle 체감의 범위 내 조정

## 4.2 optimizer가 건드리면 안 되는 것

- `challenge.max_attempts`
- `challenge.cooldown_ms.first`
- `challenge.cooldown_ms.second`
- `challenge.halt_seconds`

성격:

- 사용자 체감 플로우
- 예매 시작 이후 공통 challenge 경험
- 실패 후 재시도 구조
- 일시 정지 정책

## 4.3 해석 규칙

- `challenge.*`는 optimizer 입력에서 관측 대상일 수는 있다.
- 하지만 optimizer 출력 path에는 포함되면 안 된다.
- challenge 정책 변경은 별도 제품/운영 승인 task로만 다룬다.

## 5. 목표 상태

리팩토링 후 목표 상태는 아래와 같다.

1. `effect_evaluator.py` 프롬프트에서 `challenge.*`가 제거된다.
2. `validator.py` allowlist, baseline, bounds에서 `challenge.*`가 제거된다.
3. rule-based proposal이 challenge 값을 수정하지 않는다.
4. policy optimization SSOT에서 optimizer tuning path와 product-owned path가 분리된다.
5. 테스트가 “challenge path proposal은 거부된다”를 잠근다.

## 6. 수정 대상 파일

이번 경계 정리에 직접 관련된 파일은 아래다.

- `src/traffic_master_ai/defense/d0_mvp/optimizer/effect_evaluator.py`
- `src/traffic_master_ai/defense/d0_mvp/optimizer/validator.py`
- `src/traffic_master_ai/defense/d0_mvp/ssot_specs/L2/obs_opt/defense_policy_optimization_ssot.yaml`
- `src/traffic_master_ai/defense/d0_mvp/ssot_specs/L1/llm/defense_llm_ssot.yaml`
- 관련 테스트 파일
  - `tests/defense/test_effect_evaluator_openai.py`
  - validator / optimizer 관련 테스트가 있으면 함께 보강

검토 대상이지만 이번 리팩토링에서 직접 수정 여부를 따로 판단할 파일:

- `src/traffic_master_ai/defense/d0_mvp/policy/snapshot.py`
- `src/traffic_master_ai/defense/d0_mvp/policy/loader.py`
- `src/traffic_master_ai/defense/d0_mvp/optimizer/pipeline.py`

이 파일들은 challenge 값을 런타임 정책으로 보유하지만,
이번 리팩토링의 핵심은 “optimizer가 제안할 수 있느냐”를 닫는 것이므로 직접 수정이 꼭 필요하지 않을 수 있다.

## 7. 단계별 리팩토링 계획

## 7.1 1단계. 정책 경계 문서 고정

- L2 optimization SSOT에서 path를 두 그룹으로 분리한다.
- `optimizer_tunable_paths`와 `product_locked_paths` 같은 식으로 문서 의미를 명확히 한다.
- challenge는 “관측은 가능, optimizer 조정은 불가”라고 적는다.

산출물:

- 문서 기준으로 “왜 challenge는 제외되는가”가 명시된 상태

## 7.2 2단계. LLM 제안 surface 축소

- `effect_evaluator.py` 프롬프트에서 `challenge.*` 항목을 제거한다.
- allowlist 설명도 새 경계에 맞게 줄인다.
- “제품 고정 정책을 바꾸지 말라”는 규칙을 프롬프트에 넣는다.

산출물:

- LLM이 challenge path를 자연스럽게 제안하지 않는 상태

## 7.3 3단계. validator 계약 축소

- `_ALLOWED_PATHS`에서 `challenge.*` 제거
- `_INTEGER_PATHS`에서 `challenge.*` 제거
- `_BASELINE_VALUES`, `_NUMERIC_BOUNDS`에서 `challenge.*` 제거
- 관련 constraint 중 challenge 전용 규칙은 validator에서 제거하거나 별도 product policy validator로 이동할지 판단

산출물:

- challenge patch는 구조적으로 통과 불가한 상태

## 7.4 4단계. rule-based proposal 정리

- `_rule_based_proposal()`에서 `challenge.halt_seconds` 조정 제거
- rule-based proposal은 `risk/tier/throttle` 안에서만 제안하도록 축소

산출물:

- LLM이든 rule-based든 challenge 변경 proposal이 나오지 않는 상태

## 7.5 5단계. 테스트 잠금

- challenge path가 proposal에 들어오면 validator가 reject하는 테스트 추가
- effect evaluator prompt surface가 새 allowlist와 맞는지 검증
- 기존 proposal 성공 케이스가 challenge path 없이도 유지되는지 검증

산출물:

- 경계 회귀를 막는 테스트

## 7.6 6단계. 후속 운영 문서 정리

- task log에 경계 변경 이유와 검증 결과 기록
- 필요하면 운영 문서에 “challenge 정책은 optimizer 비대상” 원칙을 1줄로 추가

산출물:

- 코드와 문서가 같은 경계를 말하는 상태

## 8. 검증 계획

- 문서 검증
  - optimization SSOT와 LLM SSOT가 같은 허용 범위를 말하는지 확인
- 코드 검증
  - `rg`로 `challenge.max_attempts`, `challenge.cooldown_ms`, `challenge.halt_seconds`가 optimizer allowlist에 남아 있는지 확인
- 테스트 검증
  - validator 단위 테스트
  - effect evaluator / optimizer 관련 단위 테스트

핵심 확인 질문:

1. optimizer proposal에 `challenge.*`가 들어갈 수 있는가
2. 들어가면 validator가 막는가
3. rule-based proposal도 challenge를 건드리지 않는가
4. 문서와 코드가 같은 경계를 말하는가

## 9. 완료 기준

- challenge 관련 path가 optimizer 허용 범위에서 제거된다.
- effect evaluator 프롬프트, validator, rule-based proposal, SSOT가 같은 경계를 사용한다.
- challenge path proposal reject 테스트가 추가된다.
- 문서만 보면 “무엇이 optimizer 대상이고 무엇이 아닌지” 바로 알 수 있다.

## 10. 남은 판단 포인트

- `risk.probation_seconds`는 허용 범위에 남길지 별도 검토가 필요하다.
  - 방어 민감도 계열로 볼 수 있지만, 사용자 체감 흐름에 일부 영향이 있다.
- `planner.throttle_delay_ms.*`도 제품 체감이 있으므로, 추후 필요하면 “optimizer 허용 but tighter bound”로 다시 나눌 수 있다.
- 장기적으로는 optimizer path를 코드 상수와 SSOT 한 곳에서 동시에 생성하는 구조가 더 안전하다.
