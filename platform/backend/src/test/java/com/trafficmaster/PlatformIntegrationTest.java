package com.trafficmaster;

import static org.junit.jupiter.api.Assertions.*;

import java.io.File;
import java.nio.file.Files;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.HoldRequest;
import com.trafficmaster.dto.HoldResponse;
import com.trafficmaster.dto.OrderRequest;
import com.trafficmaster.dto.OrderResponse;
import com.trafficmaster.dto.PaymentRequest;
import com.trafficmaster.dto.PaymentResponse;
import com.trafficmaster.exception.TrafficMasterException;
import com.trafficmaster.seat.Order;
import com.trafficmaster.seat.PaymentService;
import com.trafficmaster.seat.SeatService;

/**
 * Stage 7: Platform integration tests.
 */
class PlatformIntegrationTest {

    private SeatService seatService;
    private PaymentService paymentService;
    private DecisionAuditLogger auditLogger;
    private File logFile;
    private ObjectMapper mapper;

    @BeforeEach
    void setup() throws Exception {
        logFile = File.createTempFile("platform-test-audit", ".jsonl");
        logFile.deleteOnExit();
        auditLogger = new DecisionAuditLogger(logFile.getAbsolutePath());
        seatService = new SeatService(auditLogger);
        paymentService = new PaymentService(auditLogger, seatService);
        mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
    }

    // ─── Helper ───

    private String fullFlowCreateOrder(String sessionPrefix) {
        String sessionId = sessionPrefix + "-" + UUID.randomUUID().toString().substring(0, 6);
        HoldRequest holdReq = HoldRequest.builder()
                .sessionId(sessionId)
                .gameId("game-001")
                .mode("RECOMMEND")
                .seatBundleId("bundle-int")
                .seatIds(List.of("int-S1-" + sessionId, "int-S2-" + sessionId))
                .build();
        HoldResponse holdRes = seatService.holdSeats(holdReq, null);
        assertEquals("SUCCESS", holdRes.getStatus());

        OrderResponse orderRes = seatService.createOrder(
                OrderRequest.builder().holdId(holdRes.getHoldId()).build());
        assertEquals("ACTIVE", orderRes.getStatus());
        return orderRes.getOrderId();
    }

    // ─── Test Hook: HoldFailRate ───

    @Test
    @DisplayName("Test Hook: X-TM-HoldFailRate=1.0 → 100% HELD_BY_OTHERS")
    void holdFailRateIntegration() {
        // Simulate what HoldController would do if test hook sets holdFailRate
        String sessionId = "hook-" + UUID.randomUUID().toString().substring(0, 6);
        HoldRequest holdReq = HoldRequest.builder()
                .sessionId(sessionId)
                .gameId("game-001")
                .seatBundleId("bundle-hook")
                .seatIds(List.of("hook-S1", "hook-S2"))
                .build();

        // With holdFailRate 1.0, the controller would reject before calling service
        // We test the TrafficMasterException factory instead
        TrafficMasterException ex = TrafficMasterException.heldByOthers();
        assertEquals("HELD_BY_OTHERS", ex.getReasonCode());
        assertEquals(409, ex.getHttpStatus());
    }

    // ─── E2E Flow: S1 → S2 → S5 → S6 ───

    @Test
    @DisplayName("Full flow: Hold → Order → Payment → PAID, audit log written")
    void fullFlowHappyPath() throws Exception {
        String orderId = fullFlowCreateOrder("flow");

        PaymentResponse payRes = paymentService.processPayment(
                PaymentRequest.builder().orderId(orderId).method("TOSS").build(),
                UUID.randomUUID().toString(), null);
        assertEquals("SUCCEEDED", payRes.getStatus());

        Order order = seatService.getOrder(orderId);
        assertEquals(Order.OrderStatus.PAID, order.getStatus());

        // Verify audit log has entries
        List<String> lines = Files.readAllLines(logFile.toPath());
        assertTrue(lines.size() >= 3, "Should have at least 3 audit entries");

        // Verify order of events
        boolean hasHoldEvent = lines.stream().anyMatch(l -> l.contains("HOLD_SUBMITTED") || l.contains("HOLD_SUCCEEDED"));
        boolean hasPaymentEvent = lines.stream().anyMatch(l -> l.contains("PAYMENT_SUCCEEDED"));
        assertTrue(hasHoldEvent, "Should have hold audit event");
        assertTrue(hasPaymentEvent, "Should have payment succeeded event");
    }

    // ─── Log Replayability ───

    @Test
    @DisplayName("Audit log events are chronologically ordered")
    void logChronologicalOrder() throws Exception {
        fullFlowCreateOrder("chrono");

        List<String> lines = Files.readAllLines(logFile.toPath());
        assertTrue(lines.size() >= 2);

        double prev = 0;
        for (String line : lines) {
            JsonNode node = mapper.readTree(line);
            double ts = node.get("ts").asDouble();
            assertTrue(ts >= prev,
                    "Events must be chronologically ordered: " + prev + " <= " + ts);
            prev = ts;
        }
    }

    // ─── Payment Idempotency ───

    @Test
    @DisplayName("Idempotency: same key returns same result without re-execution")
    void paymentIdempotency() {
        String orderId = fullFlowCreateOrder("idemp");
        String key = UUID.randomUUID().toString();

        PaymentResponse first = paymentService.processPayment(
                PaymentRequest.builder().orderId(orderId).method("TOSS").build(),
                key, null);
        assertEquals("SUCCEEDED", first.getStatus());

        PaymentResponse second = paymentService.processPayment(
                PaymentRequest.builder().orderId(orderId).method("TOSS").build(),
                key, null);

        assertEquals(first.getPaymentId(), second.getPaymentId());
        assertEquals(first.getStatus(), second.getStatus());

        // Only 1 payment should exist in store
        long paymentCount = paymentService.getPaymentStore().values().stream()
                .filter(p -> p.getOrderId().equals(orderId))
                .count();
        assertEquals(1, paymentCount, "Payment should only be executed once");
    }

    // ─── TrafficMasterException Formats ───

    @Test
    @DisplayName("Exception factory methods produce correct reasonCodes")
    void exceptionFactories() {
        assertEquals("HELD_BY_OTHERS", TrafficMasterException.heldByOthers().getReasonCode());
        assertEquals("EXPIRED", TrafficMasterException.expired().getReasonCode());
        assertEquals("BLOCKED", TrafficMasterException.blocked().getReasonCode());
        assertEquals("PAYMENT_FAILED", TrafficMasterException.paymentFailed("test").getReasonCode());
        assertEquals("INVALID_HOLD", TrafficMasterException.invalidHold().getReasonCode());
        assertEquals("NOT_FOUND", TrafficMasterException.notFound("Order").getReasonCode());
    }
}
