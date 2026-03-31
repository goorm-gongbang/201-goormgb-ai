package com.trafficmaster.seat;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import com.trafficmaster.dto.HoldRequest;
import com.trafficmaster.dto.HoldResponse;

@SpringBootTest
class ConcurrencyHoldTest {

    @Autowired
    private SeatService seatService;

    @Test
    @DisplayName("10 concurrent hold requests for same seats → exactly 1 success, 9 failures")
    void concurrentHold_sameSeats_onlyOneSucceeds() throws Exception {
        int threadCount = 10;
        List<String> seatIds = Arrays.asList("CONC-A-1", "CONC-A-2");
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch doneLatch = new CountDownLatch(threadCount);

        AtomicInteger successCount = new AtomicInteger(0);
        AtomicInteger failCount = new AtomicInteger(0);
        List<HoldResponse> results = new ArrayList<>();

        for (int i = 0; i < threadCount; i++) {
            final int idx = i;
            executor.submit(() -> {
                try {
                    startLatch.await(); // Synchronize start

                    HoldRequest request = HoldRequest.builder()
                            .sessionId("session-conc-" + idx)
                            .gameId("game-conc-001")
                            .mode("RECOMMEND")
                            .seatIds(new ArrayList<>(seatIds))
                            .build();

                    String idempotencyKey = "idem-conc-" + idx;
                    HoldResponse response = seatService.holdSeats(request, idempotencyKey);

                    synchronized (results) {
                        results.add(response);
                    }

                    if ("SUCCESS".equals(response.getStatus())) {
                        successCount.incrementAndGet();
                    } else {
                        failCount.incrementAndGet();
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                } finally {
                    doneLatch.countDown();
                }
            });
        }

        // Fire all threads simultaneously
        startLatch.countDown();
        doneLatch.await();
        executor.shutdown();

        // Assertions
        assertEquals(1, successCount.get(),
                "Exactly 1 thread should succeed");
        assertEquals(threadCount - 1, failCount.get(),
                "All other threads should fail");

        // Verify seat status is HELD by exactly one session
        String holder1 = seatService.getSeatStatus().get("CONC-A-1");
        String holder2 = seatService.getSeatStatus().get("CONC-A-2");
        assertNotNull(holder1, "Seat CONC-A-1 should be held");
        assertNotNull(holder2, "Seat CONC-A-2 should be held");
        assertEquals(holder1, holder2, "Both seats should be held by the same session");

        // Verify failed responses have correct reason
        long heldByOthers = results.stream()
                .filter(r -> "HELD_BY_OTHERS".equals(r.getReason()))
                .count();
        assertEquals(threadCount - 1, heldByOthers,
                "All failed responses should have HELD_BY_OTHERS reason");
    }

    @Test
    @DisplayName("Same session cannot hold twice → ALREADY_HAS_ACTIVE_HOLD")
    void sameSession_cannotHoldTwice() {
        String sessionId = "session-double-hold";

        HoldRequest req1 = HoldRequest.builder()
                .sessionId(sessionId)
                .gameId("game-double-001")
                .seatIds(Arrays.asList("DBL-1"))
                .build();

        HoldResponse res1 = seatService.holdSeats(req1, "idem-double-1");
        assertEquals("SUCCESS", res1.getStatus());

        HoldRequest req2 = HoldRequest.builder()
                .sessionId(sessionId)
                .gameId("game-double-001")
                .seatIds(Arrays.asList("DBL-2"))
                .build();

        HoldResponse res2 = seatService.holdSeats(req2, "idem-double-2");
        assertEquals("FAIL", res2.getStatus());
        assertEquals("ALREADY_HAS_ACTIVE_HOLD", res2.getReason());
    }

    @Test
    @DisplayName("Idempotent requests return cached result")
    void idempotentRequest_returnsCachedResult() {
        HoldRequest request = HoldRequest.builder()
                .sessionId("session-idem-test")
                .gameId("game-idem-001")
                .seatIds(Arrays.asList("IDEM-1", "IDEM-2"))
                .build();

        String key = "idem-same-key";
        HoldResponse res1 = seatService.holdSeats(request, key);
        HoldResponse res2 = seatService.holdSeats(request, key);

        assertEquals(res1.getHoldId(), res2.getHoldId());
        assertEquals(res1.getStatus(), res2.getStatus());
    }
}
