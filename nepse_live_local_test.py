"""
NEPSE Live Price — Local Test
------------------------------
Run this on YOUR machine (not in Claude's sandbox — it can't reach
nepalstock.com). Refreshes live trades every N seconds in the terminal.

Setup:
    pip install nepse_scraper --break-system-packages   # or in a venv without the flag

Notes:
- verify_ssl=False is required because NEPSE's server has a known
  incomplete SSL certificate chain. This is a documented workaround,
  not something to leave enabled on sites where it isn't necessary.
- Market is closed outside NEPSE trading hours/days — outside that
  window you'll get the last session's data, not "live" moving prices.
"""

import time
from datetime import datetime
from nepse_scraper import NepseScraper

REFRESH_SECONDS = 15   # don't go lower than this — be polite to their server
WATCHLIST = None       # e.g. ["NABIL", "NLIC", "CHCL"] — None = show all live trades


def fetch_and_print(client: NepseScraper):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    market_open = client.is_market_open()
    print(f"\n[{now}] Market open: {market_open}")

    if not market_open:
        print("Market is closed right now — showing last available data if any.")

    try:
        trades = client.get_live_trades()
    except Exception as e:
        print(f"Error fetching live trades: {e}")
        return

    if not trades:
        print("No live trade data returned.")
        return

    if WATCHLIST:
        trades = [t for t in trades if t.get("symbol") in WATCHLIST]

    print(f"{'Symbol':<10}{'LTP':>10}{'Change':>10}{'% Change':>10}{'Qty':>12}")
    print("-" * 52)
    for t in trades[:25]:  # cap what we print, not what we fetch
        symbol = t.get("symbol", "?")
        ltp = t.get("lastTradedPrice", t.get("ltp", "-"))
        change = t.get("pointChange", t.get("change", "-"))
        pct = t.get("percentageChange", t.get("perChange", "-"))
        qty = t.get("totalTradedQuantity", t.get("qty", "-"))
        print(f"{symbol:<10}{str(ltp):>10}{str(change):>10}{str(pct):>10}{str(qty):>12}")


def main():
    client = NepseScraper(verify_ssl=False)
    print("Starting NEPSE live price test. Ctrl+C to stop.")
    try:
        while True:
            fetch_and_print(client)
            time.sleep(REFRESH_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
