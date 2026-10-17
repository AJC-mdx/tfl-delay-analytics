-- dim_line: one row per Tube line, with its official colour for charts.

CREATE OR REPLACE VIEW dim_line AS
SELECT
    line_id,
    line_name,
    line_colour
FROM ref_tube_lines;
