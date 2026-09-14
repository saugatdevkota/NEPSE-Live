from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _sma(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    recent = values[-period:]
    if not recent:
        return 0.0
    return sum(recent) / len(recent)


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) < 2:
        return 50.0
    gains = []
    losses = []
    for current, previous in zip(values[1:], values[:-1]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    if len(gains) < period:
        return 50.0
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _volume_spike(volume_values: list[float], avg_window: int = 20) -> float:
    if not volume_values:
        return 0.0
    avg_vol = _sma(volume_values, avg_window)
    current_vol = volume_values[-1]
    if avg_vol == 0:
        return 0.0
    return ((current_vol - avg_vol) / avg_vol) * 100


def _daily_rows(history_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not history_rows:
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for row in history_rows:
        symbol = str(row.get("symbol") or "").upper()
        recorded_at = str(row.get("recorded_at") or "")
        date_key = recorded_at[:10] if recorded_at else "__single__"
        grouped.setdefault(symbol, {})
        key = f"{symbol}:{date_key}"
        grouped[symbol][key] = row
    merged: list[dict[str, Any]] = []
    for symbol, rows in grouped.items():
        for row in rows.values():
            row_copy = dict(row)
            row_copy["symbol"] = symbol
            merged.append(row_copy)
    return sorted(merged, key=lambda item: str(item.get("recorded_at") or "0000-00-00T00:00:00Z"))


def compute_symbol_signal(history_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not history_rows:
        return {
            "symbol": "",
            "label": "Neutral",
            "sma5": 0.0,
            "sma20": 0.0,
            "rsi14": 50.0,
            "volume_spike_pct": 0.0,
            "signal_score": 0.0,
            "note": "No history available",
        }

    daily_rows = _daily_rows(history_rows)
    if not daily_rows:
        daily_rows = history_rows

    symbol = str(daily_rows[0].get("symbol") or "").upper()
    prices = [_safe_float(row.get("ltp"), 0.0) for row in daily_rows]
    volumes = [_safe_float(row.get("total_qty"), 0.0) for row in daily_rows]

    sma5 = _sma(prices, 5)
    sma20 = _sma(prices, 20)
    rsi14 = _rsi(prices, 14)
    volume_spike = _volume_spike(volumes, 20)

    buy_lean = sma5 > sma20 and rsi14 < 80
    sell_lean = sma5 < sma20 and (rsi14 > 70 or rsi14 < 30)

    if buy_lean and volume_spike >= -25:
        label = "Potential Buy"
        note = f"SMA5={sma5:.2f} > SMA20={sma20:.2f}; RSI14={rsi14:.1f} < 80; volume spike {volume_spike:.1f}%"
        score = 1
    elif sell_lean and volume_spike <= 25:
        label = "Potential Sell"
        note = f"SMA5={sma5:.2f} < SMA20={sma20:.2f}; RSI14={rsi14:.1f} in bearish zone; volume spike {volume_spike:.1f}%"
        score = -1
    else:
        label = "Neutral"
        note = f"SMA5={sma5:.2f}, SMA20={sma20:.2f}; RSI14={rsi14:.1f}; volume spike {volume_spike:.1f}%"
        score = 0

    return {
        "symbol": symbol,
        "label": label,
        "sma5": round(sma5, 2),
        "sma20": round(sma20, 2),
        "rsi14": round(rsi14, 2),
        "volume_spike_pct": round(volume_spike, 2),
        "signal_score": score,
        "note": note,
    }
