package com.trafficmaster.seat;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.HoldRequest;
import com.trafficmaster.dto.HoldResponse;
import com.trafficmaster.dto.OrderRequest;
import com.trafficmaster.dto.OrderResponse;

import lombok.RequiredArgsConstructor;

/**
 * Stage 4/5 SSOT: Seat management with Atomic Hold guarantees.
 *
 * Consistency Rules (SSOT):
 *   Atomicity:    All-or-Nothing — if ANY seat unavailable, entire hold fails
 *   Idempotency:  Same Idempotency-Key returns cached result
 *   Concurrency:  Single Active Hold per session
 *   Separation:   UI selection ≠ server hold state
 */
@Service
@RequiredArgsConstructor
public class SeatService {

    private static final Logger log = LoggerFactory.getLogger(SeatService.class);
    private static final long HOLD_DURATION_MS = 5 * 60 * 1000; // 5 minutes

    private final DecisionAuditLogger auditLogger;

    // ─── In-Memory Stores ───
    // seatId → "AVAILABLE" | sessionId (who holds it)
    private final ConcurrentHashMap<String, String> seatStatus = new ConcurrentHashMap<>();
    // holdId → Hold
    private final ConcurrentHashMap<String, Hold> holdStore = new ConcurrentHashMap<>();
    // sessionId → holdId (active hold tracking)
    private final ConcurrentHashMap<String, String> activeHolds = new ConcurrentHashMap<>();
    // idempotencyKey → HoldResponse (cached results)
    private final ConcurrentHashMap<String, HoldResponse> idempotencyCache = new ConcurrentHashMap<>();
    // orderId → Order
    private final ConcurrentHashMap<String, Order> orderStore = new ConcurrentHashMap<>();

    // Global lock for atomic hold operations
    private final ReentrantLock holdLock = new ReentrantLock();

    // ─── Recommendation (Mock) ───

    public List<SeatBundle> getRecommendations(String gameId, int partySize, String tab) {
        List<SeatBundle> all = generateMockBundles(gameId, partySize);

        if (tab == null || "all".equals(tab)) return all;

        int filterRank = switch (tab) {
            case "rank1" -> 1;
            case "rank2" -> 2;
            case "rank3" -> 3;
            default -> 0;
        };

        if (filterRank == 0) return all;

        return all.stream()
                .filter(b -> b.getRank() == filterRank)
                .collect(Collectors.toList());
    }

    private List<SeatBundle> generateMockBundles(String gameId, int partySize) {
        List<SeatBundle> bundles = new ArrayList<>();
        String[][] sections = {
            {"네이비석", "305블럭"},
            {"블루석", "210블럭"},
            {"오렌지석", "115블럭"},
            {"레드석", "108블럭"},
            {"테이블석", "201블럭"},
            {"익사이팅존", "102블럭"},
        };
        int[] prices = {20000, 25000, 30000, 35000, 50000, 40000};

        for (int i = 0; i < sections.length; i++) {
            List<String> seatIds = new ArrayList<>();
            for (int s = 0; s < partySize; s++) {
                seatIds.add(sections[i][1] + "-" + (10 + i) + "열-" + (s + 1) + "번");
            }

            bundles.add(SeatBundle.builder()
                    .seatBundleId(UUID.randomUUID().toString())
                    .gameId(gameId)
                    .seatIds(seatIds)
                    .sectionLabel(sections[i][0])
                    .rowLabel(sections[i][1] + " " + (10 + i) + "열")
                    .totalPrice(prices[i] * partySize)
                    .rank(i < 2 ? 1 : (i < 4 ? 2 : 3))
                    .build());
        }
        return bundles;
    }

    // ─── Atomic Hold (Core) ───

    public HoldResponse holdSeats(HoldRequest request, String idempotencyKey) {
        // 1. Idempotency check
        if (idempotencyKey != null) {
            HoldResponse cached = idempotencyCache.get(idempotencyKey);
            if (cached != null) {
                log.info("Idempotent hold request returned cached result for key: {}", idempotencyKey);
                return cached;
            }
        }

        // Log HOLD_REQUESTED
        auditLogger.logStage1Event(
                request.getSessionId(),
                "HOLD_REQUESTED",
                Map.of(
                        "idempotencyKey", idempotencyKey != null ? idempotencyKey : "none",
                        "seatIds", request.getSeatIds()
                ),
                "OK", null
        );

        holdLock.lock();
        try {
            // 2. Session limit check — single active hold per session
            String existingHoldId = activeHolds.get(request.getSessionId());
            if (existingHoldId != null) {
                Hold existing = holdStore.get(existingHoldId);
                if (existing != null && existing.getStatus() == Hold.HoldStatus.ACTIVE && !existing.isExpired()) {
                    HoldResponse failResponse = HoldResponse.builder()
                            .holdId(null)
                            .status("FAIL")
                            .reason("ALREADY_HAS_ACTIVE_HOLD")
                            .build();

                    auditLogger.logStage1Event(
                            request.getSessionId(),
                            "HOLD_FAILED",
                            Map.of("reason", "ALREADY_HAS_ACTIVE_HOLD"),
                            "FAIL", "Session already has active hold"
                    );

                    cacheIfKeyed(idempotencyKey, failResponse);
                    return failResponse;
                } else {
                    // Expired hold — clean up
                    activeHolds.remove(request.getSessionId());
                    if (existing != null) {
                        existing.setStatus(Hold.HoldStatus.EXPIRED);
                        existing.getSeatIds().forEach(seatStatus::remove);
                    }
                }
            }

            // 3. Atomic availability check — ALL seats must be AVAILABLE
            for (String seatId : request.getSeatIds()) {
                String holder = seatStatus.get(seatId);
                if (holder != null) {
                    HoldResponse failResponse = HoldResponse.builder()
                            .holdId(null)
                            .status("FAIL")
                            .reason("HELD_BY_OTHERS")
                            .build();

                    auditLogger.logStage1Event(
                            request.getSessionId(),
                            "HOLD_FAILED",
                            Map.of("reason", "HELD_BY_OTHERS", "conflictSeatId", seatId),
                            "FAIL", "Seat already held by another session"
                    );

                    cacheIfKeyed(idempotencyKey, failResponse);
                    return failResponse;
                }
            }

            // 4. All available → HOLD all seats atomically
            String holdId = UUID.randomUUID().toString();
            Instant now = Instant.now();
            Instant expiresAt = now.plusMillis(HOLD_DURATION_MS);

            for (String seatId : request.getSeatIds()) {
                seatStatus.put(seatId, request.getSessionId());
            }

            Hold hold = Hold.builder()
                    .holdId(holdId)
                    .sessionId(request.getSessionId())
                    .gameId(request.getGameId())
                    .seatIds(new ArrayList<>(request.getSeatIds()))
                    .status(Hold.HoldStatus.ACTIVE)
                    .expiresAt(expiresAt)
                    .createdAt(now)
                    .build();

            holdStore.put(holdId, hold);
            activeHolds.put(request.getSessionId(), holdId);

            HoldResponse successResponse = HoldResponse.builder()
                    .holdId(holdId)
                    .status("SUCCESS")
                    .expiresAt(expiresAt)
                    .build();

            auditLogger.logStage1Event(
                    request.getSessionId(),
                    "HOLD_SUCCEEDED",
                    Map.of("holdId", holdId, "seatIds", request.getSeatIds()),
                    "OK", null
            );

            log.info("Hold succeeded: {} for session {} with {} seats",
                    holdId, request.getSessionId(), request.getSeatIds().size());

            cacheIfKeyed(idempotencyKey, successResponse);
            return successResponse;

        } finally {
            holdLock.unlock();
        }
    }

    // ─── Order Creation ───

    public OrderResponse createOrder(OrderRequest request) {
        Hold hold = holdStore.get(request.getHoldId());
        if (hold == null || hold.getStatus() != Hold.HoldStatus.ACTIVE) {
            return OrderResponse.builder()
                    .orderId(null)
                    .holdId(request.getHoldId())
                    .status("INVALID_HOLD")
                    .build();
        }

        if (hold.isExpired()) {
            hold.setStatus(Hold.HoldStatus.EXPIRED);
            return OrderResponse.builder()
                    .orderId(null)
                    .holdId(request.getHoldId())
                    .status("HOLD_EXPIRED")
                    .build();
        }

        String orderId = UUID.randomUUID().toString();
        Instant now = Instant.now();
        int pricePerSeat = 25000; // mock price
        int totalPrice = pricePerSeat * hold.getSeatIds().size();

        Order order = Order.builder()
                .orderId(orderId)
                .holdId(request.getHoldId())
                .sessionId(hold.getSessionId())
                .gameId(hold.getGameId())
                .seatIds(new ArrayList<>(hold.getSeatIds()))
                .totalPrice(totalPrice)
                .expiresAt(now.plusSeconds(300)) // 5-minute payment window
                .status(Order.OrderStatus.ACTIVE)
                .createdAt(now)
                .build();

        orderStore.put(orderId, order);

        // Clear active hold so this session can make new reservations
        activeHolds.remove(hold.getSessionId());
        // Release seat status (seats are now "ordered", not just "held")
        hold.getSeatIds().forEach(seatStatus::remove);
        hold.setStatus(Hold.HoldStatus.EXPIRED); // consumed

        log.info("Order created: {} from hold {} ({}원, expires {})", orderId, request.getHoldId(), totalPrice, order.getExpiresAt());

        return OrderResponse.builder()
                .orderId(orderId)
                .holdId(request.getHoldId())
                .status("ACTIVE")
                .build();
    }

    // ─── Order Access ───

    public Order getOrder(String orderId) {
        return orderStore.get(orderId);
    }

    /**
     * Mask phone: 01012345678 → 010-****-5678
     */
    public String maskPhone(String phone) {
        if (phone == null || phone.length() < 10) return phone;
        String last4 = phone.substring(phone.length() - 4);
        String prefix = phone.substring(0, 3);
        return prefix + "-****-" + last4;
    }

    // ─── Helpers ───

    private void cacheIfKeyed(String key, HoldResponse response) {
        if (key != null) {
            idempotencyCache.put(key, response);
        }
    }

    // Exposed for testing
    public ConcurrentHashMap<String, String> getSeatStatus() {
        return seatStatus;
    }
}

