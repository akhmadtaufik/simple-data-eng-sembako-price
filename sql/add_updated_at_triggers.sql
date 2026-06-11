-- 1. Create the reusable trigger function
-- This function will be executed on every UPDATE.
-- It simply updates the `updated_at` column to the current timestamp.
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. Add 'updated_at' columns to all tables (Idempotent)
ALTER TABLE dim_dates ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE dim_provinces ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE dim_regencies ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE dim_market_types ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE dim_markets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE dim_commodity_groups ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE dim_commodities ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE fact_daily_prices ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 3. Apply triggers to all tables
-- We first drop the trigger if it exists to make the script idempotent, then create it.

DROP TRIGGER IF EXISTS update_dim_dates_modtime ON dim_dates;
CREATE TRIGGER update_dim_dates_modtime
BEFORE UPDATE ON dim_dates
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

DROP TRIGGER IF EXISTS update_dim_provinces_modtime ON dim_provinces;
CREATE TRIGGER update_dim_provinces_modtime
BEFORE UPDATE ON dim_provinces
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

DROP TRIGGER IF EXISTS update_dim_regencies_modtime ON dim_regencies;
CREATE TRIGGER update_dim_regencies_modtime
BEFORE UPDATE ON dim_regencies
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

DROP TRIGGER IF EXISTS update_dim_market_types_modtime ON dim_market_types;
CREATE TRIGGER update_dim_market_types_modtime
BEFORE UPDATE ON dim_market_types
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

DROP TRIGGER IF EXISTS update_dim_markets_modtime ON dim_markets;
CREATE TRIGGER update_dim_markets_modtime
BEFORE UPDATE ON dim_markets
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

DROP TRIGGER IF EXISTS update_dim_commodity_groups_modtime ON dim_commodity_groups;
CREATE TRIGGER update_dim_commodity_groups_modtime
BEFORE UPDATE ON dim_commodity_groups
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

DROP TRIGGER IF EXISTS update_dim_commodities_modtime ON dim_commodities;
CREATE TRIGGER update_dim_commodities_modtime
BEFORE UPDATE ON dim_commodities
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

DROP TRIGGER IF EXISTS update_fact_daily_prices_modtime ON fact_daily_prices;
CREATE TRIGGER update_fact_daily_prices_modtime
BEFORE UPDATE ON fact_daily_prices
FOR EACH ROW EXECUTE FUNCTION update_modified_column();
