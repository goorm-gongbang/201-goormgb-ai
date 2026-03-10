package com.trafficmaster.controller;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.OrderDetailResponse;
import com.trafficmaster.dto.OrderRequest;
import com.trafficmaster.dto.OrderResponse;
import com.trafficmaster.dto.TaxPhoneRequest;
import com.trafficmaster.seat.Order;
import com.trafficmaster.seat.SeatService;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

/**
 * Stage 4/5: POST /api/orders — create order from valid hold.
 * Stage 6:   GET /api/orders/{id} — order detail.
 *            PATCH /api/orders/{id}/tax — update tax phone.
 */
@RestController
@RequestMapping("/api/orders")
@RequiredArgsConstructor
public class OrderController {

    private final SeatService seatService;
    private final DecisionAuditLogger auditLogger;

    @PostMapping
    public ResponseEntity<OrderResponse> createOrder(
            @Valid @RequestBody OrderRequest request) {
        OrderResponse response = seatService.createOrder(request);

        if ("INVALID_HOLD".equals(response.getStatus()) || "HOLD_EXPIRED".equals(response.getStatus())) {
            return ResponseEntity.badRequest().body(response);
        }

        return ResponseEntity.ok(response);
    }

    @GetMapping("/{orderId}")
    public ResponseEntity<OrderDetailResponse> getOrder(@PathVariable String orderId) {
        Order order = seatService.getOrder(orderId);
        if (order == null) {
            return ResponseEntity.notFound().build();
        }

        // Check & update expired status
        if (order.getStatus() == Order.OrderStatus.ACTIVE && order.isPaymentExpired()) {
            order.setStatus(Order.OrderStatus.EXPIRED);
        }

        OrderDetailResponse detail = OrderDetailResponse.builder()
                .orderId(order.getOrderId())
                .gameId(order.getGameId())
                .status(order.getStatus().name())
                .seatIds(order.getSeatIds())
                .totalPrice(order.getTotalPrice())
                .maskedPhone(order.getMaskedPhone())
                .expiresAt(order.getExpiresAt())
                .createdAt(order.getCreatedAt())
                // Mock game info
                .gameTitle("KT vs LG")
                .gameDate("2026.03.28(토) 14:00")
                .venue("잠실 야구장")
                .build();

        return ResponseEntity.ok(detail);
    }

    @PatchMapping("/{orderId}/tax")
    public ResponseEntity<?> updateTaxPhone(
            @PathVariable String orderId,
            @Valid @RequestBody TaxPhoneRequest request) {
        Order order = seatService.getOrder(orderId);
        if (order == null) {
            return ResponseEntity.notFound().build();
        }

        String masked = seatService.maskPhone(request.getPhone());
        order.setMaskedPhone(masked);

        auditLogger.logStage1Event(
                order.getSessionId(),
                "TAX_DEDUCTION_PHONE_UPDATED",
                Map.of("orderId", orderId, "maskedPhone", masked),
                "OK", null);

        return ResponseEntity.ok(Map.of("maskedPhone", masked));
    }
}
