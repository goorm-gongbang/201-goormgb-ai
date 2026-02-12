# Stage 4/5 (SEAT_SELECTION) Full-Stack Implementation

## Backend (Spring Boot)
- [ ] Create models: `SeatBundle`, `Hold`, `Order`, `SeatStatus`
- [ ] Create DTOs: `HoldRequest`, `HoldResponse`, `OrderRequest`, `OrderResponse`, `SeatBundleDTO`
- [ ] Create `SeatService.java` (atomic hold with ReentrantLock, idempotency, session limit)
- [ ] Create `RecommendationController.java` (GET /api/recommendations)
- [ ] Create `HoldController.java` (POST /api/holds)
- [ ] Create `OrderController.java` (POST /api/orders)
- [ ] Wire DecisionAuditLogger for S4/5 events

## Frontend (Next.js)
- [ ] Create `stores/useSeatStore.ts` (Zustand)
- [ ] Create `components/seats/RecommendPanel.tsx`
- [ ] Create `components/seats/SeatArea.tsx` (10x10 grid)
- [ ] Create `components/common/HoldFailureModal.tsx`
- [ ] Create `app/seats/page.tsx`
- [ ] Update queue GRANTED → /seats redirect

## Tests
- [ ] Create `ConcurrencyHoldTest.java` (10 threads, 1 success)
- [ ] Create `SeatSelectionE2E.spec.ts` (Playwright)

## Sync
- [ ] Update `.handover/progress.md`
