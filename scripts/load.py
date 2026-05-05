"""
load.py - Data Loading Script for Bank Indonesia Food Prices
=============================================================
Phase 3: Loads the clean pandas DataFrame into the PostgreSQL
Data Warehouse using raw SQL via psycopg2.

Key features:
  - Batch insertion via psycopg2.extras.execute_values
  - UPSERT logic (ON CONFLICT DO UPDATE) for idempotent loads
  - Connection credentials loaded from .env via python-dotenv
  - Strict try-except-finally for connection lifecycle management
"""

import os
import logging
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment Configuration
# ---------------------------------------------------------------------------
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("load")

# ---------------------------------------------------------------------------
# Database credentials from .env
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST"),
    "port": int(os.getenv("POSTGRES_PORT")),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "dbname": os.getenv("POSTGRES_DB"),
}

# ---------------------------------------------------------------------------
# UPSERT SQL — raw SQL, no ORM
# ---------------------------------------------------------------------------
UPSERT_SQL = """
    INSERT INTO fact_daily_prices (date_id, market_id, commodity_id, price)
    VALUES %s
    ON CONFLICT (date_id, market_id, commodity_id)
    DO UPDATE SET price = EXCLUDED.price
"""

# ---------------------------------------------------------------------------
# Auto-Register Markets SQL
# ---------------------------------------------------------------------------
AUTO_REGISTER_MARKETS_SQL = """
    INSERT INTO dim_markets (market_id, regency_id, market_type_id, market_name)
    SELECT data.market_id, r.regency_id, data.market_type_id, data.market_name
    FROM (VALUES %s) AS data(market_id, market_name, regency_name, market_type_id)
    JOIN dim_regencies r ON r.regency_name = data.regency_name
    ON CONFLICT (market_id) DO NOTHING
"""


# ---------------------------------------------------------------------------
# Main Loading Function
# ---------------------------------------------------------------------------
def load_data(df: pd.DataFrame) -> int:
    """
    Load a clean DataFrame into the fact_daily_prices table via UPSERT.

    Uses ``psycopg2.extras.execute_values`` for efficient batch insertion
    and ``ON CONFLICT DO UPDATE`` to handle revised prices from the BI API
    without creating duplicates.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: ``date_id``, ``market_id``,
        ``commodity_id``, ``price``.

    Returns
    -------
    int
        The number of rows successfully upserted.
    """
    if df.empty:
        logger.warning("DataFrame is empty. Nothing to load.")
        return 0

    # ------------------------------------------------------------------
    # Step 1: Prepare data — DataFrame → list of tuples
    # ------------------------------------------------------------------
    required_columns = ["date_id", "market_id", "commodity_id", "price", "market_name", "regency_name", "market_type_id"]

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"DataFrame is missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    # 1A. Prepare markets for auto-registration
    markets_df = df[['market_id', 'market_name', 'regency_name', 'market_type_id']].drop_duplicates(subset=['market_id'])
    market_records = list(markets_df.itertuples(index=False, name=None))
    logger.info("Prepared %d unique markets for potential auto-registration.", len(market_records))

    # 1B. Prepare facts
    fact_columns = ["date_id", "market_id", "commodity_id", "price"]
    fact_records = list(df[fact_columns].itertuples(index=False, name=None))
    logger.info("Prepared %d records for batch upsert.", len(fact_records))

    # ------------------------------------------------------------------
    # Step 2: Connect, execute, commit — with try-except-finally
    # ------------------------------------------------------------------
    conn = None
    cur = None
    rows_loaded = 0

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        logger.info(
            "Connected to PostgreSQL at %s:%s/%s",
            DB_CONFIG["host"],
            DB_CONFIG["port"],
            DB_CONFIG["dbname"],
        )

        # 2A. Auto-Register missing markets via INSERT ... ON CONFLICT DO NOTHING
        execute_values(cur, AUTO_REGISTER_MARKETS_SQL, market_records)
        markets_added = cur.rowcount
        if markets_added > 0:
            logger.info("Auto-registered %d new market(s).", markets_added)

        # 2B. Batch upsert facts via execute_values (much faster than row-by-row)
        execute_values(cur, UPSERT_SQL, fact_records)
        rows_loaded = cur.rowcount

        conn.commit()
        logger.info("UPSERT complete. %d fact row(s) affected.", rows_loaded)

    except psycopg2.Error as e:
        logger.error("Database error during load: %s", e)
        if conn:
            conn.rollback()
            logger.info("Transaction rolled back.")
        raise

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
            logger.info("Database connection closed.")

    return rows_loaded


# ---------------------------------------------------------------------------
# Standalone test — runs extract → transform → load
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from extract import fetch_food_prices
    from transform import transform_data

    logger.info("=" * 60)
    logger.info("Running Load Test (extract → transform → load)")
    logger.info("=" * 60)

    # Test parameters: Beras (commodity 11), Jawa Barat (province 12)
    test_params = {
        "ProvId": 12,
        "PriceTypeId": 1,
        "ComId": 11,
        "date": "20 April 2026",
        "isPasokan": 1,
    }

    try:
        # Phase 1: Extract
        raw = fetch_food_prices(params=test_params)

        if not raw:
            logger.info("No data extracted. Skipping transform and load.")
        else:
            # Phase 2: Transform
            df_clean = transform_data(raw, commodity_id=test_params["ComId"])

            if df_clean.empty:
                logger.info("Transform returned empty DataFrame. Skipping load.")
            else:
                print("\n" + "=" * 60)
                print("DATA TO LOAD (first 5 rows):")
                print("=" * 60)
                print(df_clean.head(5).to_string(index=False))
                print(f"\nTotal rows to load: {len(df_clean)}")

                # Phase 3: Load
                rows = load_data(df_clean)
                print(
                    f"\n✅ Successfully upserted {rows} row(s) into fact_daily_prices."
                )

    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)

    logger.info("=" * 60)
    logger.info("Load test finished.")
    logger.info("=" * 60)
