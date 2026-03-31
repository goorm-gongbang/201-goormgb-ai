package com.trafficmaster.security;

import java.time.Duration;
import java.time.Instant;

import org.springframework.stereotype.Service;

import lombok.RequiredArgsConstructor;

/**
 * MVP: telemetry-threshold risk control.
 *
 * Goal (AC-4):
 * - Straight-line / low-noise mouse patterns should get CHALLENGE_REQUIRED or BLOCKED.
 * - Human-ish movement should pass.
 *
 * Note: This is a demo-only heuristic, scoped to local TM_TEST_MODE.
 */
@Service
@RequiredArgsConstructor
public class DefaultRiskControlService implements RiskControlService {

    // Keep telemetry "fresh enough" but still valid across queue waits in demo.
    private static final long MAX_TELEMETRY_AGE_MS = 120_000;

    // Conservative thresholds: only near-perfect straight lines should trigger.
    private static final double MIN_TOTAL_DIST_PX = 80.0;
    private static final double MAX_EXTRA_DIST_PX = 0.8; // totalDist - linearDist
    private static final double MAX_TREMOR_STDDEV = 0.08;

    private final BehaviorTelemetryStore telemetryStore;

    @Override
    public RiskDecision decide(String sessionId) {
        var snapOpt = telemetryStore.latest(sessionId);
        if (snapOpt.isEmpty()) return RiskDecision.NONE;

        var snap = snapOpt.get();
        Instant receivedAt = snap.receivedAt();
        if (receivedAt == null) return RiskDecision.NONE;

        long ageMs = Duration.between(receivedAt, Instant.now()).toMillis();
        if (ageMs > MAX_TELEMETRY_AGE_MS) return RiskDecision.NONE;

        Double total = snap.totalDist();
        Double linear = snap.linearDist();
        Double tremor = snap.tremorStdDev();

        if (total == null || linear == null || tremor == null) return RiskDecision.NONE;
        if (total < MIN_TOTAL_DIST_PX) return RiskDecision.NONE;

        double extra = Math.max(0.0, total - linear);

        if (extra <= MAX_EXTRA_DIST_PX && tremor <= MAX_TREMOR_STDDEV) {
            // MVP: hard block near-perfect bot movement.
            return RiskDecision.BLOCKED;
        }

        return RiskDecision.NONE;
    }
}
