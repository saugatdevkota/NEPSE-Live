"""Fetch public IPO listings and sync them to Supabase."""

from __future__ import annotations

import argparse
import html
import os
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_URLS = [
    "https://www.sharesansar.com/ipo",
    "https://merolagani.com/IPO",
    "https://merolagani.com/ipo",
]


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    text = html.unescape(value)
    text = re.sub(r"<.*?>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_date(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    text = _clean_text(raw_value)
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %b %Y",
        "%b %d, %Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    for fmt in ("%d-%b-%Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _parse_shares(value: str | None) -> int:
    if value is None:
        return 0
    text = _clean_text(value)
    if not text:
        return 0
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else 0


def normalize_share_type(raw_type: str | None) -> str:
    text = (_clean_text(raw_type) or "ordinary").lower()
    if "fpo" in text:
        return "fpo"
    if "local" in text:
        return "local"
    return "ordinary"


def extract_ipo_rows_from_html(html_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    table_matches = re.findall(r"<tr\b[^>]*>(.*?)</tr>", html_text, flags=re.I | re.S)
    for match in table_matches:
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", match, flags=re.I | re.S)
        if len(cells) < 5:
            continue
        texts = [_clean_text(item) for item in cells]
        if any("company" in text.lower() for text in texts):
            continue
        company_name = texts[0]
        symbol = texts[1].upper().replace(" ", "")
        open_date = _parse_date(texts[2])
        close_date = _parse_date(texts[3])
        shares_offered = _parse_shares(texts[4])
        share_type = normalize_share_type(texts[5] if len(texts) > 5 else "ordinary")

        if not company_name or not symbol:
            continue

        rows.append(
            {
                "company_name": company_name,
                "symbol": symbol,
                "open_date": open_date,
                "close_date": close_date,
                "shares_offered": shares_offered,
                "share_type": share_type,
            }
        )
    return rows


def fetch_ipo_rows(urls: list[str] | None = None) -> list[dict[str, Any]]:
    candidate_urls = urls or DEFAULT_URLS
    for url in candidate_urls:
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=20) as response:
                html_text = response.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        rows = extract_ipo_rows_from_html(html_text)
        if rows:
            return rows
    return []


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Supabase credentials are set, but the optional 'supabase' package is not installed. "
            "Install scraper/requirements-supabase.txt."
        ) from exc
    return create_client(url, key)


def _row_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("company_name"),
        row.get("symbol"),
        row.get("open_date"),
        row.get("close_date"),
        row.get("shares_offered"),
        row.get("share_type"),
    )


def sync_ipo_alerts(supabase, rows: list[dict[str, Any]]) -> int:
    if supabase is None or not rows:
        return 0

    response = supabase.table("ipo_alerts").select(
        "symbol,company_name,open_date,close_date,shares_offered,share_type"
    ).execute()
    existing = getattr(response, "data", []) or []
    existing_map = {str(item.get("symbol") or "").upper(): item for item in existing}

    to_upsert: list[dict[str, Any]] = []
    for row in rows:
        cleaned = {
            "company_name": str(row.get("company_name") or "").strip(),
            "symbol": str(row.get("symbol") or "").upper().strip(),
            "open_date": row.get("open_date"),
            "close_date": row.get("close_date"),
            "shares_offered": int(row.get("shares_offered") or 0),
            "share_type": normalize_share_type(row.get("share_type")),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if not cleaned["company_name"] or not cleaned["symbol"]:
            continue
        current = existing_map.get(cleaned["symbol"])
        if current and _row_signature(current) == _row_signature(cleaned):
            continue
        to_upsert.append(cleaned)

    if to_upsert:
        supabase.table("ipo_alerts").upsert(to_upsert, on_conflict="symbol").execute()

    return len(to_upsert)


def run(urls: list[str] | None = None) -> list[dict[str, Any]]:
    rows = fetch_ipo_rows(urls)
    supabase = get_supabase()
    if supabase:
        count = sync_ipo_alerts(supabase, rows)
        print(f"Synced {count} IPO alerts to Supabase.")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch IPO listings and sync them to Supabase.")
    parser.add_argument("--url", dest="urls", nargs="*", default=None, help="IPO source URL(s) to scrape")
    args = parser.parse_args()
    run(urls=args.urls)
