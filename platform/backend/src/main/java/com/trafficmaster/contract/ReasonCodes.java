package com.trafficmaster.contract;

/**
 * Centralized reasonCode constants for API error/decision contracts.
 */
public final class ReasonCodes {

    private ReasonCodes() {}

    public static final String HELD_BY_OTHERS = "HELD_BY_OTHERS";
    public static final String EXPIRED = "EXPIRED";
    public static final String BLOCKED = "BLOCKED";
    public static final String CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED";
    public static final String PAYMENT_FAILED = "PAYMENT_FAILED";
    public static final String INVALID_HOLD = "INVALID_HOLD";
    public static final String NOT_FOUND = "NOT_FOUND";
    public static final String VALIDATION_ERROR = "VALIDATION_ERROR";
    public static final String INTERNAL_ERROR = "INTERNAL_ERROR";
    public static final String MISSING_IDEMPOTENCY_KEY = "MISSING_IDEMPOTENCY_KEY";
}

