-- Verification queries for log -> DB ingestion integrity

-- 1) total ingested rows by day
SELECT to_timestamp(ts_ms / 1000)::date AS d, count(*) AS n
FROM defense_decisions
GROUP BY 1
ORDER BY 1 DESC;

-- 2) missing trace/request keys
SELECT count(*) AS missing_trace_or_request
FROM defense_decisions
WHERE trace_id IS NULL OR request_id IS NULL;

-- 3) tier distribution
SELECT defense_tier, count(*) AS n
FROM defense_decisions
GROUP BY defense_tier
ORDER BY defense_tier;

-- 4) policy version distribution
SELECT policy_version, count(*) AS n
FROM defense_decisions
GROUP BY policy_version
ORDER BY n DESC;

-- 5) telemetry joinability sanity check
SELECT d.session_id, count(*) AS decision_rows, count(t.id) AS telemetry_rows
FROM defense_decisions d
LEFT JOIN telemetry_features t
  ON t.session_id = d.session_id
  AND abs(t.ts_ms - d.ts_ms) <= 5000
GROUP BY d.session_id
ORDER BY decision_rows DESC
LIMIT 50;

-- 6) VQA outcome summary
SELECT challenge_level, outcome, count(*) AS n
FROM vqa_events
GROUP BY challenge_level, outcome
ORDER BY challenge_level, outcome;

