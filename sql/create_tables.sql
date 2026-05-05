-- ============================================================
-- Food Price Data Warehouse - DDL
-- Database: foodprice_dw
-- Schema  : Star Schema (Dimension + Fact tables)
-- ============================================================

-- ==========================
-- Dimensi Waktu
-- ==========================
CREATE TABLE IF NOT EXISTS dim_dates (
    date_id         INT PRIMARY KEY,
    full_date       DATE NOT NULL UNIQUE,
    year            INT NOT NULL,
    quarter         INT NOT NULL,
    month           INT NOT NULL,
    month_name      VARCHAR(20) NOT NULL,
    day             INT NOT NULL,
    day_of_week     INT NOT NULL,
    day_name        VARCHAR(20) NOT NULL,
    is_weekend      BOOLEAN NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================
-- Dimensi Wilayah
-- ==========================
CREATE TABLE IF NOT EXISTS dim_provinces (
    province_id     INT PRIMARY KEY,
    province_name   VARCHAR(100) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dim_regencies (
    regency_id      INT PRIMARY KEY,
    province_id     INT NOT NULL,
    regency_name    VARCHAR(100) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_province
        FOREIGN KEY (province_id)
        REFERENCES dim_provinces (province_id)
);

-- ==========================
-- Dimensi Pasar
-- ==========================
CREATE TABLE IF NOT EXISTS dim_market_types (
    market_type_id      INT PRIMARY KEY,
    market_type_name    VARCHAR(50) NOT NULL,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dim_markets (
    market_id       INT PRIMARY KEY,
    regency_id      INT NOT NULL,
    market_type_id  INT NOT NULL,
    market_name     VARCHAR(150) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_regency
        FOREIGN KEY (regency_id)
        REFERENCES dim_regencies (regency_id),
    CONSTRAINT fk_market_type
        FOREIGN KEY (market_type_id)
        REFERENCES dim_market_types (market_type_id)
);

-- ==========================
-- Dimensi Komoditas
-- ==========================
CREATE TABLE IF NOT EXISTS dim_commodity_groups (
    group_id        INT PRIMARY KEY,
    group_name      VARCHAR(100) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dim_commodities (
    commodity_id    INT PRIMARY KEY,
    group_id        INT NOT NULL,
    commodity_name  VARCHAR(150) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_commodity_group
        FOREIGN KEY (group_id)
        REFERENCES dim_commodity_groups (group_id)
);

-- ==========================
-- Fakta Harga Harian
-- ==========================
CREATE TABLE IF NOT EXISTS fact_daily_prices (
    price_id        SERIAL PRIMARY KEY,
    date_id         INT NOT NULL,
    market_id       INT NOT NULL,
    commodity_id    INT NOT NULL,
    price           NUMERIC(12, 2) NOT NULL,
    is_pasokan      INT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_date
        FOREIGN KEY (date_id)
        REFERENCES dim_dates (date_id),
    CONSTRAINT fk_market
        FOREIGN KEY (market_id)
        REFERENCES dim_markets (market_id),
    CONSTRAINT fk_commodity
        FOREIGN KEY (commodity_id)
        REFERENCES dim_commodities (commodity_id),
    CONSTRAINT unique_daily_price
        UNIQUE (date_id, market_id, commodity_id)
);
