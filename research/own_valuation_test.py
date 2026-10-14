"""Valuation against the stock's own history (14 Oct 2026): does it predict next week?

Run from the project folder:  python research/own_valuation_test.py
Factor: today's earnings yield (yearly profit / market value, latest share count)
divided by the median of the same figure on 12 quarter-spaced dates over the past
3 years, each using only the profit that was public on that date. Higher = cheaper
than usual for this stock. Weekly rank correlation with the next 5 days' return.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from trading import data, model, weights

PERIODS = (("2018-22", "2018-02-01", "2022-01-31"), ("2022-24", "2022-02-01", "2024-03-31"),
           ("2024-26", "2024-04-01", None))

if __name__ == "__main__":
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = model.up_to_last_close(data.load_market(config.BENCHMARK), stocks)
    built = model.from_disk(stocks, nifty)
    close = built.prepared["last_close"]
    shares = built.latest_shares
    calendar = built.calendar
    profit_cache = {}

    def yield_on(day):
        day = calendar[min(int(calendar.searchsorted(day, side="right")) - 1, len(calendar) - 1)]
        if day not in profit_cache:
            year = model._latest(built.annual, day, "period_end", 640)
            profit = year["net_income"] if "net_income" in year else pd.Series(dtype=float)
            value = close.loc[day] * shares.reindex(close.columns)
            profit_cache[day] = (profit.reindex(close.columns) / value).where(value > 0)
        return profit_cache[day]

    rows = []
    first = int(calendar.searchsorted(pd.Timestamp("2018-02-01")))
    for position in weights.signal_positions(calendar, first):
        if position + 5 >= len(calendar):
            break
        day = calendar[position]
        now = yield_on(day)
        past = pd.concat([yield_on(day - pd.Timedelta(days=91 * k)) for k in range(1, 13)], axis=1)
        usual = past.median(axis=1).where(past.count(axis=1) >= 8)
        factor = (now / usual).where(usual > 0)
        liquid = built.prepared["liquid"].iloc[position]
        ahead = close.iloc[position + 5] / close.iloc[position] - 1
        pair = pd.DataFrame({"f": factor, "a": ahead})[liquid.reindex(close.columns).fillna(False)].dropna()
        if len(pair) >= 50:
            rows.append({"day": day, "ic": pair["f"].rank().corr(pair["a"].rank()), "n": len(pair)})
    ic = pd.DataFrame(rows)
    out = []
    for name, start, end in PERIODS:
        part = ic[(ic["day"] >= pd.Timestamp(start)) & ((ic["day"] <= pd.Timestamp(end)) if end else True)]
        out.append({"period": name, "weeks": len(part), "stocks/week": round(part["n"].mean()),
                    "avg IC": round(part["ic"].mean(), 3),
                    "t": round(part["ic"].mean() / part["ic"].std() * np.sqrt(len(part)), 1)})
    print(pd.DataFrame(out).to_string(index=False))
    print(f"\ndone in {time.time() - started:.0f} s")
