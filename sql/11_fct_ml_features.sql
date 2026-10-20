-- fct_ml_features (Phase 4.1): one row per line-hour for the delay-prediction
-- model. The question: "this line is running normally at the start of the
-- hour - will a new delay start during the hour?"
--
-- LEAKAGE RULE: every feature must be known AT THE START of the hour.
--   * Weather: rain in the previous hour / previous 3 hours, wind and
--     temperature at the start of the hour - never rain DURING the hour.
--   * History: only snapshots and hours that finished before this hour.
--
-- Population: running line-hours where the line was NOT disrupted at the
-- start of the hour. (If it's already disrupted, a new delay can't start -
-- the model would just learn that rule instead of anything useful.)

CREATE OR REPLACE VIEW fct_ml_features AS

WITH lh AS (
    SELECT * FROM fct_line_hour
),

-- Line status at the start of the hour = the last snapshot taken strictly
-- BEFORE the hour began (ASOF join finds the nearest earlier snapshot)
start_status AS (
    SELECT
        lh.data_source,
        lh.line_id,
        lh.hour_utc,
        s.observed_at_utc                                   AS start_snapshot_utc,
        s.is_disruption                                     AS disrupted_at_start
    FROM lh
    ASOF LEFT JOIN stg_tfl_status AS s
        ON  s.data_source = lh.data_source
        AND s.line_id     = lh.line_id
        AND lh.hour_utc   > s.observed_at_utc
),

-- How many lines were disrupted in each hour (network-wide stress)
network AS (
    SELECT
        data_source,
        hour_utc,
        COUNT(*) FILTER (WHERE any_disruption)              AS lines_disrupted
    FROM lh
    GROUP BY ALL
),

-- Delays on this line in the 24 hours BEFORE this hour
history AS (
    SELECT
        data_source,
        line_id,
        hour_utc,
        SUM(delays_started) OVER (
            PARTITION BY data_source, line_id
            ORDER BY hour_utc
            RANGE BETWEEN INTERVAL 24 HOUR PRECEDING AND INTERVAL 1 HOUR PRECEDING
        )                                                   AS delays_last_24h
    FROM lh
)

SELECT
    -- identifiers (not model inputs)
    lh.data_source,
    lh.line_id,
    lh.hour_utc,
    lh.hour_london,
    ss.start_snapshot_utc,

    -- target: did a new delay start during this hour?
    CAST(lh.new_delay_started AS INTEGER)                   AS target_new_delay,

    -- time features
    lh.hour_of_day,
    isodow(lh.hour_london)                                  AS day_of_week,     -- Mon = 1
    CAST(lh.is_weekend AS INTEGER)                          AS is_weekend,
    CAST(lh.date_london IN (SELECT date FROM ref_bank_holidays) AS INTEGER) AS is_bank_holiday,
    CAST(lh.is_rush_hour AS INTEGER)                        AS is_rush_hour,

    -- weather known at the start of the hour
    lh.rain_prev_hour_mm,
    lh.rain_last_3h_mm,
    lh.wind_speed_kmh,
    lh.temperature_c,

    -- recent history
    h.delays_last_24h,
    -- other lines disrupted in the previous hour (excluding this line)
    n.lines_disrupted - COALESCE(CAST(prev.any_disruption AS INTEGER), 0)
                                                            AS other_lines_disrupted_prev_hour
FROM lh
JOIN start_status AS ss
    USING (data_source, line_id, hour_utc)
LEFT JOIN history AS h
    USING (data_source, line_id, hour_utc)
LEFT JOIN network AS n
    ON  n.data_source = lh.data_source
    AND n.hour_utc    = lh.hour_utc - INTERVAL 1 HOUR
LEFT JOIN lh AS prev
    ON  prev.data_source = lh.data_source
    AND prev.line_id     = lh.line_id
    AND prev.hour_utc    = lh.hour_utc - INTERVAL 1 HOUR
WHERE lh.is_running
  -- line known to be running normally at the start of the hour...
  AND ss.disrupted_at_start = FALSE
  -- ...and that knowledge is recent (no data gap just before the hour)
  AND lh.hour_utc - ss.start_snapshot_utc <= INTERVAL 90 MINUTE;
