-- Data quality checks. Each row is one check; "failures" should be 0.
-- Run automatically at the end of load_database.py.

SELECT 'tfl: duplicate line + time' AS check_name, COUNT(*) AS failures
FROM (
    SELECT data_source, line_id, observed_at_utc
    FROM stg_tfl_status
    GROUP BY ALL
    HAVING COUNT(*) > 1
)

UNION ALL
SELECT 'tfl: missing timestamp', COUNT(*)
FROM stg_tfl_status WHERE observed_at_utc IS NULL

UNION ALL
SELECT 'tfl: line not in ref_tube_lines', COUNT(*)
FROM stg_tfl_status WHERE line_name IS NULL

UNION ALL
SELECT 'tfl: severity not in ref_status_severity', COUNT(*)
FROM stg_tfl_status WHERE status_category IS NULL

UNION ALL
SELECT 'tfl: Service Closed counted as disruption', COUNT(*)
FROM stg_tfl_status WHERE status_category = 'service_closed' AND is_disruption

UNION ALL
SELECT 'delays: negative duration', COUNT(*)
FROM fct_delay_episodes WHERE duration_minutes < 0

UNION ALL
SELECT 'delays: overlapping episodes on same line', COUNT(*)
FROM (
    SELECT delay_start_utc,
           LAG(delay_end_utc) OVER (PARTITION BY data_source, line_id ORDER BY delay_start_utc) AS prev_end
    FROM fct_delay_episodes
)
WHERE delay_start_utc < prev_end

UNION ALL
SELECT 'line-hour: running hour missing weather', COUNT(*)
FROM fct_line_hour
WHERE is_running AND (rain_prev_hour_mm IS NULL OR wind_speed_kmh IS NULL)

UNION ALL
SELECT 'line-hour: delay started while line closed', COUNT(*)
FROM fct_line_hour
WHERE NOT is_running AND new_delay_started

UNION ALL
SELECT 'line-hour: delays lost when grouping by hour', ABS(
    (SELECT COUNT(*) FROM fct_delay_episodes) - (SELECT SUM(delays_started) FROM fct_line_hour))

UNION ALL
-- Power BI relationships: every fact row must find its dimension rows
SELECT 'powerbi: fact rows with no matching date/hour/line/source', COUNT(*)
FROM (
    SELECT date_london AS d, hour_of_day AS h, line_id, data_source FROM fct_line_hour
    UNION ALL
    SELECT start_date_london, start_hour_of_day, line_id, data_source FROM fct_delay_episodes
) AS f
WHERE f.d           NOT IN (SELECT date FROM dim_date)
   OR f.h           NOT IN (SELECT hour_of_day FROM dim_hour)
   OR f.line_id     NOT IN (SELECT line_id FROM dim_line)
   OR f.data_source NOT IN (SELECT data_source FROM dim_data_source)

UNION ALL
SELECT 'weather: duplicate hour', COUNT(*)
FROM (SELECT hour_utc FROM stg_weather GROUP BY 1 HAVING COUNT(*) > 1)

UNION ALL
SELECT 'weather: missing or negative values', COUNT(*)
FROM stg_weather
WHERE temperature_c IS NULL OR precipitation_mm IS NULL OR wind_speed_kmh IS NULL

UNION ALL
SELECT 'footfall: unparseable date', COUNT(*)
FROM stg_footfall WHERE travel_date IS NULL

UNION ALL
SELECT 'footfall: negative or missing taps', COUNT(*)
FROM stg_footfall
WHERE entry_taps IS NULL OR exit_taps IS NULL OR entry_taps < 0 OR exit_taps < 0

ORDER BY failures DESC, check_name;
