-- Engine: ClickHouse
-- Canonical source: specs/40-db-build-agent-pack/05-defense-audit-events-minimum-ddl.md
-- Note: raw fact ingest now lands in ClickHouse via etl_worker.py; rollup/candidate read models are defined separately in 004_clickhouse_read_models.sql.

CREATE TABLE IF NOT EXISTS defense_audit_events (
    ts_ms UInt64,
    session_id String,
    event_type String,
    trace_id Nullable(String),
    challenge_id Nullable(String),
    flow_state Nullable(String),
    risk_tier Nullable(String),
    action Nullable(String),
    reason_code Nullable(String),
    policy_version Nullable(String),
    raw_payload_json String
)
ENGINE = MergeTree
PARTITION BY toDate(fromUnixTimestamp64Milli(ts_ms))
ORDER BY (session_id, ts_ms, event_type);
