-- stg_footfall: daily entry/exit taps per station.
-- TravelDate arrives as a number like 20240101, so convert it to a real date.

CREATE OR REPLACE VIEW stg_footfall AS
SELECT
    CAST(strptime(CAST(TravelDate AS VARCHAR), '%Y%m%d') AS DATE) AS travel_date,
    trim(DayOfWeek)                                          AS day_of_week,
    trim(Station)                                            AS station,
    CAST(EntryTapCount AS BIGINT)                            AS entry_taps,
    CAST(ExitTapCount  AS BIGINT)                            AS exit_taps,
    CAST(EntryTapCount AS BIGINT) + CAST(ExitTapCount AS BIGINT) AS total_taps
FROM raw_footfall
WHERE TravelDate IS NOT NULL
  AND Station IS NOT NULL;
