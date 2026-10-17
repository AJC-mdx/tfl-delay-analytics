-- rpt_weather_impact: how much more likely are delays in bad weather?
--
-- For each weather measure, line-hours are grouped into bands (Dry / Light /
-- Moderate / Heavy rain, Calm ... Very windy). For each band:
--   line_hours           how much data the band is based on (small = unreliable)
--   delay_start_rate     new delays per 100 line-hours  (main measure)
--   disrupted_hour_rate  % of line-hours with any disruption
--   relative_risk        delay_start_rate / the calmest band's rate
--                        e.g. 2.0 = delays start twice as often as when dry
--
-- Only hours when the line was running are included (overnight closures out).
-- Mock and live results are kept separate (data_source).
-- NOTE: the mock data was generated with a built-in rule (rain > 0.5 mm in the
-- previous hour or wind > 25 km/h triples the delay chance). Mock results only
-- show that this query can find that pattern - they are not a real finding.

CREATE OR REPLACE VIEW rpt_weather_impact AS

WITH running AS (
    SELECT * FROM fct_line_hour WHERE is_running
),

-- One row per line-hour per weather measure, with its band
banded AS (
    SELECT data_source, 'Rain during the hour' AS weather_measure, rain_this_hour_mm AS value,
           new_delay_started, any_disruption, delays_started
    FROM running
    UNION ALL
    SELECT data_source, 'Rain in the previous hour', rain_prev_hour_mm,
           new_delay_started, any_disruption, delays_started
    FROM running
    UNION ALL
    SELECT data_source, 'Rain in the previous 3 hours', rain_last_3h_mm,
           new_delay_started, any_disruption, delays_started
    FROM running
    UNION ALL
    SELECT data_source, 'Wind speed', wind_speed_kmh,
           new_delay_started, any_disruption, delays_started
    FROM running
),

-- Bands come from the macros in 00_macros.sql
with_band AS (
    SELECT
        *,
        CASE WHEN weather_measure = 'Wind speed' THEN wind_band_order(value)
             ELSE rain_band_order(value) END                AS band_order,
        CASE WHEN weather_measure = 'Wind speed' THEN wind_band(value)
             ELSE rain_band(value) END                      AS band
    FROM banded
    WHERE value IS NOT NULL   -- e.g. the latest hour's rain isn't known yet
),

rates AS (
    SELECT
        data_source,
        weather_measure,
        band_order,
        band,
        COUNT(*)                                            AS line_hours,
        SUM(delays_started)                                 AS delays_started,
        round(100.0 * SUM(delays_started) / COUNT(*), 2)    AS delay_start_rate,
        round(100.0 * AVG(CAST(any_disruption AS INTEGER)), 2) AS disrupted_hour_rate
    FROM with_band
    GROUP BY ALL
)

SELECT
    *,
    -- compare every band with the calmest band for the same measure
    round(delay_start_rate / NULLIF(first_value(delay_start_rate) OVER (
        PARTITION BY data_source, weather_measure ORDER BY band_order
    ), 0), 2)                                               AS relative_risk
FROM rates
ORDER BY data_source, weather_measure, band_order;
