"""
pipeline.py - Luigi Orchestration Pipeline for BI Food Price ETL
=================================================================
Phase 4: Orchestrates the Extract → Transform → Load pipeline using
Luigi task dependencies and LocalTarget state management.

Features:
  - Strict dependency chain: ExtractTask → TransformTask → LoadTask
  - Success marker logic for empty API days (holidays/weekends)
  - Intermediate data persisted as JSON/CSV for auditability
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

import luigi
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup — ensure scripts/ is importable from dags/
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from extract import fetch_food_prices   # noqa: E402
from transform import transform_data    # noqa: E402
from load import load_data              # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline")

# ---------------------------------------------------------------------------
# Directories for intermediate files and markers
# ---------------------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Marker file naming convention
# ---------------------------------------------------------------------------
EMPTY_MARKER_PREFIX = "_SUCCESS_empty_data_"


def _empty_marker_path(run_date: str) -> Path:
    """Return the path for the empty-data success marker file."""
    return DATA_DIR / f"{EMPTY_MARKER_PREFIX}{run_date}.txt"


def _is_empty_run(run_date: str) -> bool:
    """Check if this run was marked as empty by ExtractTask."""
    return _empty_marker_path(run_date).exists()


# ===================================================================
# TASK 1: ExtractTask
# ===================================================================
class ExtractTask(luigi.Task):
    """
    Fetch raw data from the Bank Indonesia API.

    If the API returns an empty payload (e.g., weekend/holiday),
    creates a marker file so downstream tasks can skip gracefully.
    """

    run_date = luigi.Parameter(default=datetime.now().strftime("%Y%m%d"))
    prov_id = luigi.IntParameter(default=12)
    com_id = luigi.IntParameter(default=11)
    price_type_id = luigi.IntParameter(default=1)
    is_pasokan = luigi.IntParameter(default=1)

    def output(self):
        return luigi.LocalTarget(str(DATA_DIR / f"raw_{self.run_date}.json"))

    def run(self):
        # Build the date string the BI API expects (e.g., "20 April 2026")
        dt = datetime.strptime(str(self.run_date), "%Y%m%d")
        date_str = dt.strftime("%d %B %Y")

        params = {
            "ProvId": self.prov_id,
            "PriceTypeId": self.price_type_id,
            "ComId": self.com_id,
            "date": date_str,
            "isPasokan": self.is_pasokan,
        }

        logger.info("ExtractTask: Fetching data for %s", date_str)

        try:
            raw_json = fetch_food_prices(params=params)
        except Exception as e:
            logger.error("ExtractTask: Extraction failed: %s", e)
            raw_json = {}

        if not raw_json:
            # ----- Empty data: create success marker -----
            marker = _empty_marker_path(str(self.run_date))
            marker.write_text(
                f"Empty data for {date_str}. "
                f"Likely a holiday or non-reporting day.\n"
                f"Timestamp: {datetime.now().isoformat()}\n"
            )
            logger.warning(
                "ExtractTask: Empty data. Marker created at %s", marker
            )
            # Still write an empty JSON so output() target exists
            with self.output().open("w") as f:
                json.dump({}, f)
        else:
            with self.output().open("w") as f:
                json.dump(raw_json, f, ensure_ascii=False)
            logger.info("ExtractTask: Raw data saved to %s", self.output().path)


# ===================================================================
# TASK 2: TransformTask
# ===================================================================
class TransformTask(luigi.Task):
    """
    Transform raw JSON into a clean DataFrame and save as CSV.

    Skips if ExtractTask flagged the run as empty (holiday marker).
    """

    run_date = luigi.Parameter(default=datetime.now().strftime("%Y%m%d"))
    prov_id = luigi.IntParameter(default=12)
    com_id = luigi.IntParameter(default=11)
    price_type_id = luigi.IntParameter(default=1)
    is_pasokan = luigi.IntParameter(default=1)

    def requires(self):
        return ExtractTask(
            run_date=self.run_date,
            prov_id=self.prov_id,
            com_id=self.com_id,
            price_type_id=self.price_type_id,
            is_pasokan=self.is_pasokan,
        )

    def output(self):
        return luigi.LocalTarget(str(DATA_DIR / f"clean_{self.run_date}.csv"))

    def run(self):
        # ----- Check for empty marker -----
        if _is_empty_run(str(self.run_date)):
            logger.info(
                "TransformTask: Skipping — empty data marker exists for %s.",
                self.run_date,
            )
            with self.output().open("w") as f:
                f.write("")  # Empty file so target exists
            return

        # Read raw JSON from ExtractTask output
        with self.input().open("r") as f:
            raw_json = json.load(f)

        if not raw_json:
            logger.warning("TransformTask: Raw JSON is empty. Skipping.")
            with self.output().open("w") as f:
                f.write("")
            return

        # Run transformation
        df_clean = transform_data(raw_json, commodity_id=int(self.com_id))

        if df_clean.empty:
            logger.warning("TransformTask: No rows after transformation.")
            with self.output().open("w") as f:
                f.write("")
            return

        # Save clean CSV — write directly to path (pandas to_csv needs
        # a real file path or binary handle, not Luigi's text wrapper)
        output_path = self.output().path
        df_clean.to_csv(output_path, index=False)

        logger.info(
            "TransformTask: Saved %d clean rows to %s",
            len(df_clean),
            output_path,
        )


# ===================================================================
# TASK 3: LoadTask
# ===================================================================
class LoadTask(luigi.Task):
    """
    Load clean CSV data into the PostgreSQL Data Warehouse.

    Skips if ExtractTask flagged the run as empty (holiday marker).
    """

    run_date = luigi.Parameter(default=datetime.now().strftime("%Y%m%d"))
    prov_id = luigi.IntParameter(default=12)
    com_id = luigi.IntParameter(default=11)
    price_type_id = luigi.IntParameter(default=1)
    is_pasokan = luigi.IntParameter(default=1)

    def requires(self):
        return TransformTask(
            run_date=self.run_date,
            prov_id=self.prov_id,
            com_id=self.com_id,
            price_type_id=self.price_type_id,
            is_pasokan=self.is_pasokan,
        )

    def output(self):
        return luigi.LocalTarget(
            str(DATA_DIR / f"_SUCCESS_load_{self.run_date}.txt")
        )

    def run(self):
        # ----- Check for empty marker -----
        if _is_empty_run(str(self.run_date)):
            logger.info(
                "LoadTask: Skipping — empty data marker exists for %s.",
                self.run_date,
            )
            with self.output().open("w") as f:
                f.write(
                    f"Skipped: No data to load for {self.run_date} "
                    f"(empty API response).\n"
                    f"Timestamp: {datetime.now().isoformat()}\n"
                )
            return

        # Read clean CSV from TransformTask output
        with self.input().open("r") as f:
            df = pd.read_csv(f)

        if df.empty:
            logger.warning("LoadTask: Clean CSV is empty. Nothing to load.")
            with self.output().open("w") as f:
                f.write(
                    f"Skipped: Empty CSV for {self.run_date}.\n"
                    f"Timestamp: {datetime.now().isoformat()}\n"
                )
            return

        # Execute UPSERT into fact_daily_prices
        rows_loaded = load_data(df)

        # Write success marker
        with self.output().open("w") as f:
            f.write(
                f"Success: Loaded {rows_loaded} rows for {self.run_date}.\n"
                f"Timestamp: {datetime.now().isoformat()}\n"
            )

        logger.info(
            "LoadTask: Successfully loaded %d rows for %s.",
            rows_loaded,
            self.run_date,
        )


# ===================================================================
# TASK 4: DailyPipelineWrapper
# ===================================================================
class DailyPipelineWrapper(luigi.WrapperTask):
    """
    Wrapper task to orchestrate the pipeline for ALL 7 targeted 
    provinces and 21 commodities automatically.
    """

    run_date = luigi.Parameter(default=datetime.now().strftime("%Y%m%d"))

    def requires(self):
        PROVINCES = [11, 12, 13, 14, 15, 16, 17]
        COMMODITIES = list(range(1, 22))
        PRICE_TYPES = [1, 2, 3, 4]

        for prov_id in PROVINCES:
            for com_id in COMMODITIES:
                for price_type_id in PRICE_TYPES:
                    yield LoadTask(
                        run_date=self.run_date,
                        prov_id=prov_id,
                        com_id=com_id,
                        price_type_id=price_type_id
                    )


# ===================================================================
# Entry Point
# ===================================================================
if __name__ == "__main__":
    luigi.run()
