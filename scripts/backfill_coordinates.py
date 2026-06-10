import os
import time
import logging
import requests
import psycopg2
from psycopg2.extras import DictCursor

# Manually load .env to avoid external dependencies like python-dotenv
def load_env_file(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    os.environ[key] = val.strip('"').strip("'")

load_env_file("/home/nulltribe/MEGAsync/Project/upgrade-skills/foodprice-pipeline/.env")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("/home/nulltribe/MEGAsync/Project/upgrade-skills/foodprice-pipeline/logs/backfill_coordinates.log"),
        logging.StreamHandler()
    ]
)

# Database connection parameters
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5434")
DB_NAME = os.getenv("POSTGRES_DB", "foodprice_dw")
DB_USER = os.getenv("POSTGRES_USER", "foodprice_admin")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "s3cur3_p@ssw0rd_2026")

# Nominatim API Configuration
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    # CRITICAL: Custom User-Agent to comply with Nominatim Acceptable Use Policy
    "User-Agent": "FoodPriceDataWarehouse/1.0 (contact@nulltribe.com)"
}

TIMEOUT = 10

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to the database: {e}")
        raise

def geocode_location(query):
    params = {
        "q": query,
        "format": "json",
        "limit": 1
    }
    try:
        response = requests.get(NOMINATIM_URL, headers=HEADERS, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            return data[0].get("lat"), data[0].get("lon")
        return None, None
    except requests.exceptions.RequestException as e:
        logging.error(f"API request failed for query '{query}': {e}")
        return None, None
    finally:
        # CRITICAL: Sleep for 1.5 seconds between every API call as per policy
        time.sleep(1.5)

def fetch_and_update_provinces(conn):
    logging.info("Starting backfill for dim_provinces...")
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT province_id, province_name FROM dim_provinces WHERE latitude IS NULL OR longitude IS NULL;")
            provinces = cur.fetchall()
            
            if not provinces:
                logging.info("No provinces need updating.")
                return

            for prov in provinces:
                prov_id = prov['province_id']
                prov_name = prov['province_name']
                query = f"{prov_name}, Indonesia"
                
                logging.info(f"Geocoding Province: {query}")
                lat, lon = geocode_location(query)
                
                if lat is not None and lon is not None:
                    cur.execute(
                        "UPDATE dim_provinces SET latitude = %s, longitude = %s WHERE province_id = %s",
                        (lat, lon, prov_id)
                    )
                    conn.commit()
                    logging.info(f"Updated province {prov_name} (ID: {prov_id}) with Lat: {lat}, Lon: {lon}")
                else:
                    logging.warning(f"Coordinates not found in API for province {prov_name} (ID: {prov_id})")

            logging.info("Completed backfill for dim_provinces.")
    except Exception as e:
        logging.error(f"An error occurred while updating provinces: {e}")
        conn.rollback()

def fetch_and_update_regencies(conn):
    logging.info("Starting backfill for dim_regencies...")
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT r.regency_id, r.regency_name, p.province_name 
                FROM dim_regencies r
                JOIN dim_provinces p ON r.province_id = p.province_id
                WHERE r.latitude IS NULL OR r.longitude IS NULL;
            """)
            regencies = cur.fetchall()

            if not regencies:
                logging.info("No regencies need updating.")
                return

            for reg in regencies:
                reg_id = reg['regency_id']
                reg_name = reg['regency_name']
                prov_name = reg['province_name']
                
                query = f"{reg_name}, {prov_name}, Indonesia"
                logging.info(f"Geocoding Regency: {query}")
                lat, lon = geocode_location(query)
                
                if lat is not None and lon is not None:
                    cur.execute(
                        "UPDATE dim_regencies SET latitude = %s, longitude = %s WHERE regency_id = %s",
                        (lat, lon, reg_id)
                    )
                    conn.commit()
                    logging.info(f"Updated Regency {reg_name} (ID: {reg_id}) with Lat: {lat}, Lon: {lon}")
                else:
                    logging.warning(f"Coordinates not found in API for Regency {reg_name} (ID: {reg_id})")

            logging.info("Completed backfill for dim_regencies.")
    except Exception as e:
        logging.error(f"An error occurred while updating regencies: {e}")
        conn.rollback()

def main():
    conn = None
    try:
        conn = get_db_connection()
        fetch_and_update_provinces(conn)
        fetch_and_update_regencies(conn)
    finally:
        if conn:
            conn.close()
            logging.info("Database connection closed.")

if __name__ == "__main__":
    main()
