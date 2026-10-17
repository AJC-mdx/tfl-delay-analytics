-- stg_tfl_status: one clean row per line per snapshot, mock and live data
-- combined into the same shape.
--
-- Rules:
--   * All times are UTC. observed_at_london is added for rush-hour analysis
--     (London switches between GMT and BST, so local time != UTC in summer).
--   * Mock data has no severity code, so we look it up from the description.
--   * "None" / empty reasons become NULL.
--   * If a line has several statuses at the same moment (e.g. Part Closure
--     AND Minor Delays), keep only the worst one (lowest priority_rank).
--   * "Service Closed" (the Tube shutting overnight) is category
--     'service_closed' with is_disruption = false, so it is NEVER counted
--     as a delay.

CREATE OR REPLACE VIEW stg_tfl_status AS

WITH mock AS (
    SELECT
        'mock'                                              AS data_source,
        CAST(time AS TIMESTAMP)                             AS observed_at_utc,
        -- "Waterloo & City" -> "waterloo-city", to match TfL's live IDs
        lower(replace(replace(trim(line), ' & ', '-'), ' ', '-')) AS line_id,
        sev.status_severity,
        trim(status)                                        AS status_description,
        NULLIF(NULLIF(trim(reason), ''), 'None')            AS reason
    FROM raw_tfl_mock
    LEFT JOIN ref_status_severity AS sev
        ON sev.status_description = trim(raw_tfl_mock.status)
),

live AS (
    SELECT
        'live'                                              AS data_source,
        -- convert from "timestamp with time zone" to a plain UTC timestamp
        CAST(collected_at_utc AT TIME ZONE 'UTC' AS TIMESTAMP) AS observed_at_utc,
        trim(line_id)                                       AS line_id,
        CAST(status_severity AS INTEGER)                    AS status_severity,
        trim(status_description)                            AS status_description,
        NULLIF(trim(CAST(reason AS VARCHAR)), '')           AS reason
    FROM raw_tfl_live
),

combined AS (
    SELECT * FROM mock
    UNION ALL
    SELECT * FROM live
)

SELECT
    c.data_source,
    c.observed_at_utc,
    date_trunc('hour', c.observed_at_utc)                   AS hour_utc,
    CAST((c.observed_at_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/London' AS TIMESTAMP)
                                                            AS observed_at_london,
    c.line_id,
    l.line_name,
    c.status_severity,
    c.status_description,
    sev.status_category,
    sev.is_disruption,
    sev.priority_rank,                                      -- 1 = worst
    c.reason
FROM combined AS c
LEFT JOIN ref_status_severity AS sev USING (status_severity)
LEFT JOIN ref_tube_lines      AS l   USING (line_id)
-- Keep the single worst status per line per snapshot
QUALIFY row_number() OVER (
    PARTITION BY c.data_source, c.line_id, c.observed_at_utc
    ORDER BY sev.priority_rank, c.status_severity
) = 1;
