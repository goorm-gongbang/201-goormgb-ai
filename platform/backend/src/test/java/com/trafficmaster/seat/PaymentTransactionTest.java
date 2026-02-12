package com.trafficmaster.seat;

import static org.junit.jupiter.api.Assertions.*;

import java.io.File;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.HoldRequest;
import com.trafficmaster.dto.OrderRequest;
import com.trafficmaster.dto.OrderResponse;
import com.trafficmaster.dto.PaymentRequest;
import com.trafficmaster.dto.PaymentResponse;

/**
 * Stage 6: Payment transaction tests.
 */
class PaymentTransactionTest {

    private SeatService seatService;
    private PaymentService paymentService;
    private DecisionAuditLogger auditLogger;

    @BeforeEach
    void setup() throws Exception {
        File tmpLog = File.createTempFile("payment-test-audit", ".jsonl");
        tmpLog.deleteOnExit();
        auditLogger = new DecisionAuditLogger(tmpLog.getAbsolutePath());
        seatService = new SeatService(auditLogger);
        paymentService = new PaymentService(auditLogger, seatService);
    }

    private String createActiveOrder() {
        // 1. Create hold
        HoldRequest holdReq = HoldRequest.builder()
                .sessionId("s-pay-" + UUID.randomUUID().toString().substring(0, 8))
                .gameId("game-001")
                .mode("RECOMMEND")
                .seatBundleId("bundle-pay")
                .seatIds(List.of("pay-S1", "pay-S2"))
                .build();
        var holdRes = seatService.holdSeats(holdReq, null);
        assertEquals("SUCCESS", holdRes.getStatus());

        // 2. Create order
        OrderRequest orderReq = OrderRequest.builder()
                .holdId(holdRes.getHoldId())
                .build();
        OrderResponse orderRes = seatService.createOrder(orderReq);
        assertEquals("ACTIVE", orderRes.getStatus());
        return orderRes.getOrderId();
    }

    @Test
    @DisplayName("Happy path: payment succeeds → SUCCEEDED, order PAID")
    void happyPath() {
        String orderId = createActiveOrder();

        PaymentResponse res = paymentService.processPayment(
                PaymentRequest.builder().orderId(orderId).method("TOSS").build(),
                UUID.randomUUID().toString(), null);

        assertEquals("SUCCEEDED", res.getStatus());
        assertNotNull(res.getPaymentId());

        Order order = seatService.getOrder(orderId);
        assertEquals(Order.OrderStatus.PAID, order.getStatus());
    }

    @Test
    @DisplayName("Forced failure via test hook → FAILED, PAYMENT_FAILED reason")
    void testHookFailure() {
        String orderId = createActiveOrder();

        PaymentResponse res = paymentService.processPayment(
                PaymentRequest.builder().orderId(orderId).method("TOSS").build(),
                UUID.randomUUID().toString(), "1.0"); // 100% fail rate

        assertEquals("FAILED", res.getStatus());
        assertEquals("PAYMENT_FAILED", res.getReasonCode());

        Order order = seatService.getOrder(orderId);
        assertEquals(Order.OrderStatus.ACTIVE, order.getStatus()); // not PAID
    }

    @Test
    @DisplayName("Expired order → EXPIRED status")
    void expiredOrder() {
        String orderId = createActiveOrder();
        // Manually set expiresAt to the past
        Order order = seatService.getOrder(orderId);
        order.setExpiresAt(Instant.now().minusSeconds(10));

        PaymentResponse res = paymentService.processPayment(
                PaymentRequest.builder().orderId(orderId).method("TOSS").build(),
                UUID.randomUUID().toString(), null);

        assertEquals("EXPIRED", res.getStatus());
        assertEquals("PAYMENT_WINDOW_EXPIRED", res.getReasonCode());
    }

    @Test
    @DisplayName("Idempotency: same key returns cached result")
    void idempotency() {
        String orderId = createActiveOrder();
        String key = UUID.randomUUID().toString();

        PaymentResponse first = paymentService.processPayment(
                PaymentRequest.builder().orderId(orderId).method("TOSS").build(),
                key, null);
        assertEquals("SUCCEEDED", first.getStatus());

        PaymentResponse second = paymentService.processPayment(
                PaymentRequest.builder().orderId(orderId).method("TOSS").build(),
                key, null);

        // Same cached result
        assertEquals(first.getPaymentId(), second.getPaymentId());
        assertEquals(first.getStatus(), second.getStatus());
    }

    @Test
    @DisplayName("Already paid order → FAILED, ALREADY_PAID reason")
    void alreadyPaid() {
        String orderId = createActiveOrder();

        // First payment succeeds
        paymentService.processPayment(
                PaymentRequest.builder().orderId(orderId).method("TOSS").build(),
                UUID.randomUUID().toString(), null);

        // Second payment with different key → ALREADY_PAID
        PaymentResponse res = paymentService.processPayment(
                PaymentRequest.builder().orderId(orderId).method("TOSS").build(),
                UUID.randomUUID().toString(), null);

        assertEquals("FAILED", res.getStatus());
        assertEquals("ALREADY_PAID", res.getReasonCode());
    }

    @Test
    @DisplayName("Non-existent order → ORDER_NOT_FOUND")
    void orderNotFound() {
        PaymentResponse res = paymentService.processPayment(
                PaymentRequest.builder().orderId("fake-order").method("TOSS").build(),
                UUID.randomUUID().toString(), null);

        assertEquals("FAILED", res.getStatus());
        assertEquals("ORDER_NOT_FOUND", res.getReasonCode());
    }
}
