# AI 팀 3/19 Dev 배포 분업 명세서 (R&R)

본 문서는 한정된 리소스(AI 팀 2인) 환경에서 3월 19일 전체 아키텍처 연동(Dev 배포)을 병목 없이 완수하기 위한 **내부 작업 분할(WBS) 및 역할(R&R) 정의서**입니다.

두 개발자 간의 **코드 의존성(Coupling)을 최소화**하여, 한 쪽의 개발 지연이 다른 쪽의 차단 로직 테스트를 방해하지 않도록 철저히 독립적인 모듈로 분리하여 진행합니다.

---

## 👨‍💻 Main Dev (지현님)

**목표:** 지연 시간(Latency)에 가장 민감하고 백엔드/클라우드와의 1차 통신 모듈을 전담하여, AI 실시간 방어망의 핵심 척추(Core)를 완성합니다.

### 1️⃣ Dual-Blocking (제재 웹훅) 로직 구현
*   **작업 내용:** AI 알고리즘이 봇으로 최종 판단(BLOCK 결정)했을 때, Istio에게 403을 내림과 **동시에** 백엔드 제재 API(`POST /api/v1/internal/sanctions`)를 비동기로 찌르는 로직 개발.
*   **변경 파일:** `src/traffic_master_ai/defense/api/main.py`
*   **리스크:** (High) 네트워크 맹점 및 지연 발생 시 예매 트래픽 전체 영향.

### 2️⃣ JWT 파싱 및 Evaluate Request 스키마 확장
*   **작업 내용:** Istio가 넘겨줄 JWT 클레임(혹은 HTTP Header `x-user-id`)을 받아오도록 `EvaluateRequest` Pydantic 모델에 필드 추가 및 상태 관리(Redis Key) 연동.
*   **변경 파일:** `src/traffic_master_ai/defense/api/models.py`

### 3️⃣ Redis 강제 연동 (State Store)
*   **작업 내용:** 현재 환경 변수 없을 때 fallback하는 인메모리(`InMemoryStateStore`) 로직을 걷어내거나, K8s 배포 환경에 맞춰 실제 Redis 클러스터와 완전히 연결 및 동시성 락(Lock) 처리 완비.
*   **변경 파일:** `src/traffic_master_ai/defense/api/state.py`

---

## 👩‍💻 Sub Dev (팀원)

**목표:** 메인 평가(Evaluate) 로직과 완전히 분리되어 있는 **프론트엔드 연동 및 비동기 파이프라인**을 전담하여, 사고가 나도 서비스 전체 장애가 발생하지 않도록(Fail-Safe) 안전한 외곽 모듈을 개발합니다.

### 1️⃣ 프론트엔드 레포지토리 보안 스크립트 연동 (Frontend)
*   **작업 내용 (Cloudflare):** 대기열 진입 API(`POST /api/booking/entry`) 호출 시 1차 가시성 없는 방어막인 Cloudflare Turnstile 위젯 렌더링 및 통과 토큰 수집 로직 추가.
*   **작업 내용 (Telemetry):** 사용자의 마우스 궤적, 스크롤, 클릭 이벤트를 주기적으로 수집하여 `POST /challenge/event` 등으로 쏘는 센서(Sensor) 스크립트를 예매화면에 부착.
*   **작업 내용 (VQA Popup):** 백엔드 API 호출 결과가 `428 CHALLENGE_REQUIRED` 로 떨어지면, 미리 만들어둔 '공 잡기' 모달창을 렌더링하고 `POST /challenge/start` & `verify` 통신을 수행하도록 연동.
*   **타겟 레포:** `platform/frontend` 내부 폴더/컴포넌트
*   **리스크:** (Low) UI/UX 스크립트로서 로컬에서 가짜 서버 띄워놓고 100% 독립 테스트(Mocking) 가능.

### 2️⃣ S3 비동기 Audit 로그 업로더 개발 (Data Pipeline)
*   **작업 내용:** `audit.py`가 디스크에 쓰는 `logs/defense_decision_audit.jsonl` 파일을 모니터링하다가 1만 줄 초과 혹은 1분 경과 시 AWS S3 (혹은 호환 MinIO)로 비동기 업로드 후 로컬 파일 비우는 스크립트/워커 프로세스 작성.
*   **타겟 레포:** 백그라운드 워커 스크립트 (예: `s3_audit_worker.py` 신규 작성)
*   **리스크:** (Low) 메인 API 성능에 0% 영향. 테스트가 간편함.

---

## 🚀 WBS 마일스톤 (3/19 타겟)

| 날짜 | Main Dev (Backend AI) | Sub Dev (Frontend & Data) |
| :--- | :--- | :--- |
| **D-2** | Redis 연동 테스트 완료 및 JWT 스키마 확장 | 프론트엔드 Cloudflare 위젯 통과 테스트 완료 |
| **D-1** | 백엔드 Sanctions API 비동기 훅 호출 개발 완료 | 프론트엔드 VQA 팝업 렌더링 및 통신 붙이기 완료 |
| **D-Day**| 로컬 통합 테스트 및 Dev 브랜치 PR 배포 | S3 파일 업로더 스크립트 작성 및 Dev 통합 |

> **협업 원칙:** Sub Dev(팀원)는 프론트엔드 개발 시, Main Dev(지현님)의 AI API 서버가 완성되기를 기다리지 말고 **로컬에 직접 Postman이나 임시 Mock 서버를 띄워서 병렬(Parallel) 진행**합니다.
