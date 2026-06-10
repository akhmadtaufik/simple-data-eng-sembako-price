import os
import csv
import time
import logging
import requests
import psycopg2
from psycopg2.extras import DictCursor

def load_env_file(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    os.environ[key] = val.strip('"').strip("'")

# Load environment
load_env_file("/home/nulltribe/MEGAsync/Project/upgrade-skills/foodprice-pipeline/.env")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("/home/nulltribe/MEGAsync/Project/upgrade-skills/foodprice-pipeline/logs/backfill_markets.log"),
        logging.StreamHandler()
    ]
)

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5434")
DB_NAME = os.getenv("POSTGRES_DB", "foodprice_dw")
DB_USER = os.getenv("POSTGRES_USER", "foodprice_admin")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "s3cur3_p@ssw0rd_2026")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "FoodPriceDataWarehouse/1.0 (contact@nulltribe.com)"}
TIMEOUT = 10

MISSING_MARKETS_CSV = "/home/nulltribe/MEGAsync/Project/upgrade-skills/foodprice-pipeline/data/missing_markets.csv"

def get_db_connection():
    try:
        return psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
        )
    except Exception as e:
        logging.error(f"Failed to connect to the database: {e}")
        raise

def geocode_location(query):
    params = {"q": query, "format": "json", "limit": 1}
    try:
        response = requests.get(NOMINATIM_URL, headers=HEADERS, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            return data[0].get("lat"), data[0].get("lon")
        return None, None
    except Exception as e:
        logging.error(f"Geocoding failed for '{query}': {e}")
        return None, None
    finally:
        # CRITICAL: 1.5 second sleep as per Nominatim policy
        time.sleep(1.5)

def fetch_and_update_markets(conn):
    logging.info("Starting backfill for dim_markets...")
    
    # Prepare CSV directory and check if file exists to write headers
    os.makedirs(os.path.dirname(MISSING_MARKETS_CSV), exist_ok=True)
    csv_file_exists = os.path.exists(MISSING_MARKETS_CSV)
    
    try:
        # Open CSV file in append mode
        with conn.cursor(cursor_factory=DictCursor) as cur, open(MISSING_MARKETS_CSV, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            if not csv_file_exists:
                writer.writerow(["market_id", "market_name", "regency_name"])

            # 1. JOIN Query for full context
            cur.execute("""
                SELECT 
                    m.market_id, 
                    m.market_name, 
                    r.regency_name, 
                    p.province_name 
                FROM dim_markets m
                JOIN dim_regencies r ON m.regency_id = r.regency_id
                JOIN dim_provinces p ON r.province_id = p.province_id
                WHERE m.latitude IS NULL OR m.longitude IS NULL;
            """)
            markets = cur.fetchall()

            if not markets:
                logging.info("No markets need updating.")
                return

            for mkt in markets:
                m_id = mkt['market_id']
                m_name = mkt['market_name']
                r_name = mkt['regency_name']
                p_name = mkt['province_name']
                
                # 2. Dynamic Search String
                query = f"{m_name}, {r_name}, {p_name}, Indonesia"
                logging.info(f"Geocoding Market: {query}")
                lat, lon = geocode_location(query)
                
                # 4. Update Logic for success
                if lat is not None and lon is not None:
                    cur.execute(
                        "UPDATE dim_markets SET latitude = %s, longitude = %s WHERE market_id = %s",
                        (lat, lon, m_id)
                    )
                    conn.commit()
                    logging.info(f"Updated Market '{m_name}' (ID: {m_id}) with Lat: {lat}, Lon: {lon}")
                # 5. CSV Fallback Mechanism
                else:
                    logging.warning(f"Coordinates not found for Market '{m_name}' (ID: {m_id}). Writing to CSV fallback.")
                    writer.writerow([m_id, m_name, r_name])
                    csvfile.flush() # Ensure it writes immediately

            logging.info("Completed backfill for dim_markets.")
    except Exception as e:
        logging.error(f"An error occurred while updating markets: {e}")
        conn.rollback()

def main():
    conn = None
    try:
        conn = get_db_connection()
        fetch_and_update_markets(conn)
    finally:
        if conn:
            conn.close()
            logging.info("Database connection closed.")

if __name__ == "__main__":
    main()
