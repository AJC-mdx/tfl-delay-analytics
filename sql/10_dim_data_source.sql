-- dim_data_source: lets ONE Power BI slicer switch both fact tables between
-- simulated (mock) and real (live) data, so they are never mixed.

CREATE OR REPLACE VIEW dim_data_source AS
SELECT * FROM (VALUES
    ('mock', 'Simulated (mock data)', TRUE,  1),
    ('live', 'Live (real TfL data)',  FALSE, 2)
) AS t(data_source, data_source_label, is_simulated, sort_order);
