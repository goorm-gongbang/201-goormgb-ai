package com.trafficmaster.security;

/**
 * Risk assessment interface.
 * MVP: telemetry-based thresholding in TM_TEST_MODE.
 * Production: integrate with ML anomaly detection.
 */
public interface RiskControlService {

    /**
     * Decide what security action should be taken for this session.
     * @param sessionId user session identifier
     * @return decision (NONE/CHALLENGE_REQUIRED/BLOCKED)
     */
    RiskDecision decide(String sessionId);
}
