"""The swing trading rules.

A stock gives a signal at the close of a day when ALL of these are true:
  - member: it was in the Nifty 500 on that day
  - quality: the business passes the quality filter (see fundamentals.py)
  - timing: the company is not about to announce results
  - liquid: average daily traded value is above the minimum
  - uptrend: close is above both the fast and the slow EMA
  - momentum: RSI is between RSI_MIN and RSI_MAX
  - interest: today's volume is above its recent average
  - strength: the stock did better than Nifty over the last 3 months

The trade itself (see backtest.py and report.py):
  - buy the next day only if price goes above the signal day's high
  - stop-loss 1.5 x ATR below the entry
  - target at 2 x the risk, or exit when the close falls below the fast EMA
  - new trades only when Nifty is above its own 50-day EMA
"""

import math

import pandas as pd

import config
from trading import indicators


def add_indicators(prices, nifty_close, member=None, quality=None, near_results=None):
    """Return a copy of the price table with indicator and signal columns added.

    Each of these is a True/False value per day. Leave one empty to switch
    that check off.
      member       : the stock was in the index that day
      quality      : the business passed the quality filter that day
      near_results : results are due within the next few days
    """
    table = prices.copy()
    close = table["Close"]

    table["ema_fast"] = indicators.ema(close, config.EMA_FAST)
    table["ema_slow"] = indicators.ema(close, config.EMA_SLOW)
    table["rsi"] = indicators.rsi(close, config.RSI_PERIOD)
    table["atr"] = indicators.atr(
        table["High"], table["Low"], close, config.ATR_PERIOD
    )

    # Today's volume against the average of the previous 20 days.
    average_volume = table["Volume"].rolling(config.VOLUME_AVG_DAYS).mean().shift(1)
    table["volume_ratio"] = table["Volume"] / average_volume

    # Average daily traded value in crore rupees (1 crore = 10,000,000).
    traded_value = close * table["Volume"]
    table["turnover_crore"] = (
        traded_value.rolling(config.VOLUME_AVG_DAYS).mean() / 1e7
    )

    # Relative strength: stock's 3-month return minus Nifty's 3-month return.
    nifty_return = indicators.period_return(nifty_close, config.RS_LOOKBACK_DAYS)
    stock_return = indicators.period_return(close, config.RS_LOOKBACK_DAYS)
    table["relative_strength"] = stock_return - nifty_return.reindex(table.index)

    enough_history = _row_numbers(table) >= config.MIN_HISTORY_DAYS
    table["member"] = _flag(member, table.index, default=True)
    table["quality_ok"] = _flag(quality, table.index, default=True)
    table["near_results"] = _flag(near_results, table.index, default=False)

    # The price rules on their own, before quality and results timing.
    table["price_signal"] = (
        enough_history
        & table["member"]
        & (table["turnover_crore"] >= config.MIN_TURNOVER_CRORE)
        & (close > table["ema_fast"])
        & (close > table["ema_slow"])
        & (table["rsi"] >= config.RSI_MIN)
        & (table["rsi"] <= config.RSI_MAX)
        & (table["volume_ratio"] > 1)
        & (table["relative_strength"] > 0)
        & (table["atr"] > 0)
    )
    table["signal"] = (
        table["price_signal"] & table["quality_ok"] & ~table["near_results"]
    )
    return table


def _flag(values, index, default):
    """A True/False column from an optional per-day series."""
    if values is None:
        return pd.Series(default, index=index)
    return values.reindex(index).fillna(default).astype(bool)


def _row_numbers(table):
    """1 for the first row, 2 for the second and so on, as a column."""
    return table["Close"].notna().cumsum()


def market_is_healthy(nifty):
    """True on days when Nifty closed above its own EMA. One value per day."""
    trend = indicators.ema(nifty["Close"], config.MARKET_EMA)
    return nifty["Close"] > trend


def stop_and_target(entry_price, atr_value):
    """Return (stop-loss price, target price) for a planned entry."""
    stop = entry_price - config.ATR_STOP_MULTIPLE * atr_value
    target = entry_price + config.TARGET_R * (entry_price - stop)
    return stop, target


def position_size(equity, entry_price, stop_price, cash=None):
    """How many shares to buy. The answer is never chosen by feel.

    It is the smallest of three limits:
      - risk:  losing (entry - stop) on every share costs 1% of equity
      - size:  the position is at most 25% of equity
      - cash:  you cannot spend more than you have (no leverage)
    """
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0 or entry_price <= 0:
        return 0

    by_risk = equity * config.RISK_PER_TRADE / risk_per_share
    by_size = equity * config.MAX_POSITION_FRACTION / entry_price
    quantity = min(by_risk, by_size)

    if cash is not None:
        # Keep a little aside for the buying charges (about 0.12%).
        by_cash = cash / (entry_price * 1.002)
        quantity = min(quantity, by_cash)

    return max(0, math.floor(quantity))
