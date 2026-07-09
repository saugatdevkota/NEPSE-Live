"""
NEPSE Live Price Scraper -> Supabase
-------------------------------------
Fetches today's price data from NEPSE and upserts it into a Supabase table.
Designed to be run either:
  - locally, for testing (python scrape_nepse.py)
  - on a schedule via GitHub Actions (see .github/workflows/scrape.yml)

Required environment variables:
  SUPABASE_URL          e.g. https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  the SERVICE ROLE key (NOT the anon key) — keep secret,
                        never put this in frontend code or commit it to git.

Field names below are CONFIRMED against a real response (2026-07-09), e.g.:
{
  'symbol': 'ACLBSL', 'closePrice': 925.0, 'previousDayClosePrice': 925.0,
  'totalTradedQuantity': 954, 'totalTradedValue': 869125.2,
  'lastUpdatedPrice': 925.0, 'totalTrades': 30, 'marketCapitalization': 3396.08,
  'fiftyTwoWeekHigh': 1240.0, 'fiftyTwoWeekLow': 827.9,
  'lastUpdatedTime': '...', 'businessDate': '2026-07-08', ...
}

NEPSE does NOT provide point/percent change directly — we calculate both
from closePrice vs previousDayClosePrice.
"""

import os
import sys
import argparse
from datetime import datetime

from nepse_scraper import NepseScraper
from supabase import create_client


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables.")
    return create_client(url, key)


def build_row(t: dict) -> dict:
    symbol = t.get("symbol")
    ltp = t.get("lastUpdatedPrice") or t.get("closePrice")
    prev_close = t.get("previousDayClosePrice")

    point_change = None
    percent_change = None
    if ltp is not None and prev_close is not None:
        point_change = round(ltp - prev_close, 2)
        if prev_close != 0:
            percent_change = round((point_change / prev_close) * 100, 2)

    return {
        "symbol": symbol,
        "ltp": ltp,
        "point_change": point_change,
        "percent_change": percent_change,
        "total_qty": t.get("totalTradedQuantity"),
        "updated_at": datetime.utcnow().isoformat(),
    }


def run(debug: bool = False):
    client = NepseScraper(verify_ssl=False)

    is_open = client.is_market_open()
    print(f"[{datetime.now()}] Market open: {is_open}")

    trades = client.get_today_price()

    if debug:
        print("Raw sample record:")
        print(trades[0] if trades else "No data returned.")
        return

    if not trades:
        print("No price data returned — check connection. Skipping DB write.")
        return

    rows = [build_row(t) for t in trades if t.get("symbol")]

    if not rows:
        print("Parsed zero rows — NEPSE may have changed field names again. Run with --debug.")
        return

    supabase = get_supabase()

    supabase.table("nepse_live_prices").upsert(rows).execute()
    supabase.table("nepse_market_status").upsert({
        "id": 1,
        "is_open": is_open,
        "updated_at": datetime.utcnow().isoformat(),
    }).execute()

    print(f"Upserted {len(rows)} rows to Supabase.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true",
                         help="Print one raw record instead of writing to Supabase")
    args = parser.parse_args()
    run(debug=args.debug)