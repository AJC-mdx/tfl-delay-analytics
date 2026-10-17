-- fct_delay_episodes: one row per delay "episode" - an unbroken run of
-- disrupted snapshots on one line - with its start, end and duration.
--
-- This is a classic "gaps and islands" problem, solved with window functions:
--   1. LAG/LEAD look at the previous/next snapshot for the same line.
--   2. Mark where a new episode starts (status flips, or there's a gap in data).
--   3. A running SUM of those markers gives every row an episode number.
--   4. GROUP BY episode number to get start, end and duration.
--
-- Rules (from Phase 2.2):
--   * A delay = is_disruption. "Service Closed" is not a disruption, so a delay
--     that runs into the overnight closure ends there.
--   * Gaps in the data (laptop off) are NOT filled. If the next snapshot is
--     further away than max_gap_minutes, we stop the episode at the last time
--     we saw it and mark the end as unconfirmed.
--   * Mock and live data are kept apart (PARTITION BY data_source).
--
-- Accuracy: the real start/end happen somewhere between two snapshots, so
-- durations are accurate to the snapshot interval (15 min live, 1 hour mock).

CREATE OR REPLACE VIEW fct_delay_episodes AS

WITH settings AS (
    -- Largest normal gap between snapshots, per source.
    -- Live is collected every 15 min, mock is hourly.
    SELECT 'live' AS data_source, INTERVAL 30 MINUTE AS max_gap
    UNION ALL
    SELECT 'mock', INTERVAL 90 MINUTE
),

-- Step 1: look at the previous and next snapshot for the same line
with_neighbours AS (
    SELECT
        s.*,
        st.max_gap,
        LAG(s.is_disruption)    OVER w AS prev_is_disruption,
        LAG(s.observed_at_utc)  OVER w AS prev_observed_at_utc,
        LEAD(s.observed_at_utc) OVER w AS next_observed_at_utc
    FROM stg_tfl_status AS s
    JOIN settings AS st USING (data_source)
    WINDOW w AS (PARTITION BY s.data_source, s.line_id ORDER BY s.observed_at_utc)
),

-- Step 2: flag the first row of every new run
flagged AS (
    SELECT
        *,
        CASE
            WHEN prev_is_disruption IS NULL                         THEN 1  -- first snapshot for this line
            WHEN is_disruption <> prev_is_disruption                THEN 1  -- status flipped
            WHEN observed_at_utc - prev_observed_at_utc > max_gap   THEN 1  -- gap in the data
            ELSE 0
        END AS is_new_run
    FROM with_neighbours
),

-- Step 3: running total of the flags = a run number for every row
numbered AS (
    SELECT
        *,
        SUM(is_new_run) OVER (
            PARTITION BY data_source, line_id
            ORDER BY observed_at_utc
            ROWS UNBOUNDED PRECEDING
        ) AS run_id
    FROM flagged
),

-- Step 4: collapse each disrupted run into one row
episodes AS (
    SELECT
        data_source,
        line_id,
        any_value(line_name)                                AS line_name,
        run_id,
        MIN(observed_at_utc)                                AS delay_start_utc,
        MAX(observed_at_utc)                                AS last_seen_disrupted_utc,
        -- the snapshot straight after the last disrupted one = recovery seen
        -- (times only go up, so the latest "next" belongs to the last row)
        MAX(next_observed_at_utc)                           AS next_snapshot_utc,
        -- no next snapshot at all = the delay is still going at the end of the data
        bool_or(next_observed_at_utc IS NULL)               AS is_ongoing,
        any_value(max_gap)                                  AS max_gap,
        COUNT(*)                                            AS snapshot_count,
        -- worst status during the episode (rank 1 = worst, from ref_status_severity)
        arg_min(status_description, priority_rank)          AS worst_status,
        arg_min(status_category,    priority_rank)          AS worst_category,
        -- first reason TfL gave
        arg_min(reason, observed_at_utc)                    AS first_reason
    FROM numbered
    WHERE is_disruption
    GROUP BY data_source, line_id, run_id
),

-- Step 5: decide the end time
ended AS (
    SELECT
        *,
        -- TRUE = we actually saw the line recover. FALSE = still ongoing or
        -- a data gap, so the real duration is at least what we report.
        NOT is_ongoing AND next_snapshot_utc - last_seen_disrupted_utc <= max_gap
                                                            AS end_confirmed
    FROM episodes
)

SELECT
    data_source,
    line_id,
    line_name,
    row_number() OVER (PARTITION BY data_source ORDER BY delay_start_utc, line_id) AS episode_id,
    delay_start_utc,
    CAST((delay_start_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/London' AS TIMESTAMP)
                                                            AS delay_start_london,
    -- for Power BI: joins to dim_date / dim_hour
    CAST(CAST((delay_start_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/London' AS TIMESTAMP) AS DATE)
                                                            AS start_date_london,
    hour(CAST((delay_start_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/London' AS TIMESTAMP))
                                                            AS start_hour_of_day,
    -- end = when we saw recovery; otherwise the last time we saw the delay
    CASE WHEN end_confirmed THEN next_snapshot_utc ELSE last_seen_disrupted_utc END
                                                            AS delay_end_utc,
    date_diff('minute', delay_start_utc,
        CASE WHEN end_confirmed THEN next_snapshot_utc ELSE last_seen_disrupted_utc END)
                                                            AS duration_minutes,
    end_confirmed,
    is_ongoing,
    snapshot_count,
    worst_status,
    worst_category,
    first_reason
FROM ended;
