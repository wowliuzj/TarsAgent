-- Metabase 追踪分析视图（PostgreSQL）
-- 用法：
--   psql "$DATABASE_URL" -f scripts/metabase_trace_views.sql

CREATE OR REPLACE VIEW vw_trace_runs_summary AS
SELECT
    r.trace_id,
    r.session_id,
    r.goal,
    r.status,
    r.started_at,
    r.completed_at,
    r.response_length,
    CASE
        WHEN r.started_at IS NOT NULL AND r.completed_at IS NOT NULL
            THEN EXTRACT(EPOCH FROM (r.completed_at - r.started_at))
        ELSE NULL
    END AS duration_seconds
FROM trace_runs r;

CREATE OR REPLACE VIEW vw_trace_event_timeline AS
SELECT
    e.trace_id,
    e.ts,
    e.node,
    e.event_type,
    e.severity,
    e.payload
FROM trace_events e;

CREATE OR REPLACE VIEW vw_trace_llm_usage AS
SELECT
    e.trace_id,
    e.ts,
    e.node,
    e.payload->>'model' AS model,
    COALESCE((e.payload->'usage'->>'prompt_tokens')::bigint, 0) AS prompt_tokens,
    COALESCE((e.payload->'usage'->>'completion_tokens')::bigint, 0) AS completion_tokens,
    COALESCE((e.payload->'usage'->>'total_tokens')::bigint, 0) AS total_tokens
FROM trace_events e
WHERE e.event_type = 'llm_call_finished';

CREATE OR REPLACE VIEW vw_trace_tool_calls AS
SELECT
    e.trace_id,
    e.ts,
    e.node,
    e.event_type,
    e.payload->>'tool_name' AS tool_name,
    COALESCE((e.payload->>'output_size')::bigint, 0) AS output_size,
    e.payload->>'result_preview' AS result_preview
FROM trace_events e
WHERE e.event_type IN ('tool_call_started', 'tool_call_finished', 'tool_call_blocked');

CREATE OR REPLACE VIEW vw_trace_hitl_decisions AS
SELECT
    e.trace_id,
    e.ts,
    e.payload->>'tool_name' AS tool_name,
    (e.payload->>'approved')::boolean AS approved,
    COALESCE((e.payload->>'confidence')::double precision, NULL) AS confidence,
    COALESCE((e.payload->>'threshold')::double precision, NULL) AS threshold,
    e.payload->>'reason' AS reason
FROM trace_events e
WHERE e.event_type = 'hitl_decision';

CREATE OR REPLACE VIEW vw_trace_auditor_verdicts AS
SELECT
    e.trace_id,
    e.ts,
    COALESCE((e.payload->>'approved')::boolean, false) AS approved,
    e.payload->>'reason' AS reason,
    e.payload->>'mode' AS mode
FROM trace_events e
WHERE e.event_type = 'auditor_verdict';

CREATE OR REPLACE VIEW vw_trace_tier_transitions AS
SELECT
    e.trace_id,
    e.ts,
    e.node,
    e.payload->>'from_tier' AS from_tier,
    e.payload->>'to_tier' AS to_tier,
    e.payload->>'trigger' AS trigger,
    e.payload->>'resolved_model' AS resolved_model
FROM trace_events e
WHERE e.event_type = 'tier_transition';
