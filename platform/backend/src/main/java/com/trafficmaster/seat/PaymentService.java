package com.trafficmaster.seat;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ThreadLocalRandom;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.PaymentRequest;
import com.trafficmaster.dto.PaymentResponse;
import com.trafficmaster.security.SecurityService;

import lombok.RequiredArgsConstructor;

/**
 * Stage 6: Payment processing with idempotency, expiry check, and test hook.
 */
@Service
@RequiredArgsConstructor
public class PaymentService {

    private static final Logger log = LoggerFactory.getLogger(PaymentService.class);

    private final DecisionAuditLogger auditLogger;
    private final SeatService seatService;
    private final SecurityService securityService;

    private final ConcurrentHashMap<String, PaymentResponse> idempotencyCache = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Payment> paymentStore = new ConcurrentHashMap<>();

    /**
     * Process payment with idempotency, expiry check, and configurable failure.
     *
     * @param request        payment request
     * @param idempotencyKey from Idempotency-Key header
     * @param failRateHeader from X-TM-PaymentFailRate header (0.0-1.0), nullable
     */
    public PaymentResponse processPayment(PaymentRequest request, String idempotencyKey, String failRateHeader) {
        // 1. Idempotency check
        if (idempotencyKey != null) {
            PaymentResponse cached = idempotencyCache.get(idempotencyKey);
            if (cached != null) {
                log.info("Idempotent payment returned cached result for key: {}", idempotencyKey);
                return cached;
            }
        }

        // 2. Get order
        Order order = seatService.getOrder(request.getOrderId());
        if (order == null) {
            return buildAndCache(idempotencyKey, null, request.getOrderId(), "FAILED", "ORDER_NOT_FOUND", null);
        }

        String sessionId = order.getSessionId();

        // Log PAYMENT_SUBMITTED
        auditLogger.logStage1Event(sessionId, "PAYMENT_SUBMITTED",
                Map.of("orderId", request.getOrderId(), "method", request.getMethod()),
                "OK", null);

        // 3. Expiry check
        if (order.isPaymentExpired()) {
            order.setStatus(Order.OrderStatus.EXPIRED);
            auditLogger.logStage1Event(sessionId, "PAYMENT_FAILED",
                    Map.of("orderId", request.getOrderId(), "reason", "EXPIRED"),
                    "FAIL", "Payment window expired");
            return buildAndCache(idempotencyKey, null, request.getOrderId(), "EXPIRED", "PAYMENT_WINDOW_EXPIRED", sessionId);
        }

        // 4. Already paid check
        if (order.getStatus() == Order.OrderStatus.PAID) {
            return buildAndCache(idempotencyKey, null, request.getOrderId(), "FAILED", "ALREADY_PAID", sessionId);
        }

        // 5. Test hook — configurable failure rate
        double failRate = parseFailRate(failRateHeader);
        if (failRate > 0 && ThreadLocalRandom.current().nextDouble() < failRate) {
            Payment failedPayment = Payment.builder()
                    .paymentId(UUID.randomUUID().toString())
                    .orderId(request.getOrderId())
                    .sessionId(sessionId)
                    .amount(order.getTotalPrice())
                    .method(request.getMethod())
                    .status(Payment.PaymentStatus.FAILED)
                    .reasonCode("PAYMENT_FAILED")
                    .createdAt(Instant.now())
                    .build();
            paymentStore.put(failedPayment.getPaymentId(), failedPayment);

            auditLogger.logStage1Event(sessionId, "PAYMENT_FAILED",
                    Map.of("orderId", request.getOrderId(), "paymentId", failedPayment.getPaymentId(),
                            "reason", "PAYMENT_FAILED"),
                    "FAIL", "Mock PG failure via test hook");

            log.info("Payment FAILED (test hook): {} for order {}", failedPayment.getPaymentId(), request.getOrderId());

            return buildAndCache(idempotencyKey, failedPayment.getPaymentId(), request.getOrderId(), "FAILED", "PAYMENT_FAILED", sessionId);
        }

        // 6. Success — update order to PAID, commit hold
        Payment payment = Payment.builder()
                .paymentId(UUID.randomUUID().toString())
                .orderId(request.getOrderId())
                .sessionId(sessionId)
                .amount(order.getTotalPrice())
                .method(request.getMethod())
                .status(Payment.PaymentStatus.SUCCEEDED)
                .createdAt(Instant.now())
                .build();
        paymentStore.put(payment.getPaymentId(), payment);

        order.setStatus(Order.OrderStatus.PAID);

        auditLogger.logStage1Event(sessionId, "PAYMENT_SUCCEEDED",
                Map.of("orderId", request.getOrderId(), "paymentId", payment.getPaymentId(),
                        "amount", order.getTotalPrice(), "method", request.getMethod()),
                "OK", null);

        log.info("Payment SUCCEEDED: {} for order {} ({}원)", payment.getPaymentId(), request.getOrderId(), order.getTotalPrice());

        // Reset security verification so next booking triggers a fresh challenge
        securityService.resetVerification(sessionId);

        return buildAndCache(idempotencyKey, payment.getPaymentId(), request.getOrderId(), "SUCCEEDED", null, sessionId);
    }

    // ─── Helpers ───

    private PaymentResponse buildAndCache(String idempotencyKey, String paymentId, String orderId, String status, String reasonCode, String sessionId) {
        PaymentResponse response = PaymentResponse.builder()
                .paymentId(paymentId)
                .orderId(orderId)
                .status(status)
                .reasonCode(reasonCode)
                .build();

        if (idempotencyKey != null) {
            idempotencyCache.put(idempotencyKey, response);
        }
        return response;
    }

    private double parseFailRate(String header) {
        if (header == null || header.isBlank()) {
            // Check env var fallback
            String envVal = System.getenv("TM_PAYMENT_FAIL_RATE");
            if (envVal != null) {
                try { return Double.parseDouble(envVal); } catch (Exception e) { return 0; }
            }
            return 0;
        }
        try { return Double.parseDouble(header); } catch (Exception e) { return 0; }
    }

    // Exposed for testing
    public ConcurrentHashMap<String, Payment> getPaymentStore() {
        return paymentStore;
    }
}
