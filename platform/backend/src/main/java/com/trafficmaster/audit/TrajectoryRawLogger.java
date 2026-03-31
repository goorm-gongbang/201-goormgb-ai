package com.trafficmaster.audit;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.annotation.PostConstruct;

/**
 * Append-only JSONL logger for R&D-only raw mouse trajectories.
 *
 * IMPORTANT:
 * - This must remain opt-in from the frontend (localStorage toggle).
 * - Do NOT write raw points into decision_audit.jsonl; keep it in a separate file
 *   to avoid large logs and accidental sharing.
 */
@Component
public class TrajectoryRawLogger {

    private static final Logger log = LoggerFactory.getLogger(TrajectoryRawLogger.class);

    private final ObjectMapper mapper;
    private final Path logPath;

    public TrajectoryRawLogger(
            @Value("${trafficmaster.audit.raw-trajectory-log-path:logs/trajectory_raw.jsonl}") String logPathStr) {
        this.logPath = Paths.get(logPathStr);
        this.mapper = new ObjectMapper();
    }

    @PostConstruct
    public void init() throws IOException {
        Files.createDirectories(logPath.getParent());
        if (!Files.exists(logPath)) {
            Files.createFile(logPath);
        }
        log.info("TrajectoryRawLogger initialized: {}", logPath.toAbsolutePath());
    }

    public synchronized void log(TrajectoryRawEvent event) {
        try (BufferedWriter writer = Files.newBufferedWriter(logPath,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
            writer.write(mapper.writeValueAsString(event));
            writer.newLine();
            writer.flush();
        } catch (IOException e) {
            log.error("Failed to write raw trajectory event: {}", e.getMessage(), e);
        }
    }

    public record TrajectoryRawEvent(
            long tsMs,
            String sessionId,
            String datasetId,
            String trigger,
            String requestId,
            String correlationId,
            Map<String, Object> features,
            List<Map<String, Object>> points
    ) {}
}

