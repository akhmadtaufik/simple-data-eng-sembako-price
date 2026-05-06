"""
backfill.py - Synchronous Historical Data Backfill for BI Food Prices
==========================================================================
Implements a "Weekly Friday Jump" strategy with stealth mechanics to avoid
IP blocking, and dual-logging for monitoring.
"""

import os
import time
import random
import logging
from datetime import date, timedelta
from pathlib import Path
from logging.handlers import RotatingFileHandler

import requests

from extract import fetch_food_prices
from transform import transform_data
from load import load_data

# ---------------------------------------------------------------------------
# Setup Paths & Dual-Logging
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "backfill_2025.log"

logger = logging.getLogger("backfill")
logger.setLevel(logging.INFO)

log_format = "%(asctime)s | %(levelname)-8s | %(message)s"
formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

# Rotating File Handler (Max 5MB, keep 3 backups)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Stream Handler (Terminal output)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# ---------------------------------------------------------------------------
# Constants & Stealth Config
# ---------------------------------------------------------------------------
PROVINCE_IDS = [11, 12, 13, 14, 15, 16, 17]
COMMODITY_IDS = list(range(1, 22))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


def get_2025_fridays() -> list[date]:
    """Generate a list of dates for every Friday in 2025."""
    start_date = date(2025, 1, 3)  # First Friday of 2025
    end_date = date(2025, 12, 26)  # Last Friday of 2025

    fridays = []
    current = start_date
    while current <= end_date:
        fridays.append(current)
        current += timedelta(days=7)

    return fridays


# ---------------------------------------------------------------------------
# Execution Logic
# ---------------------------------------------------------------------------
def run_backfill():
    fridays = get_2025_fridays()
    total_dates = len(fridays)
    logger.info(f"Starting backfill for {total_dates} Fridays in 2025.")

    session = requests.Session()

    for idx, dt in enumerate(fridays, 1):
        date_str = dt.strftime("%Y-%m-%d")
        logger.info(f"--- Processing Date {idx}/{total_dates}: {date_str} ---")

        for prov_id in PROVINCE_IDS:
            for com_id in COMMODITY_IDS:
                # Assign a random User-Agent for this request to rotate identity
                session.headers.update({"User-Agent": random.choice(USER_AGENTS)})

                params = {
                    "ProvId": prov_id,
                    "PriceTypeId": 1,
                    "ComId": com_id,
                    "date": date_str,
                    "isPasokan": 1,
                }

                try:
                    # 1. Extract
                    raw_data = fetch_food_prices(params=params, session=session)

                    if raw_data:
                        # 2. Transform
                        df_clean = transform_data(raw_data, commodity_id=com_id)

                        # 3. Load
                        rows_upserted = load_data(df_clean)
                        logger.info(
                            f"Success | Date: {date_str} | Province: {prov_id} | Commodity: {com_id} | Rows Upserted: {rows_upserted}"
                        )
                    else:
                        logger.info(
                            f"Empty Data | Date: {date_str} | Province: {prov_id} | Commodity: {com_id} | Rows Upserted: 0"
                        )

                except requests.exceptions.RequestException as e:
                    # Graceful Backoff if we hit a WAF block or Rate Limit
                    if getattr(
                        e, "response", None
                    ) is not None and e.response.status_code in (429, 403):
                        logger.critical(
                            f"Blocked! HTTP {e.response.status_code} received. Enforcing a long sleep of 120s..."
                        )
                        time.sleep(120)
                    else:
                        logger.error(
                            f"RequestException fetching Date: {date_str}, Prov: {prov_id}, Com: {com_id} -> {e}"
                        )

                except Exception as e:
                    logger.error(
                        f"Unexpected Error on Date: {date_str}, Prov: {prov_id}, Com: {com_id} -> {e}"
                    )

                finally:
                    # Dynamic Jitter after every request
                    jitter = random.uniform(2.5, 6.0)
                    time.sleep(jitter)


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Initializing 2025 Backfill Pipeline (Weekly Friday Jump)")
    logger.info("=" * 60)

    try:
        run_backfill()
    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user.")

    logger.info("=" * 60)
    logger.info("Backfill Pipeline Execution Completed")
    logger.info("=" * 60)
