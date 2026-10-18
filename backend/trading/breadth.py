"""Market-wide views for the Market tab: sector strength and breadth."""

import pandas as pd

import config
from trading import indicators


def sector_strength(ranking, close, in_trend, industry, days=21, minimum=3):
    """One row per industry, from the stocks the model scores today.

    month_% is the median one-month price change; above_ema_% the share of the
    industry's stocks above their 20-day EMA; score the median model score.
    """
    symbols = [s for s in ranking.index if s in close]
    month = close[symbols].iloc[-1] / close[symbols].iloc[-1 - days] - 1
    table = pd.DataFrame({
        "industry": [industry.get(s, "") or "Other" for s in symbols],
        "month_%": month.to_numpy() * 100,
        "above_ema": [bool(in_trend.get(s, False)) for s in symbols],
        "score": ranking.loc[symbols, "score"].to_numpy(),
    })
    grouped = table.groupby("industry").agg(
        stocks=("score", "size"), month_pct=("month_%", "median"),
        above_ema_pct=("above_ema", "mean"), score=("score", "median"))
    grouped = grouped[grouped["stocks"] >= minimum]
    grouped["above_ema_pct"] *= 100
    return grouped.round(1).sort_values("month_pct", ascending=False).rename(
        columns={"month_pct": "month_%", "above_ema_pct": "above_ema_%"})


def breadth(close, liquid, days=126):
    """Share of liquid stocks above their 20-day EMA and their 200-day average, each day."""
    fast = indicators.ema(close, config.EMA_FAST)
    long_average = close.rolling(200, min_periods=150).mean()
    counted = liquid.reindex_like(close).fillna(False).astype(bool)
    total = counted.sum(axis=1).astype(float).replace(0.0, float("nan"))
    above_fast = ((close > fast) & counted).sum(axis=1) / total
    above_long = ((close > long_average) & counted).sum(axis=1) / total
    return pd.DataFrame({"above_20_ema_%": above_fast * 100,
                         "above_200_day_%": above_long * 100}).astype(float).tail(days)
