package com.trafficmaster.seat;

import java.time.Instant;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Stage 6: Payment entity.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Payment {
    private String paymentId;
    private String orderId;
    private String sessionId;
    private int amount;
    private String method; // TOSS, KAKAO, NAVER, CARD

    @Builder.Default
    private PaymentStatus status = PaymentStatus.PENDING;

    private String reasonCode; // only set on FAILED
    private Instant createdAt;

    public enum PaymentStatus {
        PENDING, SUCCEEDED, FAILED
    }
}
