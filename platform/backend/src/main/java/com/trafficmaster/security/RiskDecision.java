package com.trafficmaster.security;

/**
 * MVP risk decision used by defense gating.
 *
 * - NONE: allow the request
 * - CHALLENGE_REQUIRED: force security challenge (428)
 * - BLOCKED: block the request (403)
 */
public enum RiskDecision {
    NONE,
    CHALLENGE_REQUIRED,
    BLOCKED
}

