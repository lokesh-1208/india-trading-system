"""Technical indicators. Each function takes price columns and returns a column."""

import pandas as pd


def ema(close, days):
    """Exponential moving average: an average that gives recent days more weight."""
    return close.ewm(span=days, adjust=False, min_periods=days).mean()


def rsi(close, days=14):
    """Relative Strength Index (Wilder), from 0 to 100.

    Above 50 means recent gains are larger than recent losses.
    """
    change = close.diff()
    gain = change.clip(lower=0)
    loss = -change.clip(upper=0)
    average_gain = gain.ewm(alpha=1 / days, adjust=False, min_periods=days).mean()
    average_loss = loss.ewm(alpha=1 / days, adjust=False, min_periods=days).mean()
    # When there are no losses at all this divides by zero and gives infinity,
    # which correctly turns into an RSI of 100.
    strength = average_gain / average_loss
    return 100 - 100 / (1 + strength)


def true_range(high, low, close):
    """The day's real movement, including any gap from yesterday's close."""
    previous_close = close.shift(1)
    ranges = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(high, low, close, days=14):
    """Average True Range (Wilder): how many rupees the stock moves in a normal day."""
    return true_range(high, low, close).ewm(
        alpha=1 / days, adjust=False, min_periods=days
    ).mean()
