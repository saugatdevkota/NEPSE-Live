"""Meroshare CSV/PDF portfolio importer for NEPSE tracker.

Usage examples:
    python import_meroshare.py add-account --name "Family 1" --boid "1234567"
    python import_meroshare.py import --account-id 1 --portfolio-file portfolio.csv --transactions-file transactions.csv
    python import_meroshare.py import --account-id 1 --portfolio-file portfolio.pdf --transactions-file transactions.pdf
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _parse_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_date(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def normalize_transaction_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text.startswith("buy") or text.startswith("purchase"):
        return "buy"
    if text.startswith("sell") or text.startswith("sale"):
        return "sell"
    return text


def _canonicalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    renamed = df.rename(columns={col: _normalize_key(col) for col in df.columns})
    return renamed


def _extract_pdf_tables(path: str | Path) -> list[list[Any]]:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is required for PDF import. Install it with pip install pdfplumber.")

    rows: list[list[Any]] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for table in tables:
                for row in table:
                    if row:
                        rows.append([cell.strip() if isinstance(cell, str) else cell for cell in row])
    return rows


def _read_pdf_as_dataframe(path: str | Path) -> pd.DataFrame:
    rows = _extract_pdf_tables(path)
    if not rows:
        return pd.DataFrame()
    header = [str(cell).strip() for cell in rows[0]]
    data_rows = rows[1:]
    return pd.DataFrame(data_rows, columns=header)


def _read_file_dataframe(path: str | Path) -> pd.DataFrame:
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".pdf":
        return _read_pdf_as_dataframe(path)
    raise ValueError(f"Unsupported file type: {path}. Use CSV or PDF.")


def parse_portfolio_csv(df: pd.DataFrame | str | Path) -> list[dict[str, Any]]:
    if isinstance(df, (str, Path)):
        df = _read_file_dataframe(df)
    df = _canonicalize_dataframe(df)

    symbol_key = None
    qty_key = None
    ltp_key = None
    for candidate in ["symbol", "security", "company", "name"]:
        if candidate in df.columns:
            symbol_key = candidate
            break
    for candidate in ["quantity", "qty", "share_qty", "units"]:
        if candidate in df.columns:
            qty_key = candidate
            break
    for candidate in ["current_ltp", "ltp", "last_traded_price", "current_price", "price"]:
        if candidate in df.columns:
            ltp_key = candidate
            break

    if symbol_key is None or qty_key is None:
        raise ValueError("Portfolio file is missing symbol and quantity columns.")

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        symbol = str(row.get(symbol_key, "")).strip().upper()
        quantity = _parse_number(row.get(qty_key))
        ltp = _parse_number(row.get(ltp_key)) if ltp_key else None
        if not symbol or quantity is None:
            continue
        rows.append({"symbol": symbol, "quantity": float(quantity), "ltp": float(ltp) if ltp is not None else None})
    return rows


def parse_transactions_csv(df: pd.DataFrame | str | Path) -> list[dict[str, Any]]:
    if isinstance(df, (str, Path)):
        df = _read_file_dataframe(df)
    df = _canonicalize_dataframe(df)

    symbol_key = None
    type_key = None
    qty_key = None
    price_key = None
    date_key = None
    for candidate in ["symbol", "security", "company"]:
        if candidate in df.columns:
            symbol_key = candidate
            break
    for candidate in ["type", "transaction_type", "buy_sell", "action"]:
        if candidate in df.columns:
            type_key = candidate
            break
    for candidate in ["quantity", "qty", "units", "shares"]:
        if candidate in df.columns:
            qty_key = candidate
            break
    for candidate in ["rate", "price", "unit_price", "cost_price", "amount_per_share"]:
        if candidate in df.columns:
            price_key = candidate
            break
    for candidate in ["date", "transaction_date", "traded_on", "posted_on"]:
        if candidate in df.columns:
            date_key = candidate
            break

    if symbol_key is None or type_key is None or qty_key is None or price_key is None:
        raise ValueError("Transactions file is missing required columns.")

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        symbol = str(row.get(symbol_key, "")).strip().upper()
        qty = _parse_number(row.get(qty_key))
        price = _parse_number(row.get(price_key))
        txn_type = normalize_transaction_type(row.get(type_key))
        txn_date = _parse_date(row.get(date_key)) if date_key else ""
        if not symbol or qty is None or price is None or not txn_type:
            continue
        rows.append({
            "symbol": symbol,
            "type": txn_type,
            "quantity": float(qty),
            "price": float(price),
            "date": txn_date,
        })
    return rows


def compute_weighted_avg_cost(transactions: Iterable[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, dict[str, float]] = {}
    ordered = sorted(
        transactions,
        key=lambda item: _parse_date(item.get("date")) or "0000-00-00",
    )

    for item in ordered:
        symbol = str(item.get("symbol", "")).strip().upper()
        txn_type = normalize_transaction_type(item.get("type"))
        qty = float(item.get("quantity") or 0)
        price = float(item.get("price") or 0)
        if not symbol or qty <= 0:
            continue

        bucket = grouped.setdefault(symbol, {"remaining_quantity": 0.0, "cost_basis": 0.0})
        if txn_type == "buy":
            bucket["cost_basis"] += qty * price
            bucket["remaining_quantity"] += qty
        elif txn_type == "sell":
            current_quantity = bucket["remaining_quantity"]
            if current_quantity <= 0:
                continue
            sold_quantity = min(qty, current_quantity)
            avg_cost = bucket["cost_basis"] / current_quantity if current_quantity else 0.0
            bucket["cost_basis"] -= sold_quantity * avg_cost
            bucket["remaining_quantity"] = current_quantity - sold_quantity

    result: dict[str, dict[str, float | int]] = {}
    for symbol, values in grouped.items():
        remaining_qty = float(values.get("remaining_quantity") or 0)
        avg_cost = (float(values.get("cost_basis") or 0.0) / remaining_qty) if remaining_qty else 0.0
        result[symbol] = {
            "avg_cost": round(avg_cost, 4),
            "remaining_quantity": int(remaining_qty) if remaining_qty.is_integer() else remaining_qty,
        }
    return result


def get_supabase_client(url: str | None = None, key: str | None = None):
    url = url or os.environ.get("SUPABASE_URL")
    key = key or os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("Supabase URL and service role key are required. Set SUPABASE_URL and SUPABASE_SERVICE_KEY.")
    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("The optional supabase package is not installed. Install scraper/requirements-supabase.txt.") from exc
    return create_client(url, key)


def add_account(name: str, boid: str, url: str | None = None, key: str | None = None) -> dict[str, Any]:
    client = get_supabase_client(url, key)
    payload = {"name": name.strip(), "boid": boid.strip()}
    response = client.table("accounts").insert(payload).execute()
    if getattr(response, "data", None):
        return response.data[0]
    return payload


def remove_account(account_id: int | str, url: str | None = None, key: str | None = None) -> bool:
    client = get_supabase_client(url, key)
    response = client.table("accounts").delete().eq("id", account_id).execute()
    return bool(getattr(response, "data", None) or True)


def import_meroshare(account_id: int | str, portfolio_file: str | Path, transactions_file: str | Path, url: str | None = None, key: str | None = None) -> dict[str, Any]:
    client = get_supabase_client(url, key)
    portfolio_rows = parse_portfolio_csv(portfolio_file)
    transaction_rows = parse_transactions_csv(transactions_file)

    if not portfolio_rows and not transaction_rows:
        raise ValueError("No rows were extracted from the input files.")

    if not isinstance(account_id, int):
        account_id = int(account_id)

    lookup = client.table("accounts").select("id").eq("id", account_id).execute()
    if not getattr(lookup, "data", None):
        raise ValueError(f"Account {account_id} was not found in Supabase.")

    weighted_costs = compute_weighted_avg_cost(transaction_rows)
    holdings_payload: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()

    for row in portfolio_rows:
        symbol = str(row["symbol"]).upper()
        current_qty = float(row.get("quantity") or 0)
        avg_cost = weighted_costs.get(symbol, {}).get("avg_cost")
        if avg_cost is None and current_qty > 0:
            avg_cost = float(row.get("ltp") or 0)
        if current_qty <= 0:
            continue
        holdings_payload.append({
            "account_id": account_id,
            "symbol": symbol,
            "quantity": current_qty,
            "avg_cost": float(avg_cost or 0.0),
            "last_updated": datetime.utcnow().isoformat(),
        })
        seen_symbols.add(symbol)

    for symbol, info in weighted_costs.items():
        if symbol in seen_symbols:
            continue
        remaining_qty = float(info.get("remaining_quantity") or 0)
        if remaining_qty <= 0:
            continue
        holdings_payload.append({
            "account_id": account_id,
            "symbol": symbol,
            "quantity": remaining_qty,
            "avg_cost": float(info.get("avg_cost") or 0.0),
            "last_updated": datetime.utcnow().isoformat(),
        })

    if holdings_payload:
        client.table("holdings").upsert(holdings_payload, on_conflict="account_id,symbol").execute()

    if transaction_rows:
        transactions_payload = [{
            "account_id": account_id,
            "symbol": str(row["symbol"]).upper(),
            "type": row["type"],
            "quantity": float(row["quantity"]),
            "price": float(row["price"]),
            "date": row.get("date") or datetime.utcnow().strftime("%Y-%m-%d"),
        } for row in transaction_rows]
        client.table("transactions").upsert(
            transactions_payload,
            on_conflict="account_id,symbol,type,quantity,price,date",
        ).execute()

    return {
        "account_id": account_id,
        "portfolio_rows": len(portfolio_rows),
        "transaction_rows": len(transaction_rows),
        "holdings_upserted": len(holdings_payload),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import Meroshare portfolio and transaction data into Supabase.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add-account", help="Create a family portfolio account.")
    add_parser.add_argument("--name", required=True)
    add_parser.add_argument("--boid", required=True)
    add_parser.add_argument("--url", default=os.environ.get("SUPABASE_URL"))
    add_parser.add_argument("--key", default=os.environ.get("SUPABASE_SERVICE_KEY"))

    remove_parser = subparsers.add_parser("remove-account", help="Remove a portfolio account.")
    remove_parser.add_argument("--account-id", required=True, type=int)
    remove_parser.add_argument("--url", default=os.environ.get("SUPABASE_URL"))
    remove_parser.add_argument("--key", default=os.environ.get("SUPABASE_SERVICE_KEY"))

    import_parser = subparsers.add_parser("import", help="Import Meroshare CSV/PDF files by account.")
    import_parser.add_argument("--account-id", required=True, type=int)
    import_parser.add_argument("--portfolio-file", required=True)
    import_parser.add_argument("--transactions-file", required=True)
    import_parser.add_argument("--url", default=os.environ.get("SUPABASE_URL"))
    import_parser.add_argument("--key", default=os.environ.get("SUPABASE_SERVICE_KEY"))

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "add-account":
        result = add_account(args.name, args.boid, args.url, args.key)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "remove-account":
        result = remove_account(args.account_id, args.url, args.key)
        print({"deleted": result})
        return

    if args.command == "import":
        result = import_meroshare(args.account_id, args.portfolio_file, args.transactions_file, args.url, args.key)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
