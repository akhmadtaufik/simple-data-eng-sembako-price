#!/usr/bin/env bash
# ==============================================================
# setup.sh - Project Initialization Script
# ==============================================================
# Orchestrates the entire setup process:
# 1. Virtual Environment & Dependencies
# 2. Docker Compose (PostgreSQL)
# 3. DB Initialization Wait Logic
# 4. Master Data Seeding (Phase 0)
# ==============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

echo "=============================================="
echo "  Food Price Pipeline - Environment Setup"
echo "=============================================="

# ----------------------------------------------------------
# Step 1: Create virtual environment (if not exists)
# ----------------------------------------------------------
if [ -d "${VENV_DIR}" ]; then
    echo "[INFO] Virtual environment already exists at ${VENV_DIR}"
else
    echo "[INFO] Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
    echo "[OK]   Virtual environment created at ${VENV_DIR}"
fi

# ----------------------------------------------------------
# Step 2: Activate virtual environment
# ----------------------------------------------------------
echo "[INFO] Activating virtual environment..."
source "${VENV_DIR}/bin/activate"
echo "[OK]   Virtual environment activated ($(python3 --version))"

# ----------------------------------------------------------
# Step 3: Upgrade pip & Install dependencies
# ----------------------------------------------------------
echo "[INFO] Upgrading pip..."
pip install --upgrade pip --quiet

echo "[INFO] Installing pipenv..."
pip install pipenv --quiet

echo "[INFO] Installing project dependencies from Pipfile..."
cd "${SCRIPT_DIR}"
pipenv install --system --deploy 2>/dev/null || pipenv install --system
echo "[OK]   All dependencies installed successfully."

# ----------------------------------------------------------
# Step 4: Spin up PostgreSQL via Docker Compose
# ----------------------------------------------------------
echo "[INFO] Spinning up PostgreSQL infrastructure..."
cd "${SCRIPT_DIR}/docker"
docker compose up -d --build
cd "${SCRIPT_DIR}"
echo "[OK]   Docker containers started."

# ----------------------------------------------------------
# Step 5: Wait for PostgreSQL Initialization
# ----------------------------------------------------------
# Load variables from .env
if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
fi

echo "[INFO] Waiting for PostgreSQL to become ready..."
MAX_RETRIES=30
RETRY_COUNT=0
# Loop until pg_isready succeeds on the container
while ! docker compose -f "${SCRIPT_DIR}/docker/docker-compose.yml" exec -T postgres pg_isready -U "${POSTGRES_USER:-foodprice_admin}" -d "${POSTGRES_DB:-foodprice_dw}" > /dev/null 2>&1; do
    echo -n "."
    sleep 2
    RETRY_COUNT=$((RETRY_COUNT+1))
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo ""
        echo "[ERROR] PostgreSQL failed to start within 60 seconds. Exiting."
        exit 1
    fi
done

echo ""
echo "[INFO] PostgreSQL is accepting connections."
# The Postgres Docker entrypoint runs init scripts (DDL + Date Seeding) and then restarts.
# We sleep an additional 10 seconds to guarantee the DDL scripts have completely finished
# and the DB is fully ready for external Python queries to avoid race conditions.
echo "[INFO] Waiting 10 seconds for initial DDL and DML scripts to finalize..."
sleep 10
echo "[OK]   Database is fully initialized."

# ----------------------------------------------------------
# Step 6: Execute Python Master Data Seeding
# ----------------------------------------------------------
echo "[INFO] Executing master data seeding script (Phase 0)..."
python scripts/seed_dimensions.py
echo "[OK]   Master data effectively seeded."

# ----------------------------------------------------------
# Summary
# ----------------------------------------------------------
echo ""
echo "=============================================="
echo "  Infrastructure & Master Data Ready!"
echo "=============================================="
echo ""
echo "  To activate the environment manually:"
echo "    source ${VENV_DIR}/bin/activate"
echo ""
echo "  To run the extraction script:"
echo "    python scripts/extract.py"
echo ""
echo "  To run the entire Airflow/Luigi pipeline:"
echo "    bash run_pipeline.sh"
echo ""
