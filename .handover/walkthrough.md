# Stage 1 (PRE_ENTRY) — Implementation Walkthrough

## 요약

Stage 1 전체 구현 완료: 경기 상세 페이지, 예매 설정 패널, 예매 진입(S1→S2 전이).

---

## 파일 구조

### Backend (`platform/backend/`)

```
src/main/java/com/trafficmaster/
├── TrafficMasterApplication.java      # 엔트리포인트
├── config/
│   └── WebConfig.java                 # CORS 설정
├── dto/
│   ├── PreferencesDTO.java            # @Min(1)/@Max(10) partySize
│   ├── PriceRangeDTO.java             # @Min(20000)/@Max(100000) + @AssertTrue
│   ├── GameDetailDTO.java             # SaleStatus enum 포함
│   ├── BookingRequestDTO.java         # @NotNull sessionId, @NotBlank gameId
│   ├── BookingResponseDTO.java        # queueTicketId + nextUrl
│   ├── TeamDTO.java
│   ├── VenueDTO.java
│   └── PriceItemDTO.java
├── session/
│   ├── SessionStore.java              # Interface (getOrCreate default method)
│   ├── InMemorySessionStore.java      # ConcurrentHashMap 구현체
│   └── SessionData.java              # sessionId, currentStage, preferences
├── audit/
│   ├── AuditEvent.java                # Level 0 Addendum telemetry schema
│   └── DecisionAuditLogger.java       # Append-only JSONL writer
└── controller/
    ├── GameController.java            # GET /api/games/{gameId}
    ├── SessionController.java         # GET/POST /api/sessions/{id}/preferences
    └── BookingController.java         # POST /api/booking/entry (S1→S2)
```

### Frontend (`platform/frontend/src/`)

```
├── types/index.ts                     # GameDetail, Preferences, SaleStatus
├── services/api.ts                    # Axios + TM_SESSION_ID 자동 관리
├── stores/usePreferenceStore.ts       # Zustand + localStorage + debounced API sync
├── components/
│   ├── BookingCard.tsx                # 토글, 드롭다운, 슬라이더, 예매 버튼
│   └── GameInfoTabs.tsx               # 경기 정보 / 가격표 탭
└── app/games/[gameId]/page.tsx        # 메인 페이지 (GameDetail + Booking)
```

---

## 검증 결과

### Backend JUnit (8 tests — ALL PASS ✅)

| 테스트 | 결과 |
|--------|------|
| GET /api/games/{gameId} → 200 + 필드 검증 | ✅ |
| GET /preferences (unknown session) → default 반환 | ✅ |
| POST /preferences (valid) → 200 | ✅ |
| POST /preferences (partySize=11) → 400 | ✅ |
| POST /preferences (partySize=0) → 400 | ✅ |
| POST /booking/entry (valid) → queueTicketId | ✅ |
| POST /booking/entry (missing sessionId) → 400 | ✅ |
| POST /booking/entry → BOOKING_CLICKED 감사 로그 | ✅ |

### Frontend TypeScript

- `npx tsc --noEmit` → **0 errors** (앱 코드)
- E2E 테스트(`e2e/`)는 `@playwright/test` 설치 후 실행 가능

---

## 실행 방법

```bash
# Backend
cd platform/backend
./gradlew bootRun

# Frontend (별도 터미널)
cd platform/frontend
npm run dev
# → http://localhost:3000/games/game-001

# Backend Tests
cd platform/backend
./gradlew test

# E2E Tests (Playwright 설치 필요)
cd platform/frontend
npm install -D @playwright/test
npx playwright install chromium
npx playwright test e2e/BookingE2ETest.spec.ts
```

---

## Level 0 Addendum 준수 사항

| 규칙 | 구현 방식 |
|------|----------|
| **S1→S2 전이** | `BookingController`에서 session stage를 S2로 변경 후 queueTicketId 반환 |
| **decision_audit 스키마** | `AuditEvent` 클래스가 Addendum `telemetry.fields` 전체 준수 |
| **ReasonCode 표준** | Hold/Order/Payment 코드는 아직 사용 안 함 (S1 범위 외) |
| **Test Hook 지원** | `application.yml`에 `TM_TEST_MODE` env var 설정 준비 완료 |
