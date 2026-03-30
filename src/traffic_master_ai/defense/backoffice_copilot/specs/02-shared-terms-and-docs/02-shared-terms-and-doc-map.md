# 02-shared-terms-and-doc-map

## 1. 문서 목적
이 문서는 Backoffice Copilot SSOT 문서들의 역할과 경계를 정렬하는 메타 문서다.  
구현 규칙을 새로 만들지 않고, 기존 문서의 권위 범위, 공통 용어, 읽기 순서, 충돌 해결 기준을 고정한다.

## 2. 문서 체계 한눈에 보기
| 문서 | 한 줄 역할 | 권위 범위 |
| --- | --- | --- |
| `00-core-rules.md` | 시스템 헌법(불변 원칙) | 범위, 금지사항, 책임 분리, 최상위 원칙 |
| `01-service-overview.md` | 제품 정의서 | 서비스 목표/비목표, 대상 세션, F 상태 모델 |
| `10-post-review-rules.md` | 도메인 규칙서 | 후보 추출, 세션 분석, fallback 트리거, LLM 입출력 규칙 |
| `11-review-output-rules.md` | 출력 계약서 | PostgreSQL 2테이블 저장, export 후속 산출물 규칙, 파일 간 정합성 |
| `20-langgraph-node-spec.md` | 실행 구조 계약서 | LangGraph 노드 책임, 노드 간 I/O, 병렬 처리 경계 |
| `21-data-contract.md` | 데이터 스키마 계약서 | 입력/중간/출력 DTO 최소 필드, semantic mapping 경계, 필드 추가 금지 |
| `30-ops-and-checks.md` | 운영 검증서 | 실행 전/후 체크, 실패 허용 기준, QA 최소 세트 |

## 3. 공통 용어 사전
### Runtime
- 용어: Runtime
- 한 줄 정의: 실시간으로 allow/throttle/require_s3/block을 판단하고 감사 로그를 남기는 실행 계층.
- 최초/공식 정의 문서: `00-core-rules.md`, `01-service-overview.md`
- 구현 시 주의점: Backoffice Copilot이 Runtime 판단을 재정의하거나 대체하면 안 된다.

### Backoffice Copilot
- 용어: Backoffice Copilot
- 한 줄 정의: 시간 구간 종료 후 Runtime 통과 세션을 로그 기반으로 사후 판단하는 시스템.
- 최초/공식 정의 문서: `00-core-rules.md`, `01-service-overview.md`
- 구현 시 주의점: 실시간 제재/정책 자동반영/운영 UI/API 범위를 포함하지 않는다.

### match_id
- 용어: match_id
- 한 줄 정의: v1 사후 판단 실행(run)을 식별하는 단일 기준 키.
- 최초/공식 정의 문서: `21-data-contract.md`, `20-langgraph-node-spec.md`
- 구현 시 주의점: v1에서는 `review_run_id`를 활성 식별자로 사용하지 않는다.

### session_id
- 용어: session_id
- 한 줄 정의: 후보 추출, 타임라인 재구성, 결과 저장의 기준 키가 되는 세션 식별자.
- 최초/공식 정의 문서: `10-post-review-rules.md`, `21-data-contract.md`
- 구현 시 주의점: 문서에 `sessionId` 표기가 섞여 있어도 데이터 계약 키는 `session_id`를 기준으로 맞춘다.

### candidate session
- 용어: candidate session
- 한 줄 정의: 사후 판단 가치가 있어 후속 분석 대상으로 선택된 회색지대 세션.
- 최초/공식 정의 문서: `10-post-review-rules.md`
- 구현 시 주의점: hard filter는 `10-post-review-rules.md` 기준이며 `payment_success`나 결제 단계 표현을 후보 조건으로 쓰지 않는다.

### session_summary
- 용어: session_summary
- 한 줄 정의: 후보 추출 단계에서 생성되는 세션 단위 중간 집계 산출물.
- 최초/공식 정의 문서: `21-data-contract.md`(최소 스키마), `10-post-review-rules.md`(확장 예시)
- 구현 시 주의점: 필드 충돌 시 `21-data-contract.md`의 최소 스키마를 우선하고 `latest_*`/`terminal_outcome` 값은 semantic mapping 결과로 해석한다.

### session_analysis
- 용어: session_analysis
- 한 줄 정의: 후보 세션 타임라인을 규칙 기반으로 재구성한 분석 결과 객체.
- 최초/공식 정의 문서: `21-data-contract.md`(최소 스키마), `10-post-review-rules.md`(생성 규칙)
- 구현 시 주의점: `terminal_outcome`, `suspicious_signals`, `needs_raw_fallback`의 해석 규칙을 임의 변경하지 않고, row loader 책임과 semantic mapping 책임을 섞지 않는다.

### review_result
- 용어: review_result
- 한 줄 정의: 세션 사후 판단 최종 레이블.
- 최초/공식 정의 문서: `11-review-output-rules.md`, `21-data-contract.md`
- 구현 시 주의점: 허용값은 `NORMAL`, `SUSPICIOUS` 두 개뿐이다.

### evidence_summary
- 용어: evidence_summary
- 한 줄 정의: 세션 판단 근거를 설명하는 1문장 텍스트.
- 최초/공식 정의 문서: `10-post-review-rules.md`, `11-review-output-rules.md`
- 구현 시 주의점: 입력 근거 밖 추측 금지, 빈 문자열 금지.

### summary_text
- 용어: summary_text
- 한 줄 정의: 시간 구간 전체 결과를 설명하는 3줄 요약 배열.
- 최초/공식 정의 문서: `11-review-output-rules.md`, `21-data-contract.md`
- 구현 시 주의점: 길이는 정확히 3이어야 하며 파일 간 수치와 모순되면 안 된다.

### suspicious session
- 용어: suspicious session
- 한 줄 정의: `review_result=SUSPICIOUS`로 확정되어 DB에 저장되고 필요 시 export로 파생되는 세션.
- 최초/공식 정의 문서: `11-review-output-rules.md`
- 구현 시 주의점: `NORMAL` 세션은 suspicious export에 저장하지 않고 summary 통계에만 반영한다.

### defense_audit_events
- 용어: defense_audit_events
- 한 줄 정의: 사후 판단의 1순위 입력 원본 로그(`1 event = 1 row`).
- 최초/공식 정의 문서: `00-core-rules.md`, `21-data-contract.md`
- 구현 시 주의점: 시간 구간 필터를 반드시 적용하고, 파이프라인 기본 입력으로 사용한다.

### decision_audit
- 용어: decision_audit
- 한 줄 정의: 보강 조회용 2순위 원본 감사 로그.
- 최초/공식 정의 문서: `10-post-review-rules.md`, `21-data-contract.md`
- 구현 시 주의점: 필요한 세션에 한해 좁은 범위 조회만 허용되며 전량 스캔은 금지다.

### raw fallback
- 용어: raw fallback
- 한 줄 정의: warehouse 정보 부족 시 `decision_audit`로 의미 필드를 보강하는 제한적 조회 절차.
- 최초/공식 정의 문서: `10-post-review-rules.md`, `20-langgraph-node-spec.md`
- 구현 시 주의점: `needs_raw_fallback=true` 조건 세션만, `session_id+time window` 제한 조회를 지켜야 한다.

### semantic mapping
- 용어: semantic mapping
- 한 줄 정의: 원시 row의 `flowState`, `terminalReason`, `reasonCode`, `latest_*`를 공식 해석 필드로 변환하는 계층.
- 최초/공식 정의 문서: `10-post-review-rules.md`, `21-data-contract.md`
- 구현 시 주의점: row loader는 raw row만 읽고, event interpreter/세션 분석은 semantic mapping 결과를 소비한다.

### time window
- 용어: time window
- 한 줄 정의: 분석 대상 이벤트를 자르는 실행 시간 범위(`window_start_ms`, `window_end_ms`).
- 최초/공식 정의 문서: `20-langgraph-node-spec.md`, `21-data-contract.md`
- 구현 시 주의점: 모든 입력/조회/집계가 이 범위를 벗어나면 안 된다.

### terminal_outcome
- 용어: terminal_outcome
- 한 줄 정의: semantic mapping이 세션 종료 맥락을 session-level 판단용 값으로 정리한 결과(`NOT_BLOCKED` 등).
- 최초/공식 정의 문서: `10-post-review-rules.md`, `21-data-contract.md`
- 구현 시 주의점: 후보 추출 hard filter는 `10-post-review-rules.md`를 따르며 payment 의미를 역으로 재도입하지 않는다.

### F0 / F1 / F2 / F3R / F3M / F4R / F4M / FX
- 용어: F 상태 인덱스
- 한 줄 정의: Runtime 이후 사후 판단 대상을 해석할 때 쓰는 티켓팅 흐름 상태 모델.
- 최초/공식 정의 문서: `01-service-overview.md`
- 구현 시 주의점: S 기반 구모델을 재도입하지 말고, F 상태 인덱스를 v1 후보 hard filter로 승격하지 않는다.

## 4. 문서별 역할 요약
| 문서명 | 한 줄 역할 | 이 문서가 답하는 질문 | 이 문서를 언제 읽어야 하는지 |
| --- | --- | --- | --- |
| `00-core-rules.md` | 최상위 불변 규칙 정의 | “이 시스템이 절대 하면 안 되는 것은 무엇인가?” | 구현 시작 전, 범위 충돌 발생 시 즉시 |
| `01-service-overview.md` | 제품 범위와 상태 모델 정의 | “무엇을 위한 서비스이며 어떤 세션을 다루는가?” | 요구사항 해석 시작 시, 도메인 온보딩 시 |
| `10-post-review-rules.md` | 사후 판단 도메인 규칙 정의 | “후보를 어떻게 뽑고 세션 분석/LLM 계약을 어떻게 구성하는가?” | 후보/분석/fallback 로직 구현 직전 |
| `11-review-output-rules.md` | DB-first 출력 계약 정의 | “어떤 DB row를 정식 저장으로 보고 export를 어떻게 파생하는가?” | 저장기 구현 직전, 결과 포맷 이슈 발생 시 |
| `20-langgraph-node-spec.md` | 노드 구조와 책임 분리 정의 | “그래프 노드가 어떤 순서로 무엇을 입출력하는가?” | 파이프라인 구조 설계/수정 직전 |
| `21-data-contract.md` | 최소 스키마 계약 정의 | “필수 필드는 무엇이며 semantic mapping 경계는 어디까지인가?” | DTO/모델 작성 직전, 필드 추가 요청 발생 시 |
| `30-ops-and-checks.md` | 운영/검증 기준 정의 | “무엇을 검증해야 성공/부분성공/실패로 볼 것인가?” | 배치 운영 준비, QA/장애 대응 시 |

## 5. 문서 읽기 순서
### 처음 읽을 때 (최초 진입 순서)
1. `02-shared-terms-and-doc-map.md`
2. `00-core-rules.md`
3. `01-service-overview.md`
4. `21-data-contract.md`
5. `20-langgraph-node-spec.md`
6. `10-post-review-rules.md`
7. `11-review-output-rules.md`
8. `30-ops-and-checks.md`

### 구현할 때 (구현 직전 순서)
1. `00-core-rules.md`
2. `01-service-overview.md`
3. `20-langgraph-node-spec.md`
4. `21-data-contract.md`
5. `10-post-review-rules.md`
6. `11-review-output-rules.md`
7. `30-ops-and-checks.md`

### 디버깅할 때 (먼저 볼 순서)
1. `30-ops-and-checks.md` (실패 유형/체크리스트)
2. `11-review-output-rules.md` (파일/정합성 오류)
3. `21-data-contract.md` (필드 누락/스키마 오류)
4. `20-langgraph-node-spec.md` (노드 경계/흐름 오류)
5. `10-post-review-rules.md` (도메인 규칙/해석 오류)
6. `00-core-rules.md`, `01-service-overview.md` (범위 오해 재확인)

### 스키마를 바꿀 때 (스키마 변경 순서)
1. `00-core-rules.md`, `01-service-overview.md`로 변경 필요성/범위 확인
2. `21-data-contract.md` 먼저 수정(필드 계약 확정)
3. `20-langgraph-node-spec.md` 수정(노드 I/O 동기화)
4. `11-review-output-rules.md` 수정(출력 계약 동기화)
5. `10-post-review-rules.md` 수정(도메인 규칙 동기화)
6. `30-ops-and-checks.md` 수정(검증 체크리스트 동기화)

## 6. 문서 충돌 해결 규칙
| 충돌 유형 | 우선 문서(권위) | 적용 규칙 |
| --- | --- | --- |
| 서비스 범위/비범위 충돌 | `00-core-rules.md` > `01-service-overview.md` | 상위 헌법(`00`)을 우선하고, 제품 정의(`01`)는 그 안에서만 해석 |
| 대상 세션 정의 충돌 | `01-service-overview.md` + `10-post-review-rules.md` | 제품 정의(`01`)를 먼저 고정한 뒤, 판정 규칙은 `10`으로 구체화 |
| 노드 책임/노드 수/흐름 충돌 | `20-langgraph-node-spec.md` | 노드 구조와 입출력 경계는 `20`을 단일 기준으로 사용 |
| 필드명/필수 필드/최소 스키마 충돌 | `21-data-contract.md` | 스키마 계약은 `21`을 우선하고, 다른 문서는 `21`에 맞춰 수정 |
| 출력 파일 형식/컬럼/정합성 충돌 | `11-review-output-rules.md` (필드 정의는 `21` 우선) | 파일 규칙은 `11`, 필드 최소 계약은 `21`을 우선 적용 |
| 후보 추출/terminal_outcome/fallback 트리거 충돌 | `10-post-review-rules.md` | 도메인 해석 규칙은 `10`을 우선 |
| 운영 성공/실패/검증 체크 충돌 | `30-ops-and-checks.md` | 실행 판정과 QA 기준은 `30`을 우선 |
| 동일 번호 `.md` vs `.yaml` 표현 불일치 | 해당 번호 `.md` 우선, `.yaml` 동기화 | 사람이 읽는 SSOT 본문은 `.md` 기준으로 정렬 후 YAML 갱신 |

## 7. 문서 작성/수정 시 주의점
- 동일 규칙을 여러 문서에 중복 정의하지 말고, 권위 문서로 링크/참조만 남긴다.
- 새 필드 추가/삭제는 반드시 `21-data-contract.md`를 먼저 수정한 뒤 다른 문서를 맞춘다.
- 노드 수, 노드 책임, 노드 간 I/O 변경은 `20-langgraph-node-spec.md`를 먼저 수정한다.
- 출력 파일명/컬럼/정합성 규칙 변경은 `11-review-output-rules.md`를 먼저 수정한다.
- 후보 추출 규칙, `terminal_outcome`, raw fallback 조건 변경은 `10-post-review-rules.md`를 먼저 수정한다.
- 운영 체크리스트/실패 허용 기준 변경은 `30-ops-and-checks.md`를 먼저 수정한다.
- 서비스 정체성/비범위 변경은 하위 문서가 아니라 `00-core-rules.md`, `01-service-overview.md`에서 시작한다.

## 8. 최종 요약
Backoffice Copilot 문서 체계는 `00/01`이 범위를 고정하고, `20/21/10/11`이 구현 계약을 분담하며, `30`이 운영 검증을 담당한다.  
필드 계약은 `21`, 노드 책임은 `20`, 출력 규칙은 `11`, 도메인 해석은 `10`을 우선해 충돌을 푼다.  
수정은 항상 “범위 확인 → 권위 문서 선수정 → 하위 문서 동기화” 순서로 진행한다.  
이 문서는 구현 지침서가 아니라, 문서들을 일관되게 읽고 수정하기 위한 참조 지도다.
