from scraper.technical_signal import compute_symbol_signal


def build_history(prices, volumes):
    return [
        {"symbol": "NABIL", "ltp": float(price), "total_qty": int(volume), "recorded_at": f"2024-01-{idx:02d}T00:00:00Z"}
        for idx, (price, volume) in enumerate(zip(prices, volumes), start=1)
    ]


def test_buy_signal():
    prices = [100, 101, 102, 101, 103, 104, 103, 105, 106, 105, 107, 108, 107, 109, 110, 109, 111, 112, 111, 113, 114, 113, 115, 116, 115, 117, 118, 117, 119, 120]
    volumes = [1000] * 30
    signal = compute_symbol_signal(build_history(prices, volumes))
    assert signal["label"] == "Potential Buy"
    assert signal["sma5"] > signal["sma20"]
    assert signal["rsi14"] < 80


def test_sell_signal():
    prices = [130, 128, 127, 125, 124, 122, 120, 118, 116, 115, 113, 111, 109, 108, 106, 104, 102, 100, 98, 96, 95, 93, 91, 89, 87, 85, 83, 81, 80, 78]
    volumes = [1000] * 30
    signal = compute_symbol_signal(build_history(prices, volumes))
    assert signal["label"] == "Potential Sell"
    assert signal["sma5"] < signal["sma20"]


def test_neutral_signal_when_mixed():
    prices = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 102, 101, 100, 101, 100, 101, 100, 101, 100, 101]
    volumes = [1000] * 30
    signal = compute_symbol_signal(build_history(prices, volumes))
    assert signal["label"] == "Neutral"
