-- dim_date: the calendar table. One row per London date, covering every
-- date in our data (it grows automatically as the live data grows).

CREATE OR REPLACE VIEW dim_date AS

WITH bounds AS (
    SELECT MIN(date_london) AS first_date, MAX(date_london) AS last_date
    FROM fct_line_hour
),

dates AS (
    SELECT CAST(d AS DATE) AS date
    FROM bounds, generate_series(first_date, last_date, INTERVAL 1 DAY) AS t(d)
)

SELECT
    d.date,
    year(d.date)                                            AS year,
    month(d.date)                                           AS month_number,
    strftime(d.date, '%b %Y')                               AS month_label,      -- "Jan 2024"
    year(d.date) * 100 + month(d.date)                      AS month_sort,       -- sort month_label by this
    isodow(d.date)                                          AS day_of_week_number, -- Mon = 1 ... Sun = 7
    dayname(d.date)                                         AS day_of_week,
    left(dayname(d.date), 3)                                AS day_of_week_short,
    isodow(d.date) >= 6                                     AS is_weekend,
    bh.date IS NOT NULL                                     AS is_bank_holiday,
    bh.holiday_name,
    -- a normal working day: not a weekend and not a bank holiday
    isodow(d.date) < 6 AND bh.date IS NULL                  AS is_working_day
FROM dates AS d
LEFT JOIN ref_bank_holidays AS bh
    ON bh.date = d.date;
