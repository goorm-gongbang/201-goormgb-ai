# Canonical Audit Minimum Contract

## 목차

1. 목적
2. 최종 row shape
3. 필수 필드
4. optional typed 필드
5. `raw_payload` 보존 규칙
6. ETL / Backoffice 적용 규칙
7. 남은 gap

## 1. 목적

이 문서는 `decision_audit` raw row의 canonical contract를 하나로 고정한다.

이제 canonical audit row는

- flat top-level
- `snake_case`
- 고정 typed field + `raw_payload`

형태만 허용한다.

`audit.py`, `d0_mvp/api/runtime.py`, `clickhouse_ingest.py`, `backoffice_copilot/ingest/loader.py`는 이 계약을 기준으로 정렬한다.

## 2. 최종 row shape

```json
{
  "ts_ms": 1710000000000,
  "session_id": "sess-1",
  "event_type": "DEF_ORCH_EXECUTED",
  "trace_id": "trace-1",
  "request_id": "req-1",
  "correlation_id": "corr-1",
  "challenge_id": "challenge-1",
  "flow_state": "S3",
  "risk_tier": "T2",
  "action": "THROTTLE",
  "reason_code": "RULE_HIT",
  "policy_version": "policy-v1",
  "raw_payload": {
    "result": {
      "status": "OK",
      "http_status": 200
    },
    "request_meta": {
      "test_mode": true
    }
  }
}
```

규칙:

- top-level에 nested `camelCase` 계약을 두지 않는다.
- event-specific detail은 `raw_payload` 안에만 둔다.
- `raw_payload`도 JSON object여야 한다.
- top-level unknown field는 허용하지 않는다.

## 3. 필수 필드

| field | 설명 |
| --- | --- |
| `ts_ms` | epoch milliseconds. non-negative int |
| `session_id` | 현재 기준 기본 운영 join key |
| `event_type` | audit event taxonomy 값 |
| `raw_payload` | typed field 외 나머지 detail object |

## 4. optional typed 필드

| field | 설명 |
| --- | --- |
| `trace_id` | request / drill-down 식별자 |
| `request_id` | request 단위 식별자. 없으면 생략 가능 |
| `correlation_id` | 상위 request correlation 식별자 |
| `challenge_id` | challenge 계열 이벤트 식별자 |
| `flow_state` | 당시 flow 상태 |
| `risk_tier` | 정규화된 tier 값. `defense_tier`를 쓰지 않는다 |
| `action` | 정규화된 action 값 |
| `reason_code` | 결과 또는 decision reason |
| `policy_version` | 선택된 policy version |

메모:

- optional 필드는 present 시 non-empty string이어야 한다.
- `defense_tier`는 canonical field가 아니며 `risk_tier`로 통일한다.

## 5. `raw_payload` 보존 규칙

원칙:

- typed field로 승격하지 않은 값은 모두 `raw_payload`로 보존한다.
- ClickHouse `raw_payload_json`은 row 전체가 아니라 `raw_payload`만 serialize 한다.
- typed field를 `raw_payload`에 중복 저장하지 않는다.

대표 예시:

- `audit.py` evaluate row
  - `decision_id`
  - `risk_score`
  - `rule_hits`
  - `path`
  - `method`
  - `allow`
  - `runtime_state`
  - `telemetry_features`
- `runtime.py` D0 audit row
  - `request_meta`
  - `server_decision`
  - `result`
  - `dedup`
  - `throttle`
  - `block`
  - `challenge`
  - `turnstile`
  - `guard`
  - `analyzer`
  - `planner`
  - `orchestrator`
- challenge/VQA row
  - `match_id`
  - `feature_summary`
  - `reason_codes`
  - `vqa_attempt_score`

## 6. ETL / Backoffice 적용 규칙

`clickhouse_ingest.py`

- canonical contract만 받는다.
- legacy `defense_tier` / nested `serverDecision` / top-level `payload` 추측 변환을 하지 않는다.
- typed field는 top-level에서만 읽는다.
- `raw_payload_json`은 `raw_payload`만 직렬화한다.

`backoffice_copilot/ingest/loader.py`

- canonical row를 기본 입력으로 읽는다.
- legacy fixture/과거 row는 compatibility로만 허용한다.
- semantic mapping은 top-level typed field + `raw_payload`를 함께 본다.

기본 join guidance:

- 현재 기본 join은 `session_id + 시간 구간`
- `match_id`는 아직 canonical top-level 필드가 아니다

## 7. 남은 gap

- `match_id`, `http_status`, `dedup_is_duplicate`, rollout field는 아직 top-level typed field로 승격되지 않았다.
- event taxonomy 자체는 아직 `EVALUATE` / `CHALLENGE_VERIFIED` / D0 runtime catalog가 공존한다.
- `AuditWarehouse`는 local compatibility adapter라 canonical raw log와 별도의 과도기 계층이 남아 있다.
