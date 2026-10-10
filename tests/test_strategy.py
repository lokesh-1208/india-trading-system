"""Checks position sizing, stop/target and the signal rules."""

import numpy as np
import pandas as pd

import config
from trading import strategy


def test_stop_and_target():
    stop, target = strategy.stop_and_target(100.0, 4.0)
    assert stop == 94.0       # 100 - 1.5 x 4
    assert target == 112.0    # 100 + 2 x 6


def test_position_size_limited_by_risk():
    # Risk 1% of 1,00,000 = 1,000. Risk per share 40. So 25 shares (12,500).
    assert strategy.position_size(100_000, 500.0, 460.0) == 25


def test_position_size_limited_by_25_percent_cap():
    # Risk allows 100 shares, but 25% of capital is 25,000 = 25 shares.
    assert strategy.position_size(100_000, 1000.0, 990.0) == 25


def test_position_size_limited_by_cash():
    assert strategy.position_size(100_000, 500.0, 480.0, cash=5_000) == 9


def test_position_size_is_zero_when_stop_is_not_below_entry():
    assert strategy.position_size(100_000, 500.0, 500.0) == 0
    assert strategy.position_size(100_000, 500.0, 510.0) == 0


def _uptrend_stock(volume):
    """A stock that rises 2% then falls 1%, again and again, ending on an up day."""
    days = pd.bdate_range("2024-01-01", periods=201)
    closes = [100.0]
    for day in range(200):
        closes.append(closes[-1] * (1.02 if day % 2 == 1 else 0.99))
    close = pd.Series(closes, index=days)
    volumes = pd.Series(float(volume), index=days)
    volumes.iloc[-1] = volume * 2          # a volume surge on the last day
    return pd.DataFrame({
        "Open": close.shift(1).fillna(100.0),
        "High": close * 1.005,
        "Low": close * 0.985,
        "Close": close,
        "Volume": volumes,
    })


def _flat_nifty(index):
    return pd.Series(20_000.0, index=index)


def test_signal_is_true_for_a_liquid_uptrend_with_a_volume_surge():
    stock = _uptrend_stock(volume=5_000_000)
    table = strategy.add_indicators(stock, _flat_nifty(stock.index))
    last = table.iloc[-1]
    assert config.RSI_MIN <= last["rsi"] <= config.RSI_MAX
    assert last["volume_ratio"] > 1
    assert last["relative_strength"] > 0
    assert bool(last["signal"])


def test_signal_is_false_when_the_stock_is_not_liquid():
    stock = _uptrend_stock(volume=1_000)
    table = strategy.add_indicators(stock, _flat_nifty(stock.index))
    assert table.iloc[-1]["turnover_crore"] < config.MIN_TURNOVER_CRORE
    assert not bool(table.iloc[-1]["signal"])


def test_signal_is_false_without_a_volume_surge():
    stock = _uptrend_stock(volume=5_000_000)
    stock.iloc[-1, stock.columns.get_loc("Volume")] = 5_000_000
    table = strategy.add_indicators(stock, _flat_nifty(stock.index))
    assert not bool(table.iloc[-1]["signal"])


def test_no_signal_in_the_first_days_of_a_new_listing():
    stock = _uptrend_stock(volume=5_000_000)
    table = strategy.add_indicators(stock, _flat_nifty(stock.index))
    assert not table["signal"].iloc[: config.MIN_HISTORY_DAYS - 1].any()


def test_market_is_healthy_only_above_its_ema():
    days = pd.bdate_range("2024-01-01", periods=120)
    rising = pd.DataFrame({"Close": np.linspace(20_000, 22_000, 120)}, index=days)
    falling = pd.DataFrame({"Close": np.linspace(22_000, 20_000, 120)}, index=days)
    assert bool(strategy.market_is_healthy(rising).iloc[-1])
    assert not bool(strategy.market_is_healthy(falling).iloc[-1])


def test_no_signal_on_days_the_stock_was_not_in_the_index():
    stock = _uptrend_stock(volume=5_000_000)
    not_a_member = pd.Series(False, index=stock.index)
    table = strategy.add_indicators(stock, _flat_nifty(stock.index), not_a_member)
    assert not table["signal"].any()


def test_quality_and_results_checks_switch_the_signal_off():
    stock = _uptrend_stock(volume=5_000_000)
    nifty = _flat_nifty(stock.index)
    yes = pd.Series(True, index=stock.index)
    no = pd.Series(False, index=stock.index)

    weak_business = strategy.add_indicators(stock, nifty, quality=no).iloc[-1]
    assert bool(weak_business["price_signal"]) and not bool(weak_business["signal"])

    results_due = strategy.add_indicators(stock, nifty, near_results=yes).iloc[-1]
    assert bool(results_due["price_signal"]) and not bool(results_due["signal"])
