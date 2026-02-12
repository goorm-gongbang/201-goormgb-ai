package com.trafficmaster.seat;

import java.time.Instant;
import java.util.List;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Order entity — created from a valid Hold.
 * Extended for Stage 6: includes game/seat/price info and tax phone.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Order {
    private String orderId;
    private String holdId;
    private String sessionId;

    // Game & seat info (populated from Hold)
    private String gameId;
    private List<String> seatIds;
    private int totalPrice;

    // Tax deduction
    private String maskedPhone;

    // Expiry (5-min payment window)
    private Instant expiresAt;

    @Builder.Default
    private OrderStatus status = OrderStatus.ACTIVE;

    private Instant createdAt;

    public enum OrderStatus {
        ACTIVE, PAID, CANCELLED, EXPIRED
    }

    public boolean isPaymentExpired() {
        return expiresAt != null && Instant.now().isAfter(expiresAt);
    }
}
