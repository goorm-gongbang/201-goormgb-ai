package com.trafficmaster.controller;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.trafficmaster.audit.TrajectoryRawLogger;
import com.trafficmaster.audit.AuditEvent;
import com.trafficmaster.audit.DecisionAuditLogger;

import lombok.RequiredArgsConstructor;

/**
 * Stage 7: Behavioral telemetry collector.
 *
 * Contract-first endpoint for FE/agent "behavior features".
 * POST /api/telemetry/behavior
 */
@RestController
@RequestMapping("/api/telemetry")
@RequiredArgsConstructor
public class TelemetryController {

    private static final Logger log = LoggerFactory.getLogger(TelemetryController.class);
    private final DecisionAuditLogger auditLogger;
    private final TrajectoryRawLogger rawLogger;
    private final com.trafficmaster.security.BehaviorTelemetryStore telemetryStore;

    @PostMapping("/behavior")
    public ResponseEntity<Map<String, String>> collectBehavior(@RequestBody TelemetryBehaviorRequest request) {
        String sessionId = request.sessionId != null && !request.sessionId.isBlank()
                ? request.sessionId
                : "anonymous";
        String trigger = request.trigger != null && !request.trigger.isBlank()
                ? request.trigger
                : "unknown";
        String datasetId = request.datasetId != null ? request.datasetId : "";
        String requestId = request.requestId != null && !request.requestId.isBlank()
                ? request.requestId
                : UUID.randomUUID().toString();

        Map<String, Object> payload = new HashMap<>();
        payload.put("trigger", trigger);
        if (request.features != null) {
            payload.put("features", request.features);
        }
        if (request.points != null && !request.points.isEmpty()) {
            payload.put("rawPoints", Map.of(
                    "count", request.points.size(),
                    "datasetId", datasetId
            ));
        }

        if (request.features != null) {
            telemetryStore.record(sessionId, request.features);
        }

        if (request.points != null && !request.points.isEmpty()) {
            rawLogger.log(new TrajectoryRawLogger.TrajectoryRawEvent(
                    System.currentTimeMillis(),
                    sessionId,
                    datasetId,
                    trigger,
                    requestId,
                    request.correlationId,
                    request.features,
                    request.points
            ));
        }

        auditLogger.log(AuditEvent.builder()
                .sessionId(sessionId)
                .stage("TELEMETRY")
                .eventType("BEHAVIOR")
                .actor("USER")
                .requestId(requestId)
                .correlationId(request.correlationId)
                .payload(payload)
                .build());

        log.debug("Collected telemetry behavior: sessionId={} trigger={}", sessionId, trigger);
        return ResponseEntity.ok(Map.of("status", "OK"));
    }

    static record TelemetryBehaviorRequest(
            @JsonAlias("session_id") String sessionId,
            String trigger,
            Map<String, Object> features,
            List<Map<String, Object>> points,
            @JsonAlias("dataset_id") String datasetId,
            @JsonAlias("request_id") String requestId,
            @JsonAlias("correlation_id") String correlationId
    ) {}
}
