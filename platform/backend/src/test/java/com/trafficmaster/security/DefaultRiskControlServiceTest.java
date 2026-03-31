package com.trafficmaster.security;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;

import org.junit.jupiter.api.Test;

class DefaultRiskControlServiceTest {

    @Test
    void botLikeTelemetryIsBlocked() {
        BehaviorTelemetryStore store = new BehaviorTelemetryStore();
        DefaultRiskControlService svc = new DefaultRiskControlService(store);

        store.record("sess-bot", Map.of(
                "totalDist", 120.0,
                "linearDist", 120.0,
                "tremorStdDev", 0.0
        ));

        assertEquals(RiskDecision.BLOCKED, svc.decide("sess-bot"));
    }

    @Test
    void humanLikeTelemetryIsAllowed() {
        BehaviorTelemetryStore store = new BehaviorTelemetryStore();
        DefaultRiskControlService svc = new DefaultRiskControlService(store);

        store.record("sess-human", Map.of(
                "totalDist", 120.0,
                "linearDist", 100.0, // extraDist=20px (curved/noisy)
                "tremorStdDev", 0.35
        ));

        assertEquals(RiskDecision.NONE, svc.decide("sess-human"));
    }
}

