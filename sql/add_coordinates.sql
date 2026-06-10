-- Add latitude and longitude columns for geographical dimension tables
-- We use NUMERIC(10, 8) for latitude: Up to 2 digits before decimal (since max is 90) + 8 digits after decimal = 10 digits total
-- We use NUMERIC(11, 8) for longitude: Up to 3 digits before decimal (since max is 180) + 8 digits after decimal = 11 digits total

ALTER TABLE dim_provinces
ADD COLUMN IF NOT EXISTS latitude NUMERIC(10, 8),
ADD COLUMN IF NOT EXISTS longitude NUMERIC(11, 8);

ALTER TABLE dim_regencies
ADD COLUMN IF NOT EXISTS latitude NUMERIC(10, 8),
ADD COLUMN IF NOT EXISTS longitude NUMERIC(11, 8);
