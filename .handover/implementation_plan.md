# Stage 1 (PRE_ENTRY) — Full-Stack Implementation Plan

Traffic-Master의 Stage 1 (경기 상세 정보 확인 및 예매 진입) 전체 구현.

> [!IMPORTANT]
> 기존 `platform/` 코드는 무시하고, 동일 프로젝트 내에 새 패키지/파일로 구현합니다.
> Level 0 (Addendum) 규칙이 Level 1 (Stage SSOT)보다 항상 우선합니다.

---

## Proposed Changes

### Backend — Spring Boot (Java 21)

기존 패키지 `com.goorm.gongbang.defender`를 `com.trafficmaster`로 교체합니다.

---

#### [MODIFY] [build.gradle](file:///Users/jangjihyeon/201-goormgb-ai/platform/backend/build.gradle)

- `group` → `com.trafficmaster`
- `spring-boot-starter-validation` 추가 (Jakarta `@Valid`, `@Min`, `@Max`)
- `jackson-datatype-jsr310` 추가 (ISODate 직렬화)
- `spring-boot-starter-security`, `data-jpa`, `data-redis`, `postgresql` 제거 (MVP에선 불필요)
- `spring-boot-starter-test` 유지

#### [MODIFY] [settings.gradle](file:///Users/jangjihyeon/201-goormgb-ai/platform/backend/settings.gradle)

- `rootProject.name = 'traffic-master-backend'`

---

#### [NEW] [TrafficMasterApplication.java](file:///Users/jangjihyeon/201-goormgb-ai/platform/backend/src/main/java/com/trafficmaster/TrafficMasterApplication.java)

- `@SpringBootApplication` 메인 클래스

#### [NEW] [application.yml](file:///Users/jangjihyeon/201-goormgb-ai/platform/backend/src/main/resources/application.yml)

- 서버 포트 8080, audit 로그 경로 설정

---

#### [NEW] DTOs (`com.trafficmaster.dto`)

| 파일 | 내용 |
|------|------|
| `PreferencesDTO.java` | `recommendEnabled`, `partySize(@Min(1)/@Max(10))`, `priceFilterEnabled`, `priceRange` |
| `PriceRangeDTO.java` | `min(@Min(20000))`, `max(@Max(100000))` + `@AssertTrue(min<=max)` |
| `GameDetailDTO.java` | `gameId`, `homeTeam`, `awayTeam`, `dateTime`, `venue`, `saleStatus`, `dDay`, `priceTable` |
| `TeamDTO.java` | `name`, `logo` |
| `VenueDTO.java` | `name`, `location` |
| `PriceItemDTO.java` | `grade`, `price`, `color` |
| `BookingRequestDTO.java` | `sessionId(@NotNull)`, `gameId(@NotBlank)`, `preferences(@Valid)` |
| `BookingResponseDTO.java` | `queueTicketId`, `nextUrl` |

---

#### [NEW] Session Management (`com.trafficmaster.session`)

| 파일 | 내용 |
|------|------|
| `SessionStore.java` | Interface: `get/save/exists` |
| `InMemorySessionStore.java` | `@Component` + `ConcurrentHashMap` 구현체 |
| `SessionData.java` | `sessionId`, `currentStage`, `preferences`, `createdAt`, `updatedAt` |

---

#### [NEW] Audit Logger (`com.trafficmaster.audit`)

| 파일 | 내용 |
|------|------|
| `DecisionAuditLogger.java` | Addendum `telemetry` 스키마 준수, `decision_audit.jsonl`에 append-only 기록 |
| `AuditEvent.java` | `ts`, `sessionId`, `stage`, `eventType`, `actor`, `requestId`, `correlationId`, `payload`, `serverDecision`, `result` |

---

#### [NEW] Controllers (`com.trafficmaster.controller`)

| 파일 | 엔드포인트 |
|------|-----------|
| `GameController.java` | `GET /api/games/{gameId}` — Mock 데이터 반환 |
| `SessionController.java` | `GET/POST /api/sessions/{sessionId}/preferences` |
| `BookingController.java` | `POST /api/booking/entry` — QueueTicket 발급 mock |

---

#### [DELETE] 기존 defender 패키지

| 파일 |
|------|
| `DefenderApplication.java` |
| `SecurityConfig.java` |
| `TelemetryController.java` |
| `TelemetryRequest.java` |

---

### Frontend — Next.js (App Router, TypeScript, Tailwind v4)

---

#### [NEW] [types/index.ts](file:///Users/jangjihyeon/201-goormgb-ai/platform/frontend/src/types/index.ts)

- `Preferences`, `GameDetail`, `Team`, `Venue`, `PriceItem`, `SaleStatus` 타입 정의

#### [NEW] [services/api.ts](file:///Users/jangjihyeon/201-goormgb-ai/platform/frontend/src/services/api.ts)

- Axios 인스턴스 (baseURL: `/api`, 헤더에 `X-Session-Id` 자동 포함)
- `getGame()`, `getPreferences()`, `postPreferences()`, `postBookingEntry()` 함수
- `getOrCreateSessionId()` — localStorage에서 `TM_SESSION_ID` 관리

#### [NEW] [stores/usePreferenceStore.ts](file:///Users/jangjihyeon/201-goormgb-ai/platform/frontend/src/stores/usePreferenceStore.ts)

- Zustand store: `preferences` 상태 + `toggle/setPartySize/setPriceRange` 액션
- `localStorage` 동기화 (`TM_PREFERENCES` 키)
- Debounced API sync (300ms)

#### [NEW] [components/BookingCard.tsx](file:///Users/jangjihyeon/201-goormgb-ai/platform/frontend/src/components/BookingCard.tsx)

- 추천 토글, 인원 드롭다운, 가격대 필터/슬라이더, 예매하기 버튼
- `saleStatus`에 따라 버튼 비활성화 (ON_SALE만 활성)

#### [NEW] [components/GameInfoTabs.tsx](file:///Users/jangjihyeon/201-goormgb-ai/platform/frontend/src/components/GameInfoTabs.tsx)

- 경기 정보 탭 + 가격표 탭

#### [NEW] [app/games/\[gameId\]/page.tsx](file:///Users/jangjihyeon/201-goormgb-ai/platform/frontend/src/app/games/%5BgameId%5D/page.tsx)

- `GameDetailPage`: 진입 시 세션 생성 + Game 데이터 fetch
- 좌측 GameInfoTabs + 우측 BookingCard 레이아웃

#### [MODIFY] [layout.tsx](file:///Users/jangjihyeon/201-goormgb-ai/platform/frontend/src/app/layout.tsx)

- title/description을 "Traffic-Master"로 변경

#### [MODIFY] [next.config.ts](file:///Users/jangjihyeon/201-goormgb-ai/platform/frontend/next.config.ts)

- `/api/**` → `http://localhost:8080` 프록시 rewrite 추가

---

### Tests

---

#### [NEW] [BookingControllerTest.java](file:///Users/jangjihyeon/201-goormgb-ai/platform/backend/src/test/java/com/trafficmaster/controller/BookingControllerTest.java)

- `GET /api/games/{gameId}` — 200 + GameDetail 응답 검증
- `GET /api/sessions/{id}/preferences` — 없는 세션도 default 반환 검증
- `POST /api/sessions/{id}/preferences` — validation 실패(partySize=11) → 400 검증
- `POST /api/booking/entry` — 정상 → queueTicketId 존재 검증
- `POST /api/booking/entry` → `decision_audit.jsonl`에 `BOOKING_CLICKED` 기록 검증

#### [NEW] [BookingE2ETest.spec.ts](file:///Users/jangjihyeon/201-goormgb-ai/platform/frontend/e2e/BookingE2ETest.spec.ts)

- 상태 복원: partySize 변경 → 새로고침 → 유지 검증
- 제약 조건: partySize 범위 초과 시 UI 제한 검증
- 예매하기 버튼 클릭 → 라우팅 검증

---

## Verification Plan

### Automated Tests

**Backend (JUnit):**
```bash
cd /Users/jangjihyeon/201-goormgb-ai/platform/backend
./gradlew test
```

**Frontend E2E (Playwright):**
```bash
cd /Users/jangjihyeon/201-goormgb-ai/platform/frontend
npx playwright install --with-deps chromium
npx playwright test e2e/BookingE2ETest.spec.ts
```

### Manual Verification

1. **백엔드 빌드 확인**: `./gradlew bootRun` 실행 후 `http://localhost:8080/api/games/game-001` 접속하여 JSON 응답 확인
2. **프론트엔드 실행**: `npm run dev` 후 `http://localhost:3000/games/game-001` 접속하여 UI 렌더링 확인
3. **Audit 로그 검증**: 예매하기 클릭 후 `decision_audit.jsonl` 파일에 로그 기록 확인
