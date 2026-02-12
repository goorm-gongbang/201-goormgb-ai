package com.trafficmaster.security;

import org.springframework.stereotype.Service;

/**
 * MVP stub: never triggers security challenge automatically.
 * Production: plug in ML-based anomaly detection.
 */
@Service
public class DefaultRiskControlService implements RiskControlService {

    @Override
    public boolean shouldTriggerChallenge(String sessionId) {
        return false;
    }
}
