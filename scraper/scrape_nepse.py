"""
NEPSE Live Price Scraper -> Supabase
-------------------------------------
Fetches today's price data from NEPSE, upserts current snapshot into
nepse_live_prices, and appends a row per symbol into nepse_price_history
(for charting / historical lookback).

Required environment variables:
  SUPABASE_URL          e.g. https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  the SERVICE ROLE key (NOT the anon key)

NEPSE does NOT provide point/percent change directly — we calculate both
from closePrice vs previousDayClosePrice.
"""

import os
import sys
import argparse
from datetime import datetime, timezone

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
    ltp = t.get("lastUpdatedPrice")
    if ltp is None:
        ltp = t.get("closePrice")
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

    base_rows = [build_row(t) for t in trades if t.get("symbol")]

    if not base_rows:
        print("Parsed zero rows — NEPSE may have changed field names again. Run with --debug.")
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    # Snapshot rows: one per symbol, overwritten each run (for "current price")
    snapshot_rows = [{**r, "updated_at": now_iso} for r in base_rows]

    # Only record chart history while the market is open. Runs around the
    # session boundaries would otherwise append repeated closed-market data.
    history_rows = [
        {
            "symbol": r["symbol"],
            "ltp": r["ltp"],
            "point_change": r["point_change"],
            "percent_change": r["percent_change"],
            "recorded_at": now_iso,
        }
        for r in base_rows
    ] if is_open else []

    supabase = get_supabase()

    supabase.table("nepse_live_prices").upsert(snapshot_rows).execute()
    supabase.table("nepse_market_status").upsert({
        "id": 1,
        "is_open": is_open,
        "updated_at": now_iso,
    }).execute()

    # Insert in chunks — Supabase/PostgREST can reject overly large single inserts
    CHUNK = 200
    for i in range(0, len(history_rows), CHUNK):
        supabase.table("nepse_price_history").insert(history_rows[i:i + CHUNK]).execute()

    print(f"Upserted {len(snapshot_rows)} snapshot rows, appended {len(history_rows)} history rows.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true",
                         help="Print one raw record instead of writing to Supabase")
    args = parser.parse_args()
    run(debug=args.debug)
