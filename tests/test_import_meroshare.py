import pandas as pd

from import_meroshare import (
    compute_weighted_avg_cost,
    normalize_transaction_type,
    parse_portfolio_csv,
    parse_transactions_csv,
)


def test_normalize_transaction_type():
    assert normalize_transaction_type("Buy") == "buy"
    assert normalize_transaction_type("SELL") == "sell"
    assert normalize_transaction_type("purchase") == "buy"


def test_parse_portfolio_csv():
    df = pd.DataFrame([
        {"Symbol": "NABIL", "Quantity": 25, "Current LTP": 450.5},
        {"Symbol": "NICA", "Quantity": 10, "Current LTP": 245.0},
    ])
    rows = parse_portfolio_csv(df)
    assert rows == [
        {"symbol": "NABIL", "quantity": 25, "ltp": 450.5},
        {"symbol": "NICA", "quantity": 10, "ltp": 245.0},
    ]


def test_parse_transactions_csv():
    df = pd.DataFrame([
        {"Symbol": "NABIL", "Type": "Buy", "Quantity": 10, "Rate": 420.0, "Date": "2024-01-05"},
        {"Symbol": "NABIL", "Type": "Buy", "Quantity": 15, "Rate": 430.5, "Date": "2024-02-01"},
        {"Symbol": "NABIL", "Type": "Sell", "Quantity": 5, "Rate": 440.0, "Date": "2024-03-01"},
    ])
    rows = parse_transactions_csv(df)
    assert rows == [
        {"symbol": "NABIL", "type": "buy", "quantity": 10, "price": 420.0, "date": "2024-01-05"},
        {"symbol": "NABIL", "type": "buy", "quantity": 15, "price": 430.5, "date": "2024-02-01"},
        {"symbol": "NABIL", "type": "sell", "quantity": 5, "price": 440.0, "date": "2024-03-01"},
    ]


def test_compute_weighted_avg_cost():
    transactions = [
        {"symbol": "NABIL", "type": "buy", "quantity": 10, "price": 420.0, "date": "2024-01-05"},
        {"symbol": "NABIL", "type": "buy", "quantity": 15, "price": 430.5, "date": "2024-02-01"},
        {"symbol": "NABIL", "type": "sell", "quantity": 5, "price": 440.0, "date": "2024-03-01"},
    ]
    result = compute_weighted_avg_cost(transactions)
    assert result["NABIL"]["avg_cost"] == 426.3
    assert result["NABIL"]["remaining_quantity"] == 20
