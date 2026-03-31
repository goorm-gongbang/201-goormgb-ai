package com.trafficmaster.controller;

import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.audit.AuditEvent;
import com.trafficmaster.audit.DecisionAuditLogger;

import lombok.RequiredArgsConstructor;

/**
 * Stage 7: Client-side event log collector.
 * POST /api/logs — receives batched client events.
 */
@RestController
@RequestMapping("/api/logs")
@RequiredArgsConstructor
public class LogController {

    private static final Logger log = LoggerFactory.getLogger(LogController.class);
    private final DecisionAuditLogger auditLogger;

    @PostMapping
    public ResponseEntity<Map<String, String>> collectLogs(@RequestBody List<ClientEvent> events) {
        for (ClientEvent event : events) {
            auditLogger.log(AuditEvent.builder()
                    .sessionId(event.sessionId)
                    .stage("CLIENT")
                    .eventType(event.eventType)
                    .actor("USER")
                    .requestId(event.requestId)
                    .correlationId(event.correlationId)
                    .payload(event.payload)
                    .build());
        }
        log.debug("Collected {} client events", events.size());
        return ResponseEntity.ok(Map.of("status", "OK", "count", String.valueOf(events.size())));
    }

    static record ClientEvent(
            String sessionId,
            String eventType,
            String requestId,
            String correlationId,
            Map<String, Object> payload
    ) {}
}
