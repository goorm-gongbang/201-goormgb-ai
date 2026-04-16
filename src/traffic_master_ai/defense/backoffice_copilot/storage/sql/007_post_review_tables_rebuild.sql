-- Migration 007: post_review_runs + post_review_session_results final schema rebuild
--
-- Purpose:
--   The 302 bootstrap repo historically created post_review_runs and
--   post_review_session_results with a design that diverged from the AI code's
--   actual save_bundle() contract:
--
--     Old bootstrap schema (WRONG):
--       post_review_runs(
--           id BIGSERIAL PRIMARY KEY,   -- surrogate key; code uses match_id
--           match_id TEXT NOT NULL,     -- was not PK → ON CONFLICT (match_id) fails
--           window_start_ms, window_end_ms, status, created_at, completed_at
--           -- missing: candidate_count, suspicious_count, summary_text_json, updated_at
--       )
--       post_review_session_results(
--           id BIGSERIAL PRIMARY KEY,
--           post_review_run_id BIGINT NOT NULL REFERENCES post_review_runs(id),
--           session_id TEXT NOT NULL,
--           match_id TEXT NULL,
--           final_label TEXT NOT NULL,  -- NOT review_result
--           decision_summary_json JSONB NOT NULL,
--           evidence_json JSONB NOT NULL,
--           created_at TIMESTAMPTZ NOT NULL
--           -- missing: review_result, evidence_summary, session_analysis_json,
--           --          backend_delivery_status, updated_at
--       )
--
--   The drift patches 005 and 006 attempted to add missing columns via
--   ADD COLUMN IF NOT EXISTS, but they could not fix the structural problems:
--     - BIGSERIAL surrogate PK vs TEXT natural PK
--     - Missing review_result column (only final_label existed)
--     - FK constraint tying session_results to runs by surrogate id
--     - ON CONFLICT targets that match the code contract did not exist
--
-- Strategy:
--   This migration detects old schema by checking for the `id bigint` column
--   on post_review_runs. If found, it drops both tables (CASCADE removes the FK)
--   and recreates them with the final schema.
--
--   For environments already on the correct schema (created by the updated
--   bootstrap or by prior migration 001), the detection check returns false and
--   CREATE TABLE IF NOT EXISTS is a no-op.
--
-- Safety:
--   - Data confirmed at 0 rows in staging; no row-count guard is needed.
--   - Idempotent: detection check + CREATE IF NOT EXISTS make this safe to re-run.
--   - DDL permissions: assumes ai_defense owns both tables (owner/CREATE granted
--     by infra; no workaround logic required here).
--
-- Replaces: 005_post_review_runs_schema_drift.sql
--           006_post_review_session_results_schema_drift.sql
-- (those files are now obsolete and removed from the migration list)

DO $$
BEGIN
    -- Detect old schema: post_review_runs.id column of type bigint indicates
    -- the BIGSERIAL surrogate-key design from the old bootstrap.
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name   = 'post_review_runs'
          AND column_name  = 'id'
          AND data_type    = 'bigint'
    ) THEN
        -- Safety check: avoid data loss if the table is not empty
        IF EXISTS (SELECT 1 FROM post_review_runs LIMIT 1) THEN
            RAISE EXCEPTION 'post_review_tables_rebuild: old schema detected but data exists. Aborting to prevent data loss.';
        END IF;
        RAISE NOTICE 'post_review_tables_rebuild: old schema detected (id BIGSERIAL PK). Dropping and recreating.';
        -- Drop session_results first to remove the FK dependency
        DROP TABLE IF EXISTS post_review_session_results CASCADE;
        DROP TABLE IF EXISTS post_review_runs CASCADE;
        RAISE NOTICE 'post_review_tables_rebuild: old tables dropped.';
    ELSE
        RAISE NOTICE 'post_review_tables_rebuild: correct schema already in place. CREATE IF NOT EXISTS will be no-op.';
    END IF;
END $$;

-- Create with final schema (no-op if already present from bootstrap or migration 001)
CREATE TABLE IF NOT EXISTS post_review_runs (
    match_id TEXT PRIMARY KEY,
    window_start_ms BIGINT NOT NULL,
    window_end_ms BIGINT NOT NULL,
    candidate_count INTEGER NOT NULL,
    suspicious_count INTEGER NOT NULL,
    summary_text_json JSONB NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT post_review_runs_status_check
        CHECK (status IN ('SUCCESS', 'PARTIAL_SUCCESS', 'FAILED')),
    CONSTRAINT post_review_runs_counts_check
        CHECK (candidate_count >= suspicious_count),
    CONSTRAINT post_review_runs_summary_text_json_check
        CHECK (
            jsonb_typeof(summary_text_json) = 'array'
            AND jsonb_array_length(summary_text_json) = 3
        )
);

CREATE TABLE IF NOT EXISTS post_review_session_results (
    match_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    review_result TEXT NOT NULL,
    evidence_summary TEXT NOT NULL,
    session_analysis_json JSONB NOT NULL,
    backend_delivery_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (match_id, session_id),
    CONSTRAINT post_review_session_results_review_result_check
        CHECK (review_result IN ('NORMAL', 'SUSPICIOUS')),
    CONSTRAINT post_review_session_results_backend_delivery_status_check
        CHECK (backend_delivery_status IN ('PENDING', 'SENT', 'FAILED')),
    CONSTRAINT post_review_session_results_session_analysis_json_check
        CHECK (jsonb_typeof(session_analysis_json) = 'object')
);

-- Indexes (no-op if already present)
CREATE INDEX IF NOT EXISTS idx_post_review_runs_window
    ON post_review_runs(window_start_ms, window_end_ms);

CREATE INDEX IF NOT EXISTS idx_post_review_session_results_session_id
    ON post_review_session_results(session_id);
