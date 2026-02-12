package com.trafficmaster.audit;

import java.time.Instant;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Audit event record conforming to Addendum (Level 0) telemetry.fields schema.
 * Written to decision_audit.jsonl as append-only JSONL.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class AuditEvent {

    @Builder.Default
    private Instant ts = Instant.now();

    private String sessionId;
    private String stage;
    private String eventType;

    @Builder.Default
    private String actor = "USER";

    private String requestId;
    private String correlationId;
    private Map<String, Object> payload;
    private ServerDecision serverDecision;
    private Result result;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ServerDecision {
        @Builder.Default
        private String riskTier = "T0";
        @Builder.Default
        private String action = "NONE";
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Result {
        private String status;
        private String reasonCode;
    }
}
