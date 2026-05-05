"""
seed_dimensions.py - Master Data Seeding for Dimension Tables
==============================================================
Phase 0: Populates all dimension tables to maintain referential integrity.
This is a hybrid seeding script:
- Provinces, Market Types, and Commodities use hardcoded BI standards.
- Regencies and Markets are dynamically fetched via BI API to ensure 100% ID accuracy.

Seeding order (respects FK constraints):
  1. dim_provinces
  2. dim_regencies       (FK → dim_provinces)
  3. dim_market_types
  4. dim_markets          (FK → dim_regencies, dim_market_types)
  5. dim_commodity_groups
  6. dim_commodities      (FK → dim_commodity_groups)
"""

import os
import logging
from pathlib import Path
import requests
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
logger = logging.getLogger("seed_dimensions")

# ---------------------------------------------------------------------------
# Database credentials from .env
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5434)),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "dbname": os.getenv("POSTGRES_DB"),
}

BI_API_REGENCY = os.getenv("BI_API_REGENCY")
if not BI_API_REGENCY:
    raise ValueError("BI_API_REGENCY environment variable is not set")

BI_API_DETAIL_GRID = os.getenv("BI_API_DETAIL_GRID")
if not BI_API_DETAIL_GRID:
    raise ValueError("BI_API_DETAIL_GRID environment variable is not set")


# ===================================================================
# STATIC MASTER DATA
# ===================================================================

# Target Provinces (Java & Bali + Banten)
PROVINCES = [
    (11, "Banten"),
    (12, "Jawa Barat"),
    (13, "DKI Jakarta"),
    (14, "Jawa Tengah"),
    (15, "DI Yogyakarta"),
    (16, "Jawa Timur"),
    (17, "Bali"),
]

MARKET_TYPES = [
    (1, "Pasar Tradisional"),
    (2, "Pasar Modern"),
    (3, "Pedagang Besar"),
    (4, "Produsen"),
]

COMMODITY_GROUPS = [
    (1, "Beras"),
    (2, "Daging Ayam"),
    (3, "Daging Sapi"),
    (4, "Telur Ayam"),
    (5, "Bawang Merah"),
    (6, "Bawang Putih"),
    (7, "Cabai Merah"),
    (8, "Cabai Rawit"),
    (9, "Minyak Goreng"),
    (10, "Gula Pasir"),
]

COMMODITIES = [
    (1, 1, "Beras Kualitas Bawah I"),
    (2, 1, "Beras Kualitas Bawah II"),
    (3, 1, "Beras Kualitas Medium I"),
    (4, 1, "Beras Kualitas Medium II"),
    (5, 1, "Beras Kualitas Super I"),
    (6, 1, "Beras Kualitas Super II"),
    (7, 2, "Daging Ayam Ras Segar"),
    (8, 3, "Daging Sapi Kualitas 1"),
    (9, 3, "Daging Sapi Kualitas 2"),
    (10, 4, "Telur Ayam Ras Segar"),
    (11, 5, "Bawang Merah Ukuran Sedang"),
    (12, 6, "Bawang Putih Ukuran Sedang"),
    (13, 7, "Cabai Merah Besar"),
    (14, 7, "Cabai Merah Keriting"),
    (15, 8, "Cabai Rawit Hijau"),
    (16, 8, "Cabai Rawit Merah"),
    (17, 9, "Minyak Goreng Curah"),
    (18, 9, "Minyak Goreng Kemasan Bermerk 1"),
    (19, 9, "Minyak Goreng Kemasan Bermerk 2"),
    (20, 10, "Gula Pasir Kualitas Premium"),
    (21, 10, "Gula Pasir Lokal"),
]


# ===================================================================
# DYNAMIC DATA FETCHING
# ===================================================================


def clean_kemendagri_name(base_name: str, prov_id: int, regency_id: int = None) -> str:
    """
    Cleans the regency name from the API and correctly prepends 'Kota ' or 'Kabupaten '
    to conform to Kemendagri standards using geographic knowledge.
    """
    # 1. Handle hard collisions (where the API returns identical strings for Kota vs Kabupaten)
    EXCEPTIONS = {
        24: "Kota Serang",
        90: "Kabupaten Serang",
        27: "Kota Bandung",
        100: "Kabupaten Bandung",
        28: "Kota Cirebon",
        103: "Kabupaten Cirebon",
        29: "Kota Tasikmalaya",
        106: "Kabupaten Tasikmalaya",
        30: "Kota Bekasi",
        108: "Kabupaten Bekasi",
        31: "Kota Bogor",
        107: "Kabupaten Bogor",
        33: "Kota Sukabumi",
        110: "Kabupaten Sukabumi",
        35: "Kota Semarang",
        156: "Kabupaten Semarang",
        37: "Kota Tegal",
        148: "Kabupaten Tegal",
        143: "Kota Magelang",
        160: "Kabupaten Magelang",
        155: "Kota Pekalongan",
        164: "Kabupaten Pekalongan",
        43: "Kota Malang",
        113: "Kabupaten Malang",
        44: "Kota Kediri",
        128: "Kabupaten Kediri",
        47: "Kota Madiun",
        142: "Kabupaten Madiun",
        48: "Kota Probolinggo",
        137: "Kabupaten Probolinggo",
        116: "Kota Pasuruan",
        121: "Kabupaten Pasuruan",
        129: "Kota Mojokerto",
        134: "Kabupaten Mojokerto",
        132: "Kota Blitar",
        135: "Kabupaten Blitar",
    }

    if regency_id and regency_id in EXCEPTIONS:
        return EXCEPTIONS[regency_id]

    name = base_name.strip()

    # 2. Handle known BI abbreviations
    if name.startswith("Kab."):
        name = name.replace("Kab.", "Kabupaten", 1).strip()

    if name.startswith("Kota ") or name.startswith("Kabupaten "):
        return name

    # 3. Use trailing space heuristic (BI API often adds trailing space to Kabupatens)
    if base_name.endswith(" ") or base_name.endswith("  "):
        return f"Kabupaten {name}"

    # 4. Fallback logic based on geographic knowledge for the remaining unambiguous regions
    if prov_id == 13:
        return f"Kota {name}"  # All regions in DKI Jakarta are Kotas (Administrasi)

    KNOWN_KOTAS = {
        "Cilegon",
        "Tangerang",
        "Tangerang Selatan",
        "Cimahi",
        "Banjar",
        "Depok",
        "Surakarta",
        "Surakarta (Solo)",
        "Salatiga",
        "Yogyakarta",
        "Batu",
        "Surabaya",
        "Denpasar",
        "Singaraja",
    }

    if name in KNOWN_KOTAS:
        return f"Kota {name}"

    return f"Kabupaten {name}"


def fetch_regencies(target_prov_ids: list) -> list:
    """Fetch regencies dynamically using GetRegencyAll API."""
    regencies = []
    for prov_id in target_prov_ids:
        logger.info(f"Fetching regencies for ProvId {prov_id}...")
        try:
            res = requests.get(
                BI_API_REGENCY, params={"ref_prov_id": prov_id}, timeout=30
            ).json()
            for d in res.get("data", []):
                rid = d.get("regency_id")
                if rid and rid != 0:
                    raw_name = str(d.get("regency_name", ""))
                    clean_name = clean_kemendagri_name(raw_name, prov_id, rid)
                    regencies.append((rid, prov_id, clean_name))
        except Exception as e:
            logger.error(f"Failed to fetch regencies for ProvId {prov_id}: {e}")
    return regencies


def fetch_markets(target_prov_ids: list, existing_regencies: list) -> tuple:
    """Fetch market hierarchy dynamically using GetDetailGridData2 API."""
    markets_dict = {}
    missing_regencies_dict = {}

    # Create lookup dict from the existing regencies for fallback matching
    existing_regency_dict = {r[0]: r[2] for r in existing_regencies}
    existing_regency_ids = set(existing_regency_dict.keys())

    for prov_id in target_prov_ids:
        logger.info(f"Fetching markets for ProvId {prov_id}...")
        level2_map = {}

        for pt in [1, 2, 3]:
            try:
                params = {
                    "ProvId": prov_id,
                    "PriceTypeId": pt,
                    "ComId": 1,
                    "date": "20 April 2026",
                    "isPasokan": 1,
                }
                res = requests.get(BI_API_DETAIL_GRID, params=params, timeout=30).json()
                data = res.get("data", [])

                # First pass: direct mapping
                for item in data:
                    if item.get("level") == 2:
                        r_name = str(item.get("name", "")).strip()
                        r_id = item.get("id")
                        level2_map[r_name] = r_id

                        if (
                            r_id not in existing_regency_ids
                            and r_id not in missing_regencies_dict
                        ):
                            clean_r_name = clean_kemendagri_name(r_name, prov_id, r_id)
                            missing_regencies_dict[r_id] = (r_id, prov_id, clean_r_name)

                # Second pass: markets
                for item in data:
                    if item.get("level") == 3:
                        m_name = str(item.get("name", "")).strip()
                        m_cat = str(item.get("category", "")).strip()
                        m_id = item.get("id")

                        reg_id = level2_map.get(m_cat)

                        # Name-matching fallback if level 2 map didn't resolve
                        if not reg_id:
                            for r_id, r_name in existing_regency_dict.items():
                                if (
                                    m_cat.lower() in r_name.lower()
                                    or r_name.lower() in m_cat.lower()
                                ):
                                    reg_id = r_id
                                    break

                        if not reg_id:
                            continue

                        if "Modern" in m_name:
                            market_type_id = 2
                            final_market_id = 2000 + m_id
                        elif "Besar" in m_name:
                            market_type_id = 3
                            final_market_id = 3000 + m_id
                        else:
                            market_type_id = 1
                            final_market_id = m_id

                        markets_dict[final_market_id] = (
                            final_market_id,
                            reg_id,
                            market_type_id,
                            m_name,
                        )

            except Exception as e:
                logger.error(
                    f"Failed to fetch markets for ProvId {prov_id}, PriceTypeId {pt}: {e}"
                )

    return list(markets_dict.values()), list(missing_regencies_dict.values())


# ===================================================================
# SQL TEMPLATES
# ===================================================================

SQL_UPSERT_PROVINCES = """
    INSERT INTO dim_provinces (province_id, province_name)
    VALUES %s
    ON CONFLICT (province_id) DO UPDATE
        SET province_name = EXCLUDED.province_name
"""

SQL_UPSERT_REGENCIES = """
    INSERT INTO dim_regencies (regency_id, province_id, regency_name)
    VALUES %s
    ON CONFLICT (regency_id) DO UPDATE
        SET province_id  = EXCLUDED.province_id,
            regency_name = EXCLUDED.regency_name
"""

SQL_UPSERT_MARKET_TYPES = """
    INSERT INTO dim_market_types (market_type_id, market_type_name)
    VALUES %s
    ON CONFLICT (market_type_id) DO UPDATE
        SET market_type_name = EXCLUDED.market_type_name
"""

SQL_UPSERT_MARKETS = """
    INSERT INTO dim_markets (market_id, regency_id, market_type_id, market_name)
    VALUES %s
    ON CONFLICT (market_id) DO UPDATE
        SET regency_id     = EXCLUDED.regency_id,
            market_type_id = EXCLUDED.market_type_id,
            market_name    = EXCLUDED.market_name
"""

SQL_UPSERT_COMMODITY_GROUPS = """
    INSERT INTO dim_commodity_groups (group_id, group_name)
    VALUES %s
    ON CONFLICT (group_id) DO UPDATE
        SET group_name = EXCLUDED.group_name
"""

SQL_UPSERT_COMMODITIES = """
    INSERT INTO dim_commodities (commodity_id, group_id, commodity_name)
    VALUES %s
    ON CONFLICT (commodity_id) DO UPDATE
        SET group_id       = EXCLUDED.group_id,
            commodity_name = EXCLUDED.commodity_name
"""


# ===================================================================
# SEEDING FUNCTION
# ===================================================================
def seed_all() -> dict:
    """Seed all dimension tables, handling hybrid static + dynamic data."""
    conn = None
    cur = None
    summary = {}

    target_prov_ids = [p[0] for p in PROVINCES]

    # Dynamically fetch dimensions
    logger.info("Starting dynamic API fetches...")
    dynamic_regencies = fetch_regencies(target_prov_ids)

    dynamic_markets, missing_regencies = fetch_markets(
        target_prov_ids, dynamic_regencies
    )

    if missing_regencies:
        logger.info(
            f"Discovered {len(missing_regencies)} missing regencies from Market API. Appending to Regencies list."
        )
        dynamic_regencies.extend(missing_regencies)

    # Define seeding sequence
    seed_steps = [
        ("dim_provinces", SQL_UPSERT_PROVINCES, PROVINCES),
        ("dim_regencies", SQL_UPSERT_REGENCIES, dynamic_regencies),
        ("dim_market_types", SQL_UPSERT_MARKET_TYPES, MARKET_TYPES),
        ("dim_markets", SQL_UPSERT_MARKETS, dynamic_markets),
        ("dim_commodity_groups", SQL_UPSERT_COMMODITY_GROUPS, COMMODITY_GROUPS),
        ("dim_commodities", SQL_UPSERT_COMMODITIES, COMMODITIES),
    ]

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        logger.info(
            "Connected to PostgreSQL at %s:%s/%s",
            DB_CONFIG["host"],
            DB_CONFIG["port"],
            DB_CONFIG["dbname"],
        )

        for table_name, sql, data in seed_steps:
            if not data:
                logger.warning("No data found to seed for %s. Skipping.", table_name)
                continue

            logger.info("Seeding %-25s (%d records)...", table_name, len(data))
            execute_values(cur, sql, data)
            rows = cur.rowcount
            summary[table_name] = rows
            logger.info("  ✓ %s: %d row(s) affected.", table_name, rows)

        conn.commit()
        logger.info("All dimension tables seeded successfully.")

    except psycopg2.Error as e:
        logger.error("Database error during seeding: %s", e)
        if conn:
            conn.rollback()
            logger.info("Transaction rolled back.")
        raise

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return summary


# ===================================================================
# Verification Helper
# ===================================================================
def verify_counts() -> None:
    """Query row counts from all dimension tables for verification."""
    conn = None
    cur = None
    tables = [
        "dim_provinces",
        "dim_regencies",
        "dim_market_types",
        "dim_markets",
        "dim_commodity_groups",
        "dim_commodities",
    ]

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        print("\n" + "=" * 50)
        print("DIMENSION TABLE ROW COUNTS")
        print("=" * 50)
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table:<25s}: {count:>4d} rows")
        print("=" * 50)

    except psycopg2.Error as e:
        logger.error("Verification failed: %s", e)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# ===================================================================
# Entry Point
# ===================================================================
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Starting Dimension Table Seeding (Dynamic Hybrid Phase 0)")
    logger.info("=" * 60)

    summary = seed_all()

    print("\n" + "=" * 50)
    print("SEEDING SUMMARY")
    print("=" * 50)
    for table, rows in summary.items():
        print(f"  {table:<25s}: {rows:>4d} row(s)")
    print("=" * 50)

    verify_counts()

    logger.info("=" * 60)
    logger.info("Dimension seeding complete.")
    logger.info("=" * 60)
