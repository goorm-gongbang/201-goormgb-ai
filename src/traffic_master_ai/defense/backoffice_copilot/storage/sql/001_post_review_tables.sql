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
