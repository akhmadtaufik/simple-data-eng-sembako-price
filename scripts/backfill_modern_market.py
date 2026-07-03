import time
import random
import logging
from datetime import date, timedelta
import requests
from extract import fetch_food_prices
from transform import transform_data
from load import load_data

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
]

def get_fridays_until_today() -> list[date]:
    start_date = date(2025, 1, 3) # First Friday of 2026
    end_date = date(2025, 12, 26)
    fridays = []
    current = start_date
    while current <= end_date:
        fridays.append(current)
        current += timedelta(days=7)
    return fridays

def run_targeted_ytd_backfill():
    fridays = get_fridays_until_today()
    session = requests.Session()
    
    provinces = [11, 12, 13, 14, 15, 16, 17]
    price_types = [2, 3] # STRICTLY Modern (2) and Pedagang Besar (3) ONLY
    commodities = range(1, 22)
    
    for dt in fridays:
        date_str = dt.strftime("%Y-%m-%d")
        
        for prov_id in provinces:
            for pt_id in price_types:
                for com_id in commodities:
                    session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
                    params = {
                        "ProvId": prov_id,
                        "PriceTypeId": pt_id,
                        "ComId": com_id,
                        "date": date_str,
                        "isPasokan": 1,
                    }
                    
                    try:
                        raw_data = fetch_food_prices(params=params, session=session)
                        if raw_data:
                            df_clean = transform_data(raw_data, commodity_id=com_id)
                            if not df_clean.empty:
                                rows = load_data(df_clean)
                                logging.info(f"Loaded {rows} rows | {date_str} | Prov: {prov_id} | PT: {pt_id} | Com: {com_id}")
                    except requests.exceptions.RequestException as e:
                        if getattr(e, "response", None) and e.response.status_code in (429, 403):
                            logging.critical("Blocked! HTTP 429/403. Sleeping 120s...")
                            time.sleep(120)
                        else:
                            logging.error(f"Request Error on {date_str} Prov {prov_id} Com {com_id}: {e}")
                    except Exception as e:
                        logging.error(f"Unexpected Error on {date_str}: {e}")
                    finally:
                        time.sleep(random.uniform(2.5, 6.0))

if __name__ == "__main__":
    run_targeted_ytd_backfill()
