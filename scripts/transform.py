"""
transform.py - Data Transformation Script for Bank Indonesia Food Prices
========================================================================
Phase 2: Transforms raw JSON from the BI API into a clean, analysis-ready
pandas DataFrame matching the star-schema design of the Data Warehouse.

Key transformations:
  1. Granularity filtering  — keep only level 3 (market-level) rows
  2. Unpivoting (melt)      — pivot date-columns into date/price rows
  3. Data cleaning           — coerce invalid prices, parse date formats
  4. Schema alignment        — output columns matching fact_daily_prices
"""

import re
import logging
import pandas as pd

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("transform")

# ---------------------------------------------------------------------------
# Regex pattern to identify date columns in DD/MM/YYYY format
# ---------------------------------------------------------------------------
DATE_COLUMN_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")


# ---------------------------------------------------------------------------
# Main Transformation Function
# ---------------------------------------------------------------------------
def transform_data(raw_json: dict, commodity_id: int) -> pd.DataFrame:
    """
    Transform raw BI API JSON into a clean DataFrame for warehouse loading.

    Parameters
    ----------
    raw_json : dict
        The full JSON response from the BI API. Must contain a ``data``
        key with a list of record dicts.
    commodity_id : int
        The commodity ID to attach to every row (passed from the
        extraction step's query parameters).

    Returns
    -------
    pd.DataFrame
        A clean DataFrame with columns:
        ``date_id``, ``full_date``, ``market_id``, ``commodity_id``, ``price``

        Returns an empty DataFrame with the correct columns if the input
        data is empty or yields no valid rows after cleaning.
    """
    output_columns = [
        "date_id", "full_date", "market_id", "market_name",
        "regency_name", "market_type_id", "commodity_id", "price"
    ]

    # ------------------------------------------------------------------
    # Step 0: Extract the data array from the JSON payload
    # ------------------------------------------------------------------
    data = raw_json.get("data", [])

    if not data:
        logger.warning("Input JSON has no 'data' array or it is empty.")
        return pd.DataFrame(columns=output_columns)

    df = pd.DataFrame(data)
    logger.info("Loaded %d raw rows from API payload.", len(df))

    # ------------------------------------------------------------------
    # Step 1: Granularity Filtering — keep ONLY level 3 (market detail)
    # ------------------------------------------------------------------
    # The BI API mixes aggregation levels in a single response:
    #   level 0 = National average
    #   level 1 = Province average
    #   level 2 = Regency/City average
    #   level 3 = Individual market (the actual data we need)
    # Keeping levels 0–2 would cause double-counting in aggregations.
    if "level" not in df.columns:
        logger.warning("Column 'level' not found. Cannot filter granularity.")
        return pd.DataFrame(columns=output_columns)

    rows_before = len(df)
    df = df[df["level"] == 3].copy()
    rows_after = len(df)
    logger.info(
        "Granularity filter: kept %d of %d rows (level == 3).",
        rows_after,
        rows_before,
    )

    if df.empty:
        logger.warning("No level-3 rows found after filtering.")
        return pd.DataFrame(columns=output_columns)

    # ------------------------------------------------------------------
    # Step 2: Identify date columns and non-date (metadata) columns
    # ------------------------------------------------------------------
    date_columns = [col for col in df.columns if DATE_COLUMN_PATTERN.match(col)]
    metadata_columns = [col for col in df.columns if col not in date_columns]

    if not date_columns:
        logger.warning("No date columns (DD/MM/YYYY) found in the data.")
        return pd.DataFrame(columns=output_columns)

    logger.info(
        "Detected %d date columns: %s … %s",
        len(date_columns),
        date_columns[0],
        date_columns[-1],
    )

    # ------------------------------------------------------------------
    # Step 3: Unpivot (Melt) — date columns become rows
    # ------------------------------------------------------------------
    df_melted = pd.melt(
        df,
        id_vars=["id", "name", "category"],
        value_vars=date_columns,
        var_name="date_string",
        value_name="price",
    )
    logger.info("Unpivoted into %d rows.", len(df_melted))

    # ------------------------------------------------------------------
    # Step 4: Data Cleaning & Formatting
    # ------------------------------------------------------------------

    # 4a. Coerce price to numeric — handles "-", "", None, and other
    #     non-numeric strings by converting them to NaN.
    df_melted["price"] = pd.to_numeric(df_melted["price"], errors="coerce")

    # 4b. Drop rows where price is NaN (no valid price data)
    rows_before_drop = len(df_melted)
    df_melted = df_melted.dropna(subset=["price"]).copy()
    rows_dropped = rows_before_drop - len(df_melted)

    if rows_dropped > 0:
        logger.info("Dropped %d rows with invalid/missing prices.", rows_dropped)

    if df_melted.empty:
        logger.warning("No valid price data remaining after cleaning.")
        return pd.DataFrame(columns=output_columns)

    # 4c. Parse date_string (DD/MM/YYYY) into proper date objects
    df_melted["full_date"] = pd.to_datetime(df_melted["date_string"], format="%d/%m/%Y")

    # 4d. Create date_id as YYYYMMDD integer (matches dim_dates.date_id)
    df_melted["date_id"] = df_melted["full_date"].dt.strftime("%Y%m%d").astype(int)

    # 4e. Format full_date as YYYY-MM-DD string (matches dim_dates.full_date)
    df_melted["full_date"] = df_melted["full_date"].dt.strftime("%Y-%m-%d")

    # 4f. Rename columns and add commodity_id
    df_melted = df_melted.rename(columns={
        "id": "market_id",
        "name": "market_name",
        "category": "regency_name"
    })
    df_melted["commodity_id"] = commodity_id

    # 4g. Clean regency_name and derive market_type_id
    df_melted["regency_name"] = df_melted["regency_name"].str.replace("Kab. ", "Kabupaten ", regex=False).str.strip()
    
    df_melted["market_type_id"] = 1
    df_melted.loc[df_melted["market_name"].str.contains("Modern", case=False, na=False), "market_type_id"] = 2
    df_melted.loc[df_melted["market_name"].str.contains("Besar", case=False, na=False), "market_type_id"] = 3

    # ------------------------------------------------------------------
    # Step 5: Final Output — select and order columns
    # ------------------------------------------------------------------
    df_clean = df_melted[output_columns].reset_index(drop=True)

    logger.info(
        "Transformation complete. Output: %d rows × %d columns.",
        len(df_clean),
        len(df_clean.columns),
    )

    return df_clean


# ---------------------------------------------------------------------------
# Standalone test — runs extract + transform together for verification
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from extract import fetch_food_prices

    logger.info("=" * 60)
    logger.info("Running Transform Test (extract → transform)")
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
        raw = fetch_food_prices(params=test_params)
    except Exception as e:
        logger.error("Extraction failed: %s", e)
        raw = {}

    if raw:
        df_result = transform_data(raw, commodity_id=test_params["ComId"])
        if not df_result.empty:
            print("\n" + "=" * 60)
            print("SAMPLE OUTPUT (first 10 rows):")
            print("=" * 60)
            print(df_result.head(10).to_string(index=False))
            print(f"\nTotal rows: {len(df_result)}")
            print(f"Columns:    {list(df_result.columns)}")
            print(f"Dtypes:\n{df_result.dtypes}")
        else:
            logger.info("Transform returned an empty DataFrame.")
    else:
        logger.info("No data to transform.")

    logger.info("=" * 60)
    logger.info("Transform test finished.")
    logger.info("=" * 60)
