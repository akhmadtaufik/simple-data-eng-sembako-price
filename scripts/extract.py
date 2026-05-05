"""
extract.py - Data Extraction Script for Bank Indonesia Food Price API
=====================================================================
Phase 1: Fetches raw JSON data from the BI Harga Pangan API with
robust retry logic and empty-payload handling.

API URLs are loaded from the project .env file using python-dotenv.
"""

import os
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type,
    before_sleep_log,
)

# ---------------------------------------------------------------------------
# Environment Configuration
# ---------------------------------------------------------------------------
# Load .env from the project root (one level up from scripts/)
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
logger = logging.getLogger("extract")

# ---------------------------------------------------------------------------
# Constants (loaded from .env)
# ---------------------------------------------------------------------------
BI_API_DETAIL_GRID = os.getenv("BI_API_DETAIL_GRID")
if not BI_API_DETAIL_GRID:
    raise ValueError("BI_API_DETAIL_GRID environment variable is not set")
REQUEST_TIMEOUT_SECONDS = 30


# ---------------------------------------------------------------------------
# Extraction Function
# ---------------------------------------------------------------------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def fetch_food_prices(url: str | None = None, params: dict | None = None, session: requests.Session | None = None) -> dict:
    """
    Fetch food price data from the Bank Indonesia API.

    Implements a retry mechanism via tenacity:
      - Retries up to 3 times on any RequestException
        (ConnectionError, Timeout, HTTPError, etc.).
      - Waits 2 seconds between each retry attempt.

    Parameters
    ----------
    url : str | None
        The API endpoint URL. Defaults to BI_API_DETAIL_GRID from .env.
    params : dict | None
        Query parameters to send with the GET request.
    session: requests.Session | None
        An optional requests.Session object for connection pooling and headers.

    Returns
    -------
    dict
        The parsed JSON response. Returns an empty dict ``{}`` if the
        payload data array is empty or missing.
    """
    if url is None:
        url = BI_API_DETAIL_GRID

    logger.info("Fetching data from %s (params=%s)", url, params)

    if session:
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    else:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)

    # Raise HTTPError for 4xx/5xx responses so tenacity can retry on them
    response.raise_for_status()

    try:
        json_payload = response.json()
    except requests.exceptions.JSONDecodeError:
        logger.error("Response is not valid JSON. Body: %s", response.text[:500])
        return {}

    # ----- Empty payload guard -----
    # The API may return a valid 200 response with an empty data array,
    # e.g. on weekends or public holidays when markets are closed.
    data = json_payload.get("data", [])

    if not data or len(data) == 0:
        logger.warning(
            "API returned an EMPTY data payload. "
            "This may indicate a holiday or non-reporting day. "
            "Returning empty dict safely."
        )
        return {}

    logger.info("Successfully fetched %d record(s).", len(data))
    return json_payload


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    """Run the extraction process with sample query parameters."""
    logger.info("=" * 60)
    logger.info("Starting Bank Indonesia Food Price Extraction")
    logger.info("=" * 60)
    logger.info("API URL loaded from .env: %s", BI_API_DETAIL_GRID)

    # Sample query parameters for testing the BI API
    sample_params = {
        "ProvId": 12,
        "PriceTypeId": 1,
        "ComId": 11,
        "date": "20 April 2026",
        "isPasokan": 1,
    }

    try:
        result = fetch_food_prices(params=sample_params)
    except requests.exceptions.RequestException as e:
        logger.error(
            "All retry attempts exhausted. Request failed: %s", e
        )
        result = {}

    if not result:
        logger.info("No data extracted. Pipeline will mark this run as empty.")
    else:
        record_count = len(result.get("data", []))
        logger.info("Extraction complete. Total records: %d", record_count)

    logger.info("=" * 60)
    logger.info("Extraction process finished.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
