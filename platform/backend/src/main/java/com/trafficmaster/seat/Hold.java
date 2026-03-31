package com.trafficmaster.seat;

import java.time.Instant;
import java.util.List;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Stage 4/5 SSOT: Hold — temporary seat reservation.
 * Status: ACTIVE → EXPIRED (timeout) | used for order creation.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Hold {
    private String holdId;
    private String sessionId;
    private String gameId;
    private List<String> seatIds;

    @Builder.Default
    private HoldStatus status = HoldStatus.ACTIVE;

    private Instant expiresAt;
    private Instant createdAt;

    public enum HoldStatus {
        ACTIVE, EXPIRED, FAILED
    }

    public boolean isExpired() {
        return expiresAt != null && Instant.now().isAfter(expiresAt);
    }
}
