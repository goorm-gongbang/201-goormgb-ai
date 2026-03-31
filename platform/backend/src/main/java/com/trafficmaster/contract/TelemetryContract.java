package com.trafficmaster.contract;

/**
 * Telemetry/audit contract constants shared inside backend.
 */
public final class TelemetryContract {

    private TelemetryContract() {}

    public static final String STAGE_TELEMETRY = "TELEMETRY";
    public static final String EVENT_BEHAVIOR = "BEHAVIOR";
    public static final String ACTOR_USER = "USER";

    public static final String TRIGGER_UNKNOWN = "unknown";
    public static final String SESSION_ANONYMOUS = "anonymous";

    public static final String PAYLOAD_TRIGGER = "trigger";
    public static final String PAYLOAD_FEATURES = "features";
    public static final String PAYLOAD_RAW_POINTS = "rawPoints";
    public static final String PAYLOAD_COUNT = "count";
    public static final String PAYLOAD_DATASET_ID = "datasetId";
}

