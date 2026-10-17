-- stg_weather: hourly London weather with clear names and units.
-- Open-Meteo returns times in UTC by default and wind speed in km/h.
-- IMPORTANT: precipitation at hour_utc = 10:00 is the rain that fell
-- between 09:00 and 10:00 (the hour BEFORE the timestamp). Temperature and
-- wind are readings taken at that moment.

CREATE OR REPLACE VIEW stg_weather AS
SELECT DISTINCT
    CAST(time AS TIMESTAMP)                                 AS hour_utc,
    CAST((CAST(time AS TIMESTAMP) AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/London' AS TIMESTAMP)
                                                            AS hour_london,
    CAST(temp_c   AS DOUBLE)                                AS temperature_c,
    -- rainfall can't be negative; treat anything below 0 as bad data
    CASE WHEN rain_mm >= 0 THEN CAST(rain_mm AS DOUBLE) END AS precipitation_mm,
    CASE WHEN wind_kph >= 0 THEN CAST(wind_kph AS DOUBLE) END AS wind_speed_kmh,
    weather_source                                          -- 'archive' or 'forecast'
FROM raw_weather
WHERE time IS NOT NULL;
