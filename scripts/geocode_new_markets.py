"""
geocode_new_markets.py - Automated Geocoding for New Markets
"""
import os
import time
import logging
import requests
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv
from pathlib import Path

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
logger = logging.getLogger("geocode_new_markets")

# ---------------------------------------------------------------------------
# Database and API Config
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5434)),
    "user": os.getenv("POSTGRES_USER", "foodprice_admin"),
    "password": os.getenv("POSTGRES_PASSWORD", "s3cur3_p@ssw0rd_2026"),
    "dbname": os.getenv("POSTGRES_DB", "foodprice_dw"),
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "FoodPriceDataWarehouse/1.0 (contact@nulltribe.com)"}
TIMEOUT = 10

def geocode_location(query: str):
    """Call OpenStreetMap Nominatim API to geocode a location."""
    params = {"q": query, "format": "json", "limit": 1}
    try:
        response = requests.get(NOMINATIM_URL, headers=HEADERS, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            return data[0].get("lat"), data[0].get("lon")
        return None, None
    except Exception as e:
        logger.error("Geocoding failed for '%s': %s", query, e)
        return None, None
    finally:
        time.sleep(1.5)

def main():
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        with conn.cursor(cursor_factory=DictCursor) as cur:
            logger.info("Querying for markets with missing coordinates...")
            cur.execute("""
                SELECT 
                    m.market_id, 
                    m.market_name, 
                    r.regency_name, 
                    r.latitude as regency_lat,
                    r.longitude as regency_lon,
                    p.province_name 
                FROM dim_markets m
                JOIN dim_regencies r ON m.regency_id = r.regency_id
                JOIN dim_provinces p ON r.province_id = p.province_id
                WHERE m.latitude IS NULL OR m.longitude IS NULL;
            """)
            markets = cur.fetchall()

            if not markets:
                logger.info("No markets need geocoding.")
                return

            api_geocoded = 0
            regency_fallback = 0
            failed = 0

            for mkt in markets:
                m_id = mkt['market_id']
                m_name = mkt['market_name']
                r_name = mkt['regency_name']
                p_name = mkt['province_name']
                reg_lat = mkt['regency_lat']
                reg_lon = mkt['regency_lon']
                
                query = f"{m_name}, {r_name}, {p_name}, Indonesia"
                logger.info("Geocoding Market: %s", query)
                lat, lon = geocode_location(query)
                
                if lat is not None and lon is not None:
                    # Success
                    cur.execute(
                        "UPDATE dim_markets SET latitude = %s, longitude = %s WHERE market_id = %s",
                        (lat, lon, m_id)
                    )
                    api_geocoded += 1
                    logger.info("Updated Market '%s' (ID: %s) via API (Lat: %s, Lon: %s)", m_name, m_id, lat, lon)
                else:
                    # Fallback to regency coordinates
                    if reg_lat is not None and reg_lon is not None:
                        cur.execute(
                            "UPDATE dim_markets SET latitude = %s, longitude = %s WHERE market_id = %s",
                            (reg_lat, reg_lon, m_id)
                        )
                        regency_fallback += 1
                        logger.warning("Market '%s' not found via API. Used Regency fallback (Lat: %s, Lon: %s)", m_name, reg_lat, reg_lon)
                    else:
                        failed += 1
                        logger.error("Market '%s' not found via API, and Regency has no coordinates.", m_name)

            conn.commit()
            logger.info("Geocoding Summary: %d API geocoded, %d Regency fallback, %d Failed.", api_geocoded, regency_fallback, failed)

    except Exception as e:
        logger.error("An error occurred: %s", e)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
