-- dim_hour: one row per hour of the day (London clock time), 0-23.

CREATE OR REPLACE VIEW dim_hour AS
SELECT
    h                                                       AS hour_of_day,
    lpad(CAST(h AS VARCHAR), 2, '0') || ':00'               AS hour_label,  -- "07:00"
    lpad(CAST(h AS VARCHAR), 2, '0')                        AS hour_short,  -- "07", for narrow heatmap columns
    time_band(h)                                            AS time_band,   -- from 00_macros.sql
    time_band(h) IN ('AM peak', 'PM peak')                  AS is_peak_hour -- weekdays only; combine with dim_date.is_working_day
FROM range(24) AS t(h);
