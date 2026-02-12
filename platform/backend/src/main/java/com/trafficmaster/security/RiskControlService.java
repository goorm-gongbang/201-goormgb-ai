package com.trafficmaster.security;

/**
 * Risk assessment interface.
 * MVP: always returns false (no challenge triggered).
 * Production: integrate with ML anomaly detection.
 */
public interface RiskControlService {

    /**
     * Evaluate whether a security challenge should be triggered for this session.
     * @param sessionId user session identifier
     * @return true if challenge should be triggered
     */
    boolean shouldTriggerChallenge(String sessionId);
}
