"""
NEPSE Live Price Scraper -> Supabase
-------------------------------------
Fetches live trades from NEPSE and upserts them into a Supabase table.
Designed to be run either:
  - locally, for testing (python scrape_nepse.py)
  - on a schedule via GitHub Actions (see .github/workflows/scrape.yml)

Required environment variables:
  SUPABASE_URL          e.g. https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  the SERVICE ROLE key (NOT the anon key) — keep secret,
                        never put this in frontend code or commit it to git.

--- IMPORTANT CALIBRATION NOTE ---
The exact JSON field names NEPSE's API returns for each trade record are
not yet confirmed. FIELD_MAP below has best-guess candidates for each value
and tries them in order. Run with --debug once to print a raw record, check
the real keys, then trim FIELD_MAP to just the correct one for reliability.
"""

import os
import sys
import argparse
from datetime import datetime

from nepse_scraper import NepseScraper
from supabase import create_client

# Candidate key names to try, in order, for each field we care about.
# Once you confirm the real key (via --debug), reduce each list to one item.
FIELD_MAP = {
    "symbol": ["symbol", "securitySymbol", "Symbol"],
    "ltp": ["lastTradedPrice", "ltp", "LTP", "closePrice"],
    "point_change": ["pointChange", "change", "netChange"],
    "percent_change": ["percentageChange", "perChange", "percentChange"],
    "total_qty": ["totalTradedQuantity", "qty", "totalTradeQuantity", "sharesTraded"],
}


def extract_field(record: dict, field: str):
    for key in FIELD_MAP[field]:
        if key in record:
            return record[key]
    return None


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables.")
    return create_client(url, key)


def run(debug: bool = False):
    client = NepseScraper(verify_ssl=False)

    is_open = client.is_market_open()
    print(f"[{datetime.now()}] Market open: {is_open}")

    trades = client.get_live_trades()

    if debug:
        print("Raw sample record:")
        print(trades[0] if trades else "No trades returned.")
        return

    if not trades:
        print("No live trade data returned — market likely closed. Skipping DB write.")
        return

    rows = []
    for t in trades:
        symbol = extract_field(t, "symbol")
        if not symbol:
            continue
        rows.append({
            "symbol": symbol,
            "ltp": extract_field(t, "ltp"),
            "point_change": extract_field(t, "point_change"),
            "percent_change": extract_field(t, "percent_change"),
            "total_qty": extract_field(t, "total_qty"),
            "updated_at": datetime.utcnow().isoformat(),
        })

    if not rows:
        print("Parsed zero rows — field names likely don't match. Run with --debug.")
        return

    supabase = get_supabase()

    # Upsert: insert new rows, overwrite existing ones by symbol (primary key)
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
