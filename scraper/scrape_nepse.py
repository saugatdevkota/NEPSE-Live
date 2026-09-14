"""
NEPSE Live Price Scraper
------------------------
Fetches today's prices and writes a static JSON file for the frontend.
Supabase syncing is optional when both environment variables are configured:
  SUPABASE_URL          e.g. https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  the SERVICE ROLE key (NOT the anon key)

NEPSE does NOT provide point/percent change directly — we calculate both
from closePrice vs previousDayClosePrice.
"""

import os
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nepse_scraper import NepseScraper

try:
    from scraper.technical_signal import compute_symbol_signal
except ImportError:  # pragma: no cover
    from technical_signal import compute_symbol_signal


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError as error:
        raise RuntimeError(
            "Supabase credentials are set, but the optional 'supabase' package is not installed. "
            "Install scraper/requirements-supabase.txt."
        ) from error
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


def write_static_data(output_path: str, is_open: bool, rows: list[dict], updated_at: str):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "is_open": bool(is_open),
        "updated_at": updated_at,
        "prices": rows,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} prices to {path}.")


def refresh_symbol_signals(supabase, now_iso: str):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    response = supabase.table("nepse_price_history").select("symbol,ltp,total_qty,recorded_at").gte("recorded_at", cutoff).order("symbol").order("recorded_at").execute()
    rows = getattr(response, "data", []) or []
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append({
            "symbol": symbol,
            "ltp": row.get("ltp"),
            "total_qty": row.get("total_qty"),
            "recorded_at": row.get("recorded_at"),
        })

    signal_rows = []
    for symbol, symbol_rows in grouped.items():
        signal = compute_symbol_signal(symbol_rows)
        signal_rows.append({
            "symbol": symbol,
            "label": signal["label"],
            "sma5": signal["sma5"],
            "sma20": signal["sma20"],
            "rsi14": signal["rsi14"],
            "volume_spike_pct": signal["volume_spike_pct"],
            "note": signal["note"],
            "updated_at": now_iso,
        })

    if signal_rows:
        supabase.table("symbol_signal").upsert(signal_rows, on_conflict="symbol").execute()

    return len(signal_rows)


def sync_supabase(supabase, is_open: bool, snapshot_rows: list[dict], now_iso: str):
    history_rows = [
        {
            "symbol": row["symbol"],
            "ltp": row["ltp"],
            "point_change": row["point_change"],
            "percent_change": row["percent_change"],
            "total_qty": row.get("total_qty"),
            "recorded_at": now_iso,
        }
        for row in snapshot_rows
    ] if is_open else []

    supabase.table("nepse_live_prices").upsert(snapshot_rows).execute()
    supabase.table("nepse_market_status").upsert({
        "id": 1,
        "is_open": is_open,
        "updated_at": now_iso,
    }).execute()

    chunk_size = 200
    for i in range(0, len(history_rows), chunk_size):
        supabase.table("nepse_price_history").insert(
            history_rows[i:i + chunk_size]
        ).execute()

    signal_count = refresh_symbol_signals(supabase, now_iso)
    print(
        f"Synced {len(snapshot_rows)} snapshots, {len(history_rows)} history rows, and {signal_count} technical signals to Supabase."
    )


def run(debug: bool = False, output_path: str = "frontend/data.json"):
    client = NepseScraper(verify_ssl=False)

    is_open = client.is_market_open()
    print(f"[{datetime.now()}] Market open: {is_open}")

    trades = client.get_today_price()

    if debug:
        print("Raw sample record:")
        print(trades[0] if trades else "No data returned.")
        return

    if not trades:
        print("No price data returned — check connection. Keeping the existing data file.")
        return

    base_rows = [build_row(t) for t in trades if t.get("symbol")]

    if not base_rows:
        print("Parsed zero rows — NEPSE may have changed field names again. Run with --debug.")
        return

    now_iso = datetime.now(timezone.utc).isoformat()

    snapshot_rows = [{**r, "updated_at": now_iso} for r in base_rows]
    write_static_data(output_path, is_open, snapshot_rows, now_iso)

    # Database syncing is secondary and opt-in. A paused or unconfigured
    # Supabase project never prevents the static frontend data from updating.
    supabase = get_supabase()
    if supabase:
        sync_supabase(supabase, is_open, snapshot_rows, now_iso)
    else:
        print("Supabase not configured; static JSON mode only.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true",
                         help="Print one raw record without writing data")
    parser.add_argument("--output", default="frontend/data.json",
                        help="Static frontend JSON output path")
    args = parser.parse_args()
    run(debug=args.debug, output_path=args.output)
