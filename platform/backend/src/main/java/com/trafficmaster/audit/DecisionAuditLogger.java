package com.trafficmaster.audit;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import jakarta.annotation.PostConstruct;

/**
 * Append-only JSONL audit logger conforming to Addendum (Level 0)
 * telemetry.logSchema: "decision_audit.jsonl"
 *
 * Each line is a self-contained JSON object following the AuditEvent schema.
 */
@Component
public class DecisionAuditLogger {

    private static final Logger log = LoggerFactory.getLogger(DecisionAuditLogger.class);

    private final ObjectMapper mapper;
    private final Path logPath;

    public DecisionAuditLogger(
            @Value("${trafficmaster.audit.log-path:logs/decision_audit.jsonl}") String logPathStr) {
        this.logPath = Paths.get(logPathStr);
        this.mapper = new ObjectMapper();
        this.mapper.registerModule(new JavaTimeModule());
    }

    @PostConstruct
    public void init() throws IOException {
        Files.createDirectories(logPath.getParent());
        if (!Files.exists(logPath)) {
            Files.createFile(logPath);
        }
        log.info("DecisionAuditLogger initialized: {}", logPath.toAbsolutePath());
    }

    /**
     * Log an audit event. Thread-safe via synchronized write.
     */
    public synchronized void log(AuditEvent event) {
        try (BufferedWriter writer = Files.newBufferedWriter(logPath,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
            writer.write(mapper.writeValueAsString(event));
            writer.newLine();
            writer.flush();
        } catch (IOException e) {
            log.error("Failed to write audit event: {}", e.getMessage(), e);
        }
    }

    /**
     * Convenience method to log a Stage 1 event with standard fields.
     */
    public void logStage1Event(String sessionId, String eventType, Map<String, Object> payload,
                               String resultStatus, String reasonCode) {
        AuditEvent event = AuditEvent.builder()
                .sessionId(sessionId)
                .stage("S1")
                .eventType(eventType)
                .actor("USER")
                .requestId(UUID.randomUUID().toString())
                .payload(payload)
                .serverDecision(AuditEvent.ServerDecision.builder()
                        .riskTier("T0")
                        .action("NONE")
                        .build())
                .result(AuditEvent.Result.builder()
                        .status(resultStatus)
                        .reasonCode(reasonCode)
                        .build())
                .build();
        log(event);
    }

    /**
     * Returns the log file path (useful for testing).
     */
    public Path getLogPath() {
        return logPath;
    }
}
