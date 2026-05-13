#!/usr/bin/env bash
# ==============================================================
# run_pipeline.sh - Cron-ready ETL Pipeline Runner
# ==============================================================
# This script is designed to be called by crontab to execute the
# Luigi-orchestrated ETL pipeline daily.
#
# Usage (manual):
#   bash run_pipeline.sh
#   bash run_pipeline.sh --run-date 20260420
#
# Crontab example (run daily at 17:00 WIB):
#   0 17 * * * /absolute/path/to/run_pipeline.sh >> /absolute/path/to/logs/pipeline_cron.log 2>&1
# ==============================================================

set -euo pipefail

# ----------------------------------------------------------
# Paths
# ----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
LOG_DIR="${SCRIPT_DIR}/logs"
DAG_FILE="${SCRIPT_DIR}/dags/pipeline.py"

# ----------------------------------------------------------
# Create logs directory if it doesn't exist
# ----------------------------------------------------------
mkdir -p "${LOG_DIR}"

# ----------------------------------------------------------
# Activate virtual environment
# ----------------------------------------------------------
echo "=============================================="
echo "  ETL Pipeline - $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
echo "[INFO] Activating virtual environment..."
source "${VENV_DIR}/bin/activate"
echo "[OK]   Virtual environment activated ($(python3 --version))"

# ----------------------------------------------------------
# Determine run date (default: today in YYYYMMDD format)
# ----------------------------------------------------------
RUN_DATE="${1:-$(date '+%Y%m%d')}"
echo "[INFO] Run date: ${RUN_DATE}"

# ----------------------------------------------------------
# Execute the Luigi pipeline
# ----------------------------------------------------------
# Running DailyPipelineWrapper triggers the full chain for all combinations:
#   DailyPipelineWrapper → yields multiple LoadTask
echo "[INFO] Starting Luigi pipeline..."
python "${DAG_FILE}" DailyPipelineWrapper \
    --run-date "${RUN_DATE}" \
    --workers 2 \
    --local-scheduler \
    2>&1 | tee -a "${LOG_DIR}/pipeline_cron.log"

EXIT_CODE=${PIPESTATUS[0]}

# ----------------------------------------------------------
# Summary
# ----------------------------------------------------------
if [ ${EXIT_CODE} -eq 0 ]; then
    echo "[OK]   Pipeline completed successfully."
else
    echo "[FAIL] Pipeline exited with code ${EXIT_CODE}."
fi

echo "=============================================="
echo "  Pipeline finished at $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="


# ===================================================================
# Housekeeping: Clean up intermediate files older than 7 days
# ===================================================================
echo "[INFO] Menjalankan pembersihan file data lama..."

# Definisikan path folder data Anda
DATA_DIR="/home/nulltribe/MEGAsync/Project/upgrade-skills/foodprice-pipeline/data"

# Hapus file raw JSON yang lebih tua dari 7 hari
find "$DATA_DIR" -type f -name "raw_*.json" -mtime +7 -delete

# Hapus file clean CSV yang lebih tua dari 7 hari
find "$DATA_DIR" -type f -name "clean_*.csv" -mtime +7 -delete

# Hapus file marker sukses yang lebih tua dari 7 hari
find "$DATA_DIR" -type f -name "_SUCCESS_load_*.txt" -mtime +7 -delete

echo "[OK] Pembersihan selesai."