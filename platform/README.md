# 🎫 Traffic-Master Platform

티켓 예매 시스템의 풀스택 플랫폼입니다. 대기열 → 보안 검증 → 좌석 선택 → 결제까지의 전체 예매 플로우를 구현합니다.

## 아키텍처

```
platform/
├── backend/    # Spring Boot 3 (Java 17) — REST API, 대기열, 보안, 결제
└── frontend/   # Next.js 16 (React 19) — SPA UI
```

## 빠른 시작

### 1. Backend 실행

```bash
cd platform/backend

# 일반 모드
./gradlew bootRun

# 테스트 모드 (보안 퀴즈 강제 활성화)
TM_TEST_MODE=true ./gradlew bootRun
```

- **포트**: `http://localhost:8080`
- **API 베이스**: `/api/*`

### 2. Frontend 실행

```bash
cd platform/frontend
npm install   # 최초 1회
npm run dev
```

- **포트**: `http://localhost:3000`

## 주요 기능 (Stage 1~7)

| Stage | 기능 | 백엔드 | 프론트엔드 |
|-------|------|--------|-----------|
| 1 | 공연 목록 | `GameController` | `page.tsx` |
| 2 | 가상 대기열 | `QueueService` | `useQueuePolling` |
| 3 | 보안 검증 (캡챠) | `SecurityService` | `SecurityLayer` |
| 4-5 | 좌석 선택 (지도) | `SeatService`, `MapController` | `ZoneSeatGridView` |
| 6 | 결제 | `PaymentService` | `PaymentPanel` |
| 7 | 인프라 | `DecisionAuditLogger` | `apiClient` |

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `TM_TEST_MODE` | 테스트 훅 활성화 (보안 퀴즈 강제 등) | `false` |
| `TM_PAYMENT_FAIL_RATE` | 결제 실패율 (0.0~1.0) | `0` |

## 테스트 모드 헤더

`TM_TEST_MODE=true`일 때 프론트엔드에서 자동으로 아래 헤더가 전송됩니다:

| 헤더 | 설명 |
|------|------|
| `X-Session-Id` | 세션 식별자 |
| `X-TM-ForceChallenge` | 보안 퀴즈 강제 |
| `X-TM-PaymentFailRate` | 결제 실패율 |
| `X-TM-QueueWaitMs` | 대기열 대기시간 |

## 예매 플로우

```
홈(공연 목록) → 대기열 진입 → 대기열 통과 → 보안 퀴즈 → 좌석 선택 → 결제 → 완료
```
