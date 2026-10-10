"""Checks that each indicator gives the value we can work out by hand."""

import math

import pandas as pd

from trading import indicators


def test_ema_of_a_constant_price_is_that_price():
    close = pd.Series([50.0] * 30)
    assert indicators.ema(close, 10).iloc[-1] == 50.0


def test_ema_matches_hand_calculation():
    # span 3 -> each day: 0.5 x today's price + 0.5 x yesterday's EMA
    result = indicators.ema(pd.Series([1.0, 2.0, 3.0, 4.0]), 3)
    assert pd.isna(result.iloc[0]) and pd.isna(result.iloc[1])
    assert math.isclose(result.iloc[2], 2.25)
    assert math.isclose(result.iloc[3], 3.125)


def test_rsi_is_100_when_price_only_rises():
    close = pd.Series([float(price) for price in range(100, 140)])
    assert indicators.rsi(close, 14).iloc[-1] == 100.0


def test_rsi_is_0_when_price_only_falls():
    close = pd.Series([float(price) for price in range(140, 100, -1)])
    assert indicators.rsi(close, 14).iloc[-1] == 0.0


def test_rsi_with_gains_twice_the_losses():
    # +2 one day, -1 the next: gains are twice the losses, so RSI is near 66.7
    prices = [100.0]
    for day in range(200):
        prices.append(prices[-1] + (2 if day % 2 == 0 else -1))
    result = indicators.rsi(pd.Series(prices), 14).iloc[-1]
    assert 64 < result < 70


def test_true_range_includes_the_gap_from_yesterday():
    high = pd.Series([10.0, 15.0])
    low = pd.Series([9.0, 14.0])
    close = pd.Series([9.5, 14.5])
    # Day 2: high-low is 1, but the jump from yesterday's close 9.5 to 15 is 5.5
    assert indicators.true_range(high, low, close).iloc[1] == 5.5


def test_atr_of_a_steady_2_rupee_range_is_2():
    days = 40
    high = pd.Series([102.0] * days)
    low = pd.Series([100.0] * days)
    close = pd.Series([101.0] * days)
    assert math.isclose(indicators.atr(high, low, close, 14).iloc[-1], 2.0)


def test_period_return():
    close = pd.Series([100.0, 105.0, 110.0])
    assert math.isclose(indicators.period_return(close, 2).iloc[-1], 0.10)
