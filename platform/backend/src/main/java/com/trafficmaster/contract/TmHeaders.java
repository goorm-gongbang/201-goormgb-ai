package com.trafficmaster.contract;

/**
 * Centralized HTTP header names used in Traffic-Master.
 */
public final class TmHeaders {

    private TmHeaders() {}

    public static final String X_CORRELATION_ID = "X-Correlation-Id";
    public static final String X_REQUEST_ID = "X-Request-Id";
    public static final String X_SESSION_ID = "X-Session-Id";
    public static final String X_TM_ACTOR = "X-TM-Actor";

    public static final String IDEMPOTENCY_KEY = "Idempotency-Key";

    public static final String X_TM_QUEUE_WAIT_MS = "X-TM-QueueWaitMs";
    public static final String X_TM_HOLD_FAIL_RATE = "X-TM-HoldFailRate";
    public static final String X_TM_PAYMENT_FAIL_RATE = "X-TM-PaymentFailRate";
    public static final String X_TM_FORCE_CHALLENGE = "X-TM-ForceChallenge";
}

