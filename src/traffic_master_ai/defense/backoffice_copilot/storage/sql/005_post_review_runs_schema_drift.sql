-- Migration: post_review_runs schema drift fix (idempotent)
--
-- Problem:
--   Environments where post_review_runs was created before candidate_count,
--   suspicious_count, and summary_text_json were added to the schema will fail
--   with "column does not exist" when save_bundle() tries to INSERT these columns.
--   CREATE TABLE IF NOT EXISTS is a no-op on existing tables, so the original
--   migration file cannot add new columns retroactively.
--
-- Fix:
--   ALTER TABLE ADD COLUMN IF NOT EXISTS is idempotent and safe to re-run.
--   After adding columns as nullable, existing NULL rows are backfilled with
--   safe defaults, then NOT NULL is enforced.
--   CHECK constraints are added only when absent (DO block guard).
--
-- Safe to run on:
--   - Fresh environments: ADD COLUMN IF NOT EXISTS is a no-op (columns already present)
--   - Broken environments: adds the missing columns and enforces constraints

-- Step 1: Add missing columns as nullable (no-op if already present)
ALTER TABLE post_review_runs
    ADD COLUMN IF NOT EXISTS candidate_count INTEGER,
    ADD COLUMN IF NOT EXISTS suspicious_count INTEGER,
    ADD COLUMN IF NOT EXISTS summary_text_json JSONB;

-- Step 2: Backfill NULL rows with safe defaults
--   (only affects rows that pre-date the schema addition; fresh installs have no rows here)
UPDATE post_review_runs
    SET candidate_count = 0
    WHERE candidate_count IS NULL;

UPDATE post_review_runs
    SET suspicious_count = 0
    WHERE suspicious_count IS NULL;

UPDATE post_review_runs
    SET summary_text_json = '["[migrated]", "[migrated]", "[migrated]"]'::jsonb
    WHERE summary_text_json IS NULL;

-- Step 3: Enforce NOT NULL (idempotent: PostgreSQL ignores if constraint already set)
ALTER TABLE post_review_runs
    ALTER COLUMN candidate_count SET NOT NULL,
    ALTER COLUMN suspicious_count SET NOT NULL,
    ALTER COLUMN summary_text_json SET NOT NULL;

-- Step 4: Add CHECK constraints if not already present
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'post_review_runs_counts_check'
          AND conrelid = 'post_review_runs'::regclass
    ) THEN
        ALTER TABLE post_review_runs
            ADD CONSTRAINT post_review_runs_counts_check
            CHECK (candidate_count >= suspicious_count);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'post_review_runs_summary_text_json_check'
          AND conrelid = 'post_review_runs'::regclass
    ) THEN
        ALTER TABLE post_review_runs
            ADD CONSTRAINT post_review_runs_summary_text_json_check
            CHECK (
                jsonb_typeof(summary_text_json) = 'array'
                AND jsonb_array_length(summary_text_json) = 3
            );
    END IF;
END $$;
