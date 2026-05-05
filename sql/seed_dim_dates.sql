-- ===================================================================
-- seed_dim_dates.sql
-- Generates a continuous series of dates from 2020 to 2030.
-- Designed to be idempotent and run automatically on DB initialization.
-- ===================================================================

INSERT INTO dim_dates (
    date_id,
    full_date,
    year,
    quarter,
    month,
    month_name,
    day,
    day_of_week,
    day_name,
    is_weekend
)
SELECT 
    -- date_id: YYYYMMDD format
    TO_CHAR(d, 'YYYYMMDD')::INT AS date_id,
    
    -- full_date
    d::DATE AS full_date,
    
    -- year
    EXTRACT(YEAR FROM d)::INT AS year,
    
    -- quarter
    EXTRACT(QUARTER FROM d)::INT AS quarter,
    
    -- month
    EXTRACT(MONTH FROM d)::INT AS month,
    
    -- month_name (Indonesian Localization via Explicit CASE)
    CASE EXTRACT(MONTH FROM d)
        WHEN 1 THEN 'Januari'
        WHEN 2 THEN 'Februari'
        WHEN 3 THEN 'Maret'
        WHEN 4 THEN 'April'
        WHEN 5 THEN 'Mei'
        WHEN 6 THEN 'Juni'
        WHEN 7 THEN 'Juli'
        WHEN 8 THEN 'Agustus'
        WHEN 9 THEN 'September'
        WHEN 10 THEN 'Oktober'
        WHEN 11 THEN 'November'
        WHEN 12 THEN 'Desember'
    END AS month_name,
    
    -- day of the month
    EXTRACT(DAY FROM d)::INT AS day,
    
    -- day_of_week (ISO standard: 1=Monday, 7=Sunday)
    EXTRACT(ISODOW FROM d)::INT AS day_of_week,
    
    -- day_name (Indonesian Localization via Explicit CASE)
    CASE EXTRACT(ISODOW FROM d)
        WHEN 1 THEN 'Senin'
        WHEN 2 THEN 'Selasa'
        WHEN 3 THEN 'Rabu'
        WHEN 4 THEN 'Kamis'
        WHEN 5 THEN 'Jumat'
        WHEN 6 THEN 'Sabtu'
        WHEN 7 THEN 'Minggu'
    END AS day_name,
    
    -- is_weekend (True if Saturday or Sunday)
    EXTRACT(ISODOW FROM d) IN (6, 7) AS is_weekend

FROM generate_series('2020-01-01'::DATE, '2030-12-31'::DATE, '1 day'::INTERVAL) AS d

-- Idempotency: Ignore if the date already exists
ON CONFLICT (date_id) DO NOTHING;
