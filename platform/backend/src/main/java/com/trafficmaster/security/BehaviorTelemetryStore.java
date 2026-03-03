package com.trafficmaster.security;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

/**
 * In-memory store for behavioral telemetry (per session).
 *
 * MVP scope:
 * - last-write-wins snapshot per sessionId
 * - no persistence; intended for local test-mode defense gating
 */
@Component
public class BehaviorTelemetryStore {

    private final ConcurrentHashMap<String, Snapshot> latestBySession = new ConcurrentHashMap<>();

    public void record(String sessionId, Map<String, Object> features) {
        if (sessionId == null || sessionId.isBlank()) return;
        if (features == null || features.isEmpty()) return;
        latestBySession.put(sessionId, Snapshot.from(features));
    }

    public Optional<Snapshot> latest(String sessionId) {
        if (sessionId == null || sessionId.isBlank()) return Optional.empty();
        return Optional.ofNullable(latestBySession.get(sessionId));
    }

    public record Snapshot(
            Instant receivedAt,
            Double totalDist,
            Double linearDist,
            Double linearityRatio,
            Double avgVelocity,
            Double tremorStdDev,
            Double dwellTime,
            Long timestamp
    ) {
        static Snapshot from(Map<String, Object> features) {
            return new Snapshot(
                    Instant.now(),
                    asDouble(features.get("totalDist")),
                    asDouble(features.get("linearDist")),
                    asDouble(features.get("linearityRatio")),
                    asDouble(features.get("avgVelocity")),
                    asDouble(features.get("tremorStdDev")),
                    asDouble(features.get("dwellTime")),
                    asLong(features.get("timestamp"))
            );
        }

        private static Double asDouble(Object v) {
            if (v == null) return null;
            if (v instanceof Number n) return n.doubleValue();
            if (v instanceof String s) {
                try {
                    return Double.parseDouble(s.trim());
                } catch (NumberFormatException ignored) {
                    return null;
                }
            }
            return null;
        }

        private static Long asLong(Object v) {
            if (v == null) return null;
            if (v instanceof Number n) return n.longValue();
            if (v instanceof String s) {
                try {
                    return Long.parseLong(s.trim());
                } catch (NumberFormatException ignored) {
                    return null;
                }
            }
            return null;
        }
    }
}

