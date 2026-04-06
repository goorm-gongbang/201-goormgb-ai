-- Engine: PostgreSQL
-- Canonical source: specs/40-db-build-agent-pack/07-policy-control-plane-minimum-ddl.md
-- Note: runtime direct PostgreSQL read is out of scope; Redis projection remains the runtime read path.

CREATE TABLE IF NOT EXISTS policy_versions (
    policy_version TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL,
    source_type TEXT NOT NULL,
    parent_policy_version TEXT NULL,
    document_json JSONB NOT NULL,
    validation_result_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validated_at TIMESTAMPTZ NULL,
    activated_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS policy_rollout_state (
    rollout_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    base_policy_version TEXT NOT NULL,
    candidate_policy_version TEXT NULL,
    ratio NUMERIC(6,5) NOT NULL,
    evaluation_window_seconds INTEGER NOT NULL,
    canary_duration_seconds INTEGER NOT NULL,
    expand_step_index INTEGER NULL,
    stage_started_at_ms BIGINT NOT NULL,
    updated_at_ms BIGINT NOT NULL,
    current_status TEXT NOT NULL,
    rollback_reason TEXT NULL
);

CREATE TABLE IF NOT EXISTS policy_rollout_events (
    event_id TEXT PRIMARY KEY,
    rollout_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    base_policy_version TEXT NOT NULL,
    candidate_policy_version TEXT NULL,
    stage_before TEXT NULL,
    stage_after TEXT NULL,
    ratio_before NUMERIC(6,5) NULL,
    ratio_after NUMERIC(6,5) NULL,
    reason_json JSONB NULL,
    metrics_snapshot_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS policy_optimization_runs (
    run_id TEXT PRIMARY KEY,
    base_policy_version TEXT NOT NULL,
    proposed_policy_version TEXT NULL,
    trigger_type TEXT NOT NULL,
    metrics_snapshot_id TEXT NULL,
    window_start_ms BIGINT NULL,
    window_end_ms BIGINT NULL,
    metrics_snapshot_json JSONB NULL,
    proposal_json JSONB NULL,
    validation_result_json JSONB NULL,
    result_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL
);
