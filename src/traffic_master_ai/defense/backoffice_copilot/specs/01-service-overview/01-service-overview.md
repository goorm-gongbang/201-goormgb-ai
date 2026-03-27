## 1. 문서 목적

이 문서는 Backoffice Copilot의 서비스 범위, 사용자, 입력/출력, 핵심 기능, 처리 흐름을 정의한다.

이 문서의 목적은 다음과 같다.

- 서비스의 전체 기능 범위를 고정한다.
- 사후 판단이 어떤 흐름을 대상으로 하는지 정의한다.
- 상태 인덱스(F 기준)를 기준으로 사후 판단 대상을 명확히 한다.
- 이후 도메인 문서와 구현 문서의 기준이 되는 제품 정의를 제공한다.

이 문서는 제품 정의 문서이며, 하위 문서는 이 문서를 기반으로 작성된다.

---

## 2. 서비스 한 줄 정의

Backoffice Copilot은 Runtime이 정상 통과시킨 세션 중,

지정 시간 구간 종료 후 다시 볼 가치가 있는 세션을 사후 판단하여

세션별 결과와 시간 구간 요약을 생성하는 로그 기반 분석 시스템이다.

---

## 3. 서비스 목표

이 서비스의 목표는 다음과 같다.

1. Runtime이 놓칠 수 있는 회색 지대 세션을 사후 판단한다.
2. 지정 시간 구간 단위로 특이사항을 요약한다.
3. 결과를 PostgreSQL에 먼저 저장하고, 필요 시 운영자가 후속 검토할 export를 만든다.

이 서비스는 다음을 목표로 하지 않는다.

- 실시간 방어 대체
- 제재 집행
- 정책 자동 반영
- 운영 UI 제공
- 외부 backend 서버/API 구현
- Discord/Grafana 실제 연결

---

## 4. 사용자

이 서비스의 직접 사용자는 AI 팀 개발자다.

이 서비스의 간접 사용자는 아래와 같다.

- 운영자: DB 저장 이후 생성된 suspicious export와 요약 결과를 후속 검토에 사용
- 인프라 팀: backend adapter가 넘긴 payload를 소비
- 다른 개발 파트: DB row 또는 export 결과를 참고

---

## 5. 상태 인덱스 정의

이 서비스는 기존 S 기반 상태가 아니라 아래 F 기준 티켓팅 상태 인덱스를 사용한다.

| 상태 인덱스 | Critical API | 추천 모드 | 의미 |
| --- | --- | --- | --- |
| `F0` | 없음 (초기) | 공통 | 대기열 진입 전 초기 상태 |
| `F1` | `POST /queue/matches/{matchId}/enter` | 공통 | 대기열 진입 + 예매 조건 저장 완료 |
| `F2` | `GET /seat/matches/{matchId}/seat-groups` | 공통 | 좌석 도메인 진입 + 추천 ON/OFF 확정 |
| `F3R` | `GET /seat/matches/{matchId}/recommendations/blocks` | ON | 추천 블록 리스트 조회 완료 |
| `F3M` | `GET /seat/matches/{matchId}/sections/{sectionId}/blocks` | OFF | 일반 구역/블록 조회 완료 |
| `F4R` | `POST /seat/matches/{matchId}/recommendations/blocks/{blockId}/assign` | ON | 추천 모드 자동 배정(+hold) 요청 완료 |
| `F4M` | `POST /seat/matches/{matchId}/seat-holds` | OFF | 일반 모드 좌석 hold 요청 완료 |
| `FX` | 없음 (종료) | 공통 | 결제 진입/이탈/만료/차단 등 종료 상태 |

---

## 6. Runtime 관련 전제

이 서비스는 Runtime의 기존 사후 방어용 VQA 재검증 로직을 전제로 하지 않는다.

즉 아래 로직은 제거된 상태를 전제로 한다.

- Tier 상승
- 중간 VQA 재검증 트리거
- 검증 결과에 따른 재진입 흐름

이 서비스는 아래 전제를 따른다.

1. Runtime은 실시간 판단만 수행한다.
2. Tier 상승이 발생하더라도 중간 VQA를 다시 띄우지 않는다.
3. 실시간에 정상 통과한 세션은 그대로 플로우를 진행한다.
4. 사후 판단은 종료 후 별도 계층에서 수행한다.

---

## 7. 사후 판단 대상

사후 판단 대상은 아래 조건을 모두 만족하는 세션이다.

1. `session_id`가 존재한다.
2. 지정 시간 구간 내 활동 기록이 존재한다.
3. Runtime에서 최종 차단되지 않았다.
4. Runtime 중 `T1` 또는 `T2` 흔적이 존재한다.

세부 후보 추출 hard filter와 `latest_*`, `terminal_outcome` 해석 규칙은 `10-post-review-rules.md`와 `21-data-contract.md`를 따른다.  
F 상태 인덱스는 도메인 해석 보조 모델이며, 상위 문서에서 별도 hard filter로 승격하지 않는다.

제외 대상은 아래와 같다.

1. Runtime에서 이미 `T3` 또는 최종 차단 처리된 세션
2. `session_id`가 없어 흐름 추적이 불가능한 요청
3. 의심 흔적이 거의 없는 일반 정상 세션

---

## 8. 입력

입력 소스는 아래 두 가지다.

1. `defense_audit_events.jsonl`
2. `decision_audit.jsonl`

입력 우선순위는 아래와 같다.

1. `defense_audit_events.jsonl`
2. `decision_audit.jsonl`

입력은 항상 지정 시간 구간 기준으로 필터링한다.

row loader는 원시 row를 읽는 책임만 가지며, `flowState`, `terminalReason`, `reasonCode`, `latest_*` 해석은 semantic mapping 계층 책임이다.

---

## 9. 출력

정식 출력은 아래 PostgreSQL 2개 테이블이다.

1. `post_review_runs`
2. `post_review_session_results`

export 파일은 DB 저장 이후 후속 산출물이다.

1. `summary.json`
2. `suspicious_sessions.jsonl`
3. `suspicious_sessions.csv`

### 세션 단위 최소 출력 필드

- `session_id`
- `review_result`
- `evidence_summary`

### 시간 구간 단위 최소 출력 필드

- `summary_text`
- `suspicious_sessions[]`

허용 레이블:

- `NORMAL`
- `SUSPICIOUS`

---

## 10. 핵심 처리 흐름

이 서비스의 처리 흐름은 아래와 같다.

1. 지정 시간 구간 입력
2. 로그 수집
3. 후보 세션 추출
4. 세션 흐름 및 의심 신호 분석
5. 세션별 사후 판단
6. 시간 구간 요약 생성
7. PostgreSQL 저장
8. 필요 시 export 후속 생성

---

## 11. 최종 산출물 사용 방식

### `summary.json`

- DB 저장 이후 생성되는 시간 구간 전체 특이사항 요약
- DB 기준 suspicious 세션 수 요약
- 운영자/인프라팀 참고용

### `suspicious_sessions.jsonl`

- DB row를 변환한 기계 처리용 suspicious 세션 원본
- 후속 자동 처리 또는 추가 파이프라인 입력용

### `suspicious_sessions.csv`

- DB row를 변환한 운영자 확인용 포맷
- 후속 연락/수동 검토용

---

## 12. 비범위

이 서비스는 아래를 포함하지 않는다.

- 관리자 페이지
- Runtime 실시간 판단 변경
- 중간 VQA 재검증
- 외부 backend 서버/API 구현
- Discord/Grafana 전송 구현
- 계정/토큰 제재 집행
- 정책 추천 및 자동 반영
