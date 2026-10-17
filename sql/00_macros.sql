-- Reusable SQL functions (DuckDB macros), defined once and used by the
-- views below, so the weather bands are the same everywhere.

-- Rain bands (mm of rain in an hour or period)
CREATE OR REPLACE MACRO rain_band_order(mm) AS
    CASE WHEN mm IS NULL THEN NULL
         WHEN mm = 0     THEN 1
         WHEN mm <= 0.5  THEN 2
         WHEN mm <= 2    THEN 3
         ELSE                 4 END;

CREATE OR REPLACE MACRO rain_band(mm) AS
    CASE rain_band_order(mm)
         WHEN 1 THEN 'Dry (0 mm)'
         WHEN 2 THEN 'Light (0-0.5 mm)'
         WHEN 3 THEN 'Moderate (0.5-2 mm)'
         WHEN 4 THEN 'Heavy (2+ mm)' END;

-- Wind bands (km/h)
CREATE OR REPLACE MACRO wind_band_order(kmh) AS
    CASE WHEN kmh IS NULL THEN NULL
         WHEN kmh < 15   THEN 1
         WHEN kmh < 25   THEN 2
         WHEN kmh < 40   THEN 3
         ELSE                 4 END;

CREATE OR REPLACE MACRO wind_band(kmh) AS
    CASE wind_band_order(kmh)
         WHEN 1 THEN 'Calm (<15 km/h)'
         WHEN 2 THEN 'Breezy (15-25 km/h)'
         WHEN 3 THEN 'Windy (25-40 km/h)'
         WHEN 4 THEN 'Very windy (40+ km/h)' END;

-- Rush hour = TfL weekday peaks, by London clock hour:
-- AM 07:00-09:59, PM 16:00-18:59
CREATE OR REPLACE MACRO time_band(hour_of_day) AS
    CASE WHEN hour_of_day BETWEEN 7 AND 9   THEN 'AM peak'
         WHEN hour_of_day BETWEEN 16 AND 18 THEN 'PM peak'
         WHEN hour_of_day BETWEEN 10 AND 15 THEN 'Daytime off-peak'
         WHEN hour_of_day BETWEEN 19 AND 23 THEN 'Evening'
         ELSE                                    'Night / early morning' END;
