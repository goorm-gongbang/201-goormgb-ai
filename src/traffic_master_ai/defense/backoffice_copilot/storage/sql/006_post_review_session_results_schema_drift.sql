-- Migration: post_review_session_results schema drift fix (idempotent)
--
-- Problem:
--   Environments where post_review_session_results was created before
--   evidence_summary, session_analysis_json, and backend_delivery_status
--   were added to the schema will fail with "column does not exist" when
--   save_bundle() tries to INSERT these columns.
--   CREATE TABLE IF NOT EXISTS is a no-op on existing tables, so the original
--   migration file cannot add new columns retroactively.
--
-- Fix:
--   ALTER TABLE ADD COLUMN IF NOT EXISTS is idempotent and safe to re-run.
--   After adding columns as nullable, existing NULL rows are backfilled with
--   safe defaults in a single COALESCE pass, then NOT NULL is enforced.
--   CHECK constraints are added only when absent (DO block guard).
--
-- Safe to run on:
--   - Fresh environments: ADD COLUMN IF NOT EXISTS is a no-op (columns already present)
--   - Broken environments: adds the missing columns and enforces constraints

-- Step 1: Add missing columns as nullable (no-op if already present)
ALTER TABLE post_review_session_results
    ADD COLUMN IF NOT EXISTS evidence_summary TEXT,
    ADD COLUMN IF NOT EXISTS session_analysis_json JSONB,
    ADD COLUMN IF NOT EXISTS backend_delivery_status TEXT;

-- Step 2: Backfill all NULL columns in a single pass
--   (avoids sequential full-table scans and minimises lock duration)
--   Only affects rows that pre-date the schema addition; fresh installs have no rows here.
UPDATE post_review_session_results
    SET
        evidence_summary        = COALESCE(evidence_summary,        '[migrated]'),
        session_analysis_json   = COALESCE(session_analysis_json,   '{"session_id": "[migrated]", "latest_flow_state": "UNKNOWN", "latest_action": "UNKNOWN", "latest_tier": "UNKNOWN", "terminal_outcome": "UNKNOWN", "seen_t1": false, "seen_t2": false, "vqa_fail_count": 0, "throttle_event_count": 0, "suspicious_signals": [], "timeline_summary": [], "needs_raw_fallback": false}'::jsonb),
        backend_delivery_status = COALESCE(backend_delivery_status, 'PENDING')
    WHERE
        evidence_summary IS NULL
        OR session_analysis_json IS NULL
        OR backend_delivery_status IS NULL;

-- Step 3: Enforce NOT NULL (idempotent: PostgreSQL ignores if constraint already set)
ALTER TABLE post_review_session_results
    ALTER COLUMN evidence_summary SET NOT NULL,
    ALTER COLUMN session_analysis_json SET NOT NULL,
    ALTER COLUMN backend_delivery_status SET NOT NULL;

-- Step 4: Add CHECK constraints if not already present
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'post_review_session_results_review_result_check'
          AND conrelid = 'post_review_session_results'::regclass
    ) THEN
        ALTER TABLE post_review_session_results
            ADD CONSTRAINT post_review_session_results_review_result_check
            CHECK (review_result IN ('NORMAL', 'SUSPICIOUS'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'post_review_session_results_backend_delivery_status_check'
          AND conrelid = 'post_review_session_results'::regclass
    ) THEN
        ALTER TABLE post_review_session_results
            ADD CONSTRAINT post_review_session_results_backend_delivery_status_check
            CHECK (backend_delivery_status IN ('PENDING', 'SENT', 'FAILED'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'post_review_session_results_session_analysis_json_check'
          AND conrelid = 'post_review_session_results'::regclass
    ) THEN
        ALTER TABLE post_review_session_results
            ADD CONSTRAINT post_review_session_results_session_analysis_json_check
            CHECK (jsonb_typeof(session_analysis_json) = 'object');
    END IF;
END $$;
