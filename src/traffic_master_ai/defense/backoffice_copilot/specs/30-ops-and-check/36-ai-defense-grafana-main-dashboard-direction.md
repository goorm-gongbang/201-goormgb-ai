# Backoffice Copilot Grafana + Discord Direction

## 핵심 정리

- 이 문서의 대상은 `Backoffice Copilot` 전용 보드와 Discord webhook이다.
- AI Defense 메인 파이프라인 모니터링은 다른 대시보드에서 본다.
- 새 DB 테이블이나 새 앱 작업은 전제하지 않는다.
- Grafana는 기존 저장소 `post_review_runs`, `post_review_session_results`를 읽는 결과 보드로 구성한다.
- ClickHouse `defense_post_review_candidates_v1`, `defense_session_rollups`는 enrichment로만 쓴다.
- Discord는 `POST_REVIEW_SUSPICIOUS`, `POST_REVIEW_DELIVERY_FAILED` 2종만 보낸다.

## Grafana 방향

Grafana는 운영자가 아래 4가지를 바로 볼 수 있으면 충분하다.

1. 이번 window에서 몇 건을 검토했고 몇 건을 `SUSPICIOUS`로 봤는가
2. 지금 어떤 경기와 세션을 먼저 봐야 하는가
3. suspicious 결과가 backend로 정상 전달됐는가
4. raw fallback이나 run 실패가 늘고 있는가

상단 KPI:

- post-review run 수
- `candidate_count`
- `suspicious_count`
- suspicious rate
- delivery failed 수
- raw fallback rate

필수 패널:

- `candidate_count` trend
- `suspicious_count` trend
- run status breakdown
  - `SUCCESS / PARTIAL_SUCCESS / FAILED`
- `review_result` breakdown
  - `NORMAL / SUSPICIOUS`
- `backend_delivery_status` breakdown
  - `PENDING / SENT / FAILED`
- delivery failed trend
- raw fallback rate trend
- top suspicious_signals

있으면 좋은 패널:

- 최근 suspicious 경기 목록
- 최근 suspicious 세션 목록
- failed delivery 세션 목록
- `latest_action`, `latest_risk_tier`, `latest_reason_code` 보강 패널

메모:

- 상세 table panel은 필수는 아니다.
- 보여지는 양이 너무 적어 보이면 최근 경기/세션 목록 패널을 추가하는 정도면 충분하다.
- 새 저장소를 만드는 방식이 아니라, 기존 PostgreSQL/ClickHouse를 읽는 패널만 구성한다.

## Discord webhook 방향

Discord는 raw schema dump가 아니라
운영자가 한눈에 보는 `운영 메시지` 형태로 보낸다.

### 표시 규칙

Discord 본문에서는 DB 컬럼명을 그대로 쓰지 않는다.

권장 표시명:

| 내부 필드 | Discord 표시명 |
| --- | --- |
| `match_id` | 경기 ID |
| `window_start_ms`, `window_end_ms` | 분석 구간 |
| `candidate_count` | 검토 세션 수 |
| `suspicious_count` | 의심 세션 수 |
| `summary_text_json` | 요약 |
| `session_id` | 세션 ID |
| `review_result` | 판정 |
| `evidence_summary` | 판단 근거 |
| `backend_delivery_status` | 전달 상태 |
| `latest_action` | 최근 액션 |
| `latest_risk_tier` | 최근 위험 단계 |
| `latest_reason_code` | 최근 사유 코드 |

추가 규칙:

- `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`는 운영자가 읽기 쉬운 한글 상태로 바꿔 보여준다.
- `PENDING`, `SENT`, `FAILED`도 그대로 노출하지 말고 전달 대기, 전달 완료, 전달 실패처럼 바꾼다.
- `summary_text_json`은 배열 원문이 아니라 2~3줄 bullet 요약으로 렌더링한다.
- `backend_delivery_status='FAILED'` 같은 조건식 표현은 메시지에 넣지 않는다.

### `POST_REVIEW_SUSPICIOUS`

트리거:

- `post_review_runs.status IN ('SUCCESS', 'PARTIAL_SUCCESS')`
- `post_review_runs.suspicious_count > 0`

필수 내용:

- 경기 ID
- 분석 구간
- 검토 세션 수
- 의심 세션 수
- 요약 2~3줄
- 우선 확인할 세션 상위 3개
- 각 세션의 판단 근거
- 각 세션의 전달 상태

권장 enrichment:

- 최근 액션
- 최근 위험 단계
- 최근 사유 코드

원칙:

- suspicious가 `0`이면 보내지 않는다.
- digest성 요약 메시지는 보내지 않는다.

### `POST_REVIEW_DELIVERY_FAILED`

트리거:

- `post_review_session_results.review_result = 'SUSPICIOUS'`
- `post_review_session_results.backend_delivery_status = 'FAILED'`

필수 내용:

- 경기 ID
- 분석 구간
- 실패한 세션 ID
- 판단 근거
- 전달 실패 표시

권장 enrichment:

- 최근 액션
- 최근 위험 단계
- 최근 사유 코드

원칙:

- retry 또는 수동 전달 판단용 알림으로 본다.
- dedupe 기준은 `match_id + session_id + backend_delivery_status`로 둔다.

## Discord 출력 템플릿

### 템플릿 1. Suspicious 결과 발생

```text
[Backoffice Copilot] 의심 세션 발견

- 경기 ID: {match_id}
- 분석 구간: {window_start_ms} ~ {window_end_ms}
- 검토 세션 수: {candidate_count}
- 의심 세션 수: {suspicious_count}
- 실행 상태: {run_status_kr}

[요약]
- {summary_line_1}
- {summary_line_2}
- {summary_line_3}

[우선 확인 세션]
1) 세션 ID: {session_id_1}
   - 판단 근거: {evidence_summary_1}
   - 전달 상태: {delivery_status_kr_1}
   - 최근 액션: {latest_action_1}
   - 최근 위험 단계: {latest_risk_tier_1}

2) 세션 ID: {session_id_2}
   - 판단 근거: {evidence_summary_2}
   - 전달 상태: {delivery_status_kr_2}
   - 최근 액션: {latest_action_2}
   - 최근 위험 단계: {latest_risk_tier_2}

3) 세션 ID: {session_id_3}
   - 판단 근거: {evidence_summary_3}
   - 전달 상태: {delivery_status_kr_3}
   - 최근 액션: {latest_action_3}
   - 최근 위험 단계: {latest_risk_tier_3}
```

### 템플릿 2. Backend 전달 실패

```text
[Backoffice Copilot] 전달 실패

- 경기 ID: {match_id}
- 분석 구간: {window_start_ms} ~ {window_end_ms}
- 세션 ID: {session_id}
- 전달 상태: 전달 실패

[판단 근거]
- {evidence_summary}

[보강 정보]
- 최근 액션: {latest_action}
- 최근 위험 단계: {latest_risk_tier}
- 최근 사유 코드: {latest_reason_code}
```

메모:

- 템플릿은 운영 전달용 메시지다.
- JSON, 배열, enum 원문을 그대로 노출하지 않는다.
- 사람이 바로 읽는 문장과 bullet 위주로 정리한다.

## 데이터 기준

- Grafana authority: PostgreSQL `post_review_*`
- Grafana enrichment: ClickHouse read model
- Discord authority: PostgreSQL `post_review_*`
- Discord enrichment: ClickHouse read model
- run 식별 기준: `match_id`
- 세션 보강 조회 기준: `session_id + window_start_ms + window_end_ms`

중요:

- ClickHouse enrichment가 실패해도 Discord 본문은 보내야 한다.
- PostgreSQL 결과 조회가 실패하면 Discord 알림을 만들면 안 된다.

## 이번 범위에서 빼는 것

- Blind Spot Recall
- Post-Review FPR
- Precision
- confusion matrix
- `Top-3 Pattern Coverage`

이유:

- Recall / FPR / Precision은 truth label authority가 필요하다.
- `Top-3 Pattern Coverage`는 정식 `pattern_code`가 필요하다.
- 지금 저장 계약은 운영용 post-review 결과 저장소이지 평가용 label store가 아니다.

## 최종 요청 사항

1. Backoffice Copilot 전용 Grafana 결과 보드를 따로 구성한다.
2. Grafana 기본 패널은 `candidate_count`, `suspicious_count`, suspicious rate, run status, `review_result`, `backend_delivery_status`, raw fallback 중심으로 둔다.
3. ClickHouse는 `latest_action`, `latest_risk_tier`, `latest_reason_code` enrichment로만 붙인다.
4. Discord webhook은 `POST_REVIEW_SUSPICIOUS`, `POST_REVIEW_DELIVERY_FAILED` 2종만 보낸다.
5. Discord 본문은 schema field를 그대로 노출하지 말고 운영자용 표시명으로 변환해 보낸다.
6. 라벨 데이터가 필요한 KPI는 이번 보드와 webhook에서 제외한다.

한 줄 결론:

V1은 `Backoffice Copilot 전용 결과 보드 + 정돈된 Discord webhook`으로 가는 것이 맞다.
