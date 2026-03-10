package com.trafficmaster.dto;

import java.time.Instant;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class HoldResponse {
    private String holdId;
    private String status;   // "SUCCESS" | "FAIL"
    private Instant expiresAt;
    private String reason;   // null | "HELD_BY_OTHERS" | "SOLD_OUT" | "ALREADY_HAS_ACTIVE_HOLD"
}
