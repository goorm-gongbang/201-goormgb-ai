package com.trafficmaster.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.contract.ReasonCodes;
import com.trafficmaster.contract.TmHeaders;
import com.trafficmaster.dto.PaymentRequest;
import com.trafficmaster.dto.PaymentResponse;
import com.trafficmaster.seat.PaymentService;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

/**
 * Stage 6: POST /api/payments — process payment with idempotency.
 */
@RestController
@RequestMapping("/api/payments")
@RequiredArgsConstructor
public class PaymentController {

    private final PaymentService paymentService;

    @PostMapping
    public ResponseEntity<PaymentResponse> processPayment(
            @Valid @RequestBody PaymentRequest request,
            @RequestHeader(value = TmHeaders.IDEMPOTENCY_KEY, required = false) String idempotencyKey,
            @RequestHeader(value = TmHeaders.X_TM_PAYMENT_FAIL_RATE, required = false) String failRateHeader) {

        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            return ResponseEntity.badRequest().body(
                    PaymentResponse.builder()
                            .orderId(request.getOrderId())
                            .status("FAILED")
                            .reasonCode(ReasonCodes.MISSING_IDEMPOTENCY_KEY)
                            .build());
        }

        PaymentResponse response = paymentService.processPayment(request, idempotencyKey, failRateHeader);

        if ("SUCCEEDED".equals(response.getStatus())) {
            return ResponseEntity.ok(response);
        } else {
            return ResponseEntity.status(409).body(response);
        }
    }
}
