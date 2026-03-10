# Configurability Policy (Bundle-wide)

목적: 팀 간 협업 시 "무엇이 고정 계약이고, 무엇이 운영 중 바뀔 수 있는지"를 명확히 구분한다.

## 1) 고정 계약(Fixed Contract)

아래 항목은 변경 시 버전업(SSOT/OpenAPI)과 공지 후 반영한다.

- API request/response 필드명과 타입
- 상태/이벤트/ReasonCode enum 명칭
- 보안 헤더 키 이름
- Selector 계약 키 의미
- Idempotency/Atomicity 같은 불변 규칙

## 2) 운영 가변값(Tunable Runtime Policy)

아래 항목은 ENV/정책 스냅샷으로 조정 가능하다.

- Risk threshold, challenge fail limit, repetitive limit
- TTL, timeout, throttle delay, budget
- service host/port/path prefix
- challenge type/difficulty/삽입 비율
- telemetry feature 승격(Core/Shadow) 기준

## 3) 변경 절차

1. Tunable 변경
- 정책/ENV 변경
- `policy_version` 증가
- A/B 또는 전후 비교 로그 검증

2. Fixed 변경
- SSOT/OpenAPI/연동 문서 동시 변경
- breaking change면 major version 증가
- FE/BE/Cloud 공지 후 배포

## 4) 기본 운영 원칙

- 문서의 숫자는 baseline 예시다.
- baseline을 절대값으로 취급하지 않는다.
- 관측 데이터(decision audit, telemetry, VQA outcome)를 근거로 조정한다.
