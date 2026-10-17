-- fct_line_hour: one row per line per hour that we have snapshots for, with
-- what happened on the line and the weather around it. This is the table for
-- the weather analysis (2.4), the Power BI heatmap (3.4) and the ML model (4.x).
--
-- Rules:
--   * Hours with no snapshots (laptop off) get no row - gaps are not filled.
--   * is_running = FALSE when the line was "Service Closed" for the whole hour.
--     Closed hours can't have delays, so leave them out of delay rates.
--   * Weather timing (Open-Meteo rain at 10:00 = rain from 09:00 to 10:00).
--     For the line-hour starting 09:00:
--       rain_this_hour_mm  = 09:00-10:00 (same time as the delays)
--       rain_prev_hour_mm  = 08:00-09:00 (already known at 09:00)
--       rain_last_3h_mm    = 06:00-09:00 (already known at 09:00)
--       wind / temperature = readings at 09:00
--     Only the "prev" / "last 3h" columns are known in advance, so only
--     those can be used to PREDICT delays in Phase 4.

CREATE OR REPLACE VIEW fct_line_hour AS

WITH weather AS (
    SELECT
        hour_utc,
        temperature_c,
        wind_speed_kmh,
        precipitation_mm,
        -- rain over the 3 hours ending at hour_utc. RANGE (not ROWS) so a
        -- missing hour isn't silently replaced by an older one
        SUM(precipitation_mm) OVER (
            ORDER BY hour_utc
            RANGE BETWEEN INTERVAL 2 HOUR PRECEDING AND CURRENT ROW
        ) AS precipitation_3h_mm
    FROM stg_weather
),

line_hours AS (
    SELECT
        data_source,
        line_id,
        any_value(line_name)                                AS line_name,
        hour_utc,
        COUNT(*)                                            AS snapshot_count,
        COUNT(*) FILTER (WHERE status_category <> 'service_closed') AS running_snapshot_count,
        COUNT(*) FILTER (WHERE is_disruption)               AS disrupted_snapshot_count
    FROM stg_tfl_status
    GROUP BY data_source, line_id, hour_utc
),

delay_starts AS (
    SELECT
        data_source,
        line_id,
        date_trunc('hour', delay_start_utc)                 AS hour_utc,
        COUNT(*)                                            AS delays_started
    FROM fct_delay_episodes
    GROUP BY ALL
)

SELECT
    lh.data_source,
    lh.line_id,
    lh.line_name,
    lh.hour_utc,
    CAST((lh.hour_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/London' AS TIMESTAMP)
                                                            AS hour_london,
    lh.snapshot_count,
    lh.running_snapshot_count > 0                           AS is_running,
    lh.disrupted_snapshot_count > 0                         AS any_disruption,
    -- share of the hour the line was disrupted (while running)
    lh.disrupted_snapshot_count / NULLIF(lh.running_snapshot_count, 0)
                                                            AS disrupted_share,
    COALESCE(ds.delays_started, 0)                          AS delays_started,
    COALESCE(ds.delays_started, 0) > 0                      AS new_delay_started,
    w_end.precipitation_mm                                  AS rain_this_hour_mm,
    w_start.precipitation_mm                                AS rain_prev_hour_mm,
    w_start.precipitation_3h_mm                             AS rain_last_3h_mm,
    w_start.wind_speed_kmh,
    w_start.temperature_c,
    -- For Power BI: London date/hour (joins to dim_date / dim_hour) and bands.
    -- Bands use rain in the PREVIOUS hour, which is known in advance.
    CAST(hour_london AS DATE)                               AS date_london,
    hour(hour_london)                                       AS hour_of_day,
    dayofweek(hour_london) IN (0, 6)                        AS is_weekend,
    -- rush hour = weekday peak hours, not on bank holidays
    dayofweek(hour_london) NOT IN (0, 6)
        AND CAST(hour_london AS DATE) NOT IN (SELECT date FROM ref_bank_holidays)
        AND time_band(hour(hour_london)) IN ('AM peak', 'PM peak') AS is_rush_hour,
    rain_band(w_start.precipitation_mm)                     AS rain_band,
    rain_band_order(w_start.precipitation_mm)               AS rain_band_order,
    rain_band(w_start.precipitation_mm) <> 'Dry (0 mm)'     AS is_wet,
    wind_band(w_start.wind_speed_kmh)                       AS wind_band,
    wind_band_order(w_start.wind_speed_kmh)                 AS wind_band_order
FROM line_hours AS lh
LEFT JOIN delay_starts AS ds
    USING (data_source, line_id, hour_utc)
-- weather row at the START of the hour: rain that fell in the hour before
LEFT JOIN weather AS w_start
    ON w_start.hour_utc = lh.hour_utc
-- weather row at the END of the hour: rain that fell during this hour
LEFT JOIN weather AS w_end
    ON w_end.hour_utc = lh.hour_utc + INTERVAL 1 HOUR;
