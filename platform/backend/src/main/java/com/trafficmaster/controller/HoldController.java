package com.trafficmaster.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.dto.HoldRequest;
import com.trafficmaster.dto.HoldResponse;
import com.trafficmaster.seat.SeatService;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

/**
 * Stage 4/5 SSOT: POST /api/holds — Atomic seat hold.
 * Requires Idempotency-Key header per SSOT contract.
 */
@RestController
@RequestMapping("/api/holds")
@RequiredArgsConstructor
public class HoldController {

    private final SeatService seatService;

    @PostMapping
    public ResponseEntity<HoldResponse> holdSeats(
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            @Valid @RequestBody HoldRequest request) {

        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            return ResponseEntity.badRequest().body(
                    HoldResponse.builder()
                            .status("FAIL")
                            .reason("MISSING_IDEMPOTENCY_KEY")
                            .build()
            );
        }

        HoldResponse response = seatService.holdSeats(request, idempotencyKey);

        if ("FAIL".equals(response.getStatus())) {
            return ResponseEntity.status(409).body(response);
        }

        return ResponseEntity.ok(response);
    }
}
