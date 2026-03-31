-- Defense analytics schema (MVP-1)
-- Strategy: fixed columns for common query dimensions + JSONB for evolving keys.
-- Note: numeric windows/retention/index policy are operationally tunable.

CREATE TABLE IF NOT EXISTS defense_decisions (
  id BIGSERIAL PRIMARY KEY,
  ts_ms BIGINT NOT NULL,
  session_id TEXT NOT NULL,
  trace_id TEXT,
  request_id TEXT,
  correlation_id TEXT,
  flow_state TEXT NOT NULL,
  defense_tier TEXT NOT NULL,
  action TEXT,
  reason_code TEXT,
  allow BOOLEAN NOT NULL,
  decision_id TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  risk_score DOUBLE PRECISION,
  rule_hits JSONB NOT NULL DEFAULT '[]'::jsonb,
  details_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_defense_decisions_ts
  ON defense_decisions (ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_defense_decisions_session
  ON defense_decisions (session_id);
CREATE INDEX IF NOT EXISTS idx_defense_decisions_tier
  ON defense_decisions (defense_tier, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_defense_decisions_policy
  ON defense_decisions (policy_version, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_defense_decisions_details_gin
  ON defense_decisions USING GIN (details_jsonb);

CREATE TABLE IF NOT EXISTS telemetry_features (
  id BIGSERIAL PRIMARY KEY,
  ts_ms BIGINT NOT NULL,
  session_id TEXT NOT NULL,
  trace_id TEXT,
  request_id TEXT,
  trigger TEXT,
  flow_state TEXT,
  feature_schema_version TEXT NOT NULL DEFAULT 'v1',
  total_dist DOUBLE PRECISION,
  linear_dist DOUBLE PRECISION,
  linearity_ratio DOUBLE PRECISION,
  avg_velocity DOUBLE PRECISION,
  tremor_std_dev DOUBLE PRECISION,
  dwell_time DOUBLE PRECISION,
  features_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_telemetry_features_ts
  ON telemetry_features (ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_features_session
  ON telemetry_features (session_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_features_trigger
  ON telemetry_features (trigger, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_features_jsonb_gin
  ON telemetry_features USING GIN (features_jsonb);

CREATE TABLE IF NOT EXISTS vqa_events (
  id BIGSERIAL PRIMARY KEY,
  ts_ms BIGINT NOT NULL,
  session_id TEXT NOT NULL,
  trace_id TEXT,
  request_id TEXT,
  challenge_id TEXT,
  challenge_level TEXT,
  inserted_at_stage TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  solve_latency_ms INTEGER,
  outcome TEXT NOT NULL,
  details_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_vqa_events_ts
  ON vqa_events (ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_vqa_events_session
  ON vqa_events (session_id);
CREATE INDEX IF NOT EXISTS idx_vqa_events_stage
  ON vqa_events (inserted_at_stage, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_vqa_events_jsonb_gin
  ON vqa_events USING GIN (details_jsonb);
