# 🇮🇩 Bank Indonesia Food Price ETL Pipeline

![Python](https://img.shields.io/badge/Python-3.12-blue.svg?style=flat-square&logo=python)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16.0-336791.svg?style=flat-square&logo=postgresql)
![Luigi](https://img.shields.io/badge/Orchestration-Luigi-00b8d9.svg?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?style=flat-square&logo=docker)
![Status](https://img.shields.io/badge/Status-Production-success.svg?style=flat-square)

## 1. Project Overview & Core Architecture

The **Bank Indonesia Food Price ETL Pipeline** is an end-to-end, enterprise-grade Data Engineering orchestration layer designed to extract daily staple food commodity prices (*"sembako"*) directly from the Bank Indonesia public API. 

The system scales across **7 Indonesian provinces** and monitors **21 distinct commodities**. It systematically ingests semi-structured, heavily nested JSON payloads and applies rigorous transformations to load the cleaned data into a high-performance **Star Schema Data Warehouse** powered by PostgreSQL.

This repository prioritizes idempotency, fault tolerance, and spatial enrichment, providing a single source of truth for temporal and geospatial food pricing analytics.

---

## 2. Repository Blueprint

```text
foodprice-pipeline/
├── backups/                        # Local compressed snapshot archives (*.sql.gz)
├── dags/
│   └── pipeline.py                 # Central Luigi orchestration workflow and dependency graphs
├── docker/
│   └── docker-compose.yml          # Local PostgreSQL cluster and volume configuration
├── logs/                           # Automated ETL and database backup execution logs
├── scripts/
│   ├── extract.py                  # API ingestion and robust HTTP client logic
│   ├── transform.py                # Pandas-based cleaning, unpivoting, and type coercion
│   ├── load.py                     # Bulk upserts and database interaction layer
│   ├── geocode_new_markets.py      # Spatial enrichment via Nominatim OpenStreetMap API
│   └── backfill.py                 # Historical data reconstruction using Weekly Friday Jumps
├── sql/
│   ├── 01_ddl_schema.sql           # Data warehouse table creation and constraints
│   └── 02_seed_dimensions.sql      # Initial master data seeding scripts
├── setup.sh                        # Automated environment initialization and database bootstrapping
├── run_pipeline.sh                 # Cron-friendly shell entrypoint for daily pipeline execution
├── backup_db.sh                    # Automated PostgreSQL Docker backup & recovery CLI manager
├── Pipfile                         # Pipenv dependency declarations
└── Pipfile.lock                    # Deterministic dependency resolution tree
```

---

## 3. Data Warehouse Architecture & Schema Design

The target destination is `foodprice_dw`, a dedicated PostgreSQL Data Warehouse designed using a classic **Star Schema** architecture to optimize analytical querying and aggregations. Referential integrity is strictly enforced across all entities via Primary Key to Foreign Key constraints.

### 🌟 Fact Table
* **`fact_daily_prices`**: The central transactional table capturing granular daily price events at the lowest level of dimensionality (Date + Market + Commodity).

### 📐 Dimension Tables
* **`dim_dates`**: Enriched temporal dimension incorporating localized Indonesian day and month names, weekends, and holidays flags.
* **`dim_provinces`**: Top-level administrative divisions.
* **`dim_regencies`**: Secondary administrative divisions (Kabupaten/Kota), spatially enabled with centroids.
* **`dim_market_types`**: Categorization of selling locations (e.g., Pasar Tradisional, Pasar Modern).
* **`dim_commodity_groups`**: High-level groupings (e.g., Beras, Cabai).
* **`dim_commodities`**: Granular commodity definitions mapped to their respective groups.

---

## 4. ETL Pipeline & Luigi Workflow

Orchestration is natively handled by **Luigi**, building a robust Directed Acyclic Graph (DAG) that guarantees tasks are executed strictly when their upstream dependencies are satisfied.

1. **`ExtractTask`**: Fetches raw data using hardened HTTP clients. It incorporates a **weekend/holiday safety guard** that natively understands when markets are closed, gracefully terminating the pipeline without triggering downstream failures on empty payloads.
2. **`TransformTask`**: Resolves granularity mixing by filtering strictly for *level 3 market data*. Executes complex unpivoting (melting date columns into rows via Pandas), sanitizes edge-case values, coerces standard data types, and derives normalized market types.
3. **`LoadTask`**: Executes highly optimized bulk database operations using `psycopg2.extras.execute_values`. It features an **"Auto-Register Markets"** capability, ensuring that newly reporting locations are safely dynamically inserted into the dimension table before fact insertion, preventing constraint violations.
4. **`GeocodeNewMarketsTask`**: Automatically detects newly registered markets with `NULL` coordinate values. It interfaces with OpenStreetMap's Nominatim API to fetch high-precision geographic coordinates and applies a **smart fallback algorithm** that defaults to the parent regency's centroid for unresolvable abstract markets.

---

## 5. Resilience & Stealth Mechanics

To guarantee enterprise-grade reliability and respect API limits, the ingestion components are fortified with several protective layers:

* **Exponential Backoff & Retries**: Managed via the `tenacity` library, allowing the pipeline to seamlessly recover from transient network failures or intermittent 5xx server errors up to a maximum attempt threshold.
* **Identity Masking**: Utilizes dynamic User-Agent rotation to prevent aggressive blocking.
* **Rate-Limit Mitigation**: Implements intentional, randomized jitter delays (ranging from `1.5s` to `6.0s` sleep cycles) between sequential province/commodity requests to minimize server load on the Bank Indonesia endpoints.

---

## 6. Environment Setup & Quick Start

### Prerequisites
* Python 3.12+
* Docker & Docker Compose
* Pipenv (Virtual Environment Manager)

### Configuration
Create a `.env` file in the root directory (refer to `.env.example` if available):
```env
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=foodprice_dw
POSTGRES_HOST=localhost
POSTGRES_PORT=5434
```

### Initialization

We provide a zero-touch bootstrap script to establish the environment:

```bash
bash setup.sh
```

**What this script does:**
1. Instantiates a sterile Python `.venv` using `Pipenv` and resolves dependencies.
2. Spins up the Docker PostgreSQL cluster in detached mode.
3. Implements an active wait-loop health check until PostgreSQL is ready to accept connections.
4. Executes the DDL schemas and seeds the structural dimensional master data safely.

---

## 7. Production Operations & Automation

### Manual Pipeline Execution
To trigger the pipeline for a specific historical date (e.g., for ad-hoc patches):
```bash
pipenv run python dags/pipeline.py LoadTask --date 2026-06-01 --local-scheduler
```

### Automated Scheduling via Crontab
The pipeline is designed to run asynchronously daily. Below is the standard Crontab configuration to execute the pipeline at **15:00 WIB**:

```crontab
# Run daily ETL pipeline at 15:00 WIB
0 15 * * * /path/to/foodprice-pipeline/run_pipeline.sh >> /path/to/foodprice-pipeline/logs/pipeline_cron.log 2>&1
```

### Automatic Housekeeping
To prevent storage bloat, the pipeline incorporates self-maintenance logic. During execution, it automatically purges temporary data logs, staging JSON files, and target CSV markers older than **7 days**, preserving disk space gracefully.

### Historical Data Backfill
For initializing the data warehouse with year-to-date historical trends, utilize the specialized backfill script:
```bash
pipenv run python scripts/backfill.py --start-date 2026-01-01 --end-date 2026-06-01
```
This script implements a **"Weekly Friday Jump"** strategy, requesting chunked historical windows to bypass strict API pagination limits and rebuild the past robustly.

---

## 8. Database Backup & Disaster Recovery

The project includes an automated, production-ready backup and disaster recovery manager via [`backup_db.sh`](backup_db.sh). This utility interfaces directly with the containerized PostgreSQL database to create compressed, timestamped snapshots and manage rolling retention.

### 🛡️ Core Mechanics & Architecture
* **Direct Stream Compression**: Executes `pg_dump --clean --if-exists` inside the Docker container and streams the output directly through `gzip`, producing compact `.sql.gz` snapshot archives in `backups/` without staging uncompressed SQL files to disk.
* **Rolling 30-Day Retention**: Automated housekeeping policy that safely removes snapshot archives older than **30 days** (`-mtime +30`), ensuring predictable storage consumption.
* **Pre-Flight Health Checks**: Verifies container availability and database responsiveness via `pg_isready` before executing any backup or restore commands.
* **Zero Credential Hardcoding**: Credentials and database settings are injected dynamically from `.env` at runtime.

### 💻 CLI Manager Usage

| Command | Syntax | Description |
| :--- | :--- | :--- |
| **Status Monitor** | `./backup_db.sh status` | Inspects container health, database details, backup count, and latest snapshot sizes. |
| **Manual Backup** | `./backup_db.sh backup` | Generates a single timestamped `.sql.gz` snapshot immediately. |
| **Restore Database** | `./backup_db.sh restore <file.sql.gz>` | Restores the database with interactive confirmation safety guards. |
| **Retention Purge** | `./backup_db.sh cleanup` | Scans and deletes backup files older than 30 days. |
| **Automated Mode** | `./backup_db.sh auto-backup` | Runs a backup snapshot followed by 30-day retention cleanup and logging. |
| **Cron Helper** | `./backup_db.sh cron` | Displays exact Crontab syntax and installation instructions. |

### ⏰ Scheduled Weekly Backup (Crontab)
To execute automatic database backups every **Friday at 23:00 WIB**, add the following job to your crontab (`crontab -e`):

```crontab
# Weekly PostgreSQL Docker auto-backup every Friday at 23:00 WIB
0 23 * * 5 /path/to/foodprice-pipeline/backup_db.sh auto-backup >> /path/to/foodprice-pipeline/logs/backup.log 2>&1
```

### 🔄 Disaster Recovery / Restore Procedure
To restore your database from a previous snapshot:
```bash
./backup_db.sh restore backups/foodprice_backup_YYYYMMDD_HHMMSS.sql.gz
```
The script will prompt for confirmation before safely purging existing objects and restoring the entire schema and data state into the PostgreSQL Docker container.
