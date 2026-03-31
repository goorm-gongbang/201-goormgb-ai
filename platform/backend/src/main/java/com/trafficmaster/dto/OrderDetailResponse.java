package com.trafficmaster.dto;

import java.time.Instant;
import java.util.List;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class OrderDetailResponse {
    private String orderId;
    private String gameId;
    private String status;
    private List<String> seatIds;
    private int totalPrice;
    private String maskedPhone;
    private Instant expiresAt;
    private Instant createdAt;

    // Game info (mock)
    private String gameTitle;
    private String gameDate;
    private String venue;
}
