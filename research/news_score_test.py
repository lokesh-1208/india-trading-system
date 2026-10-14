"""News score test (14 Oct 2026): filing types (now) against good/bad reading ("lean").

Run from the project folder:  python research/news_score_test.py
News history starts 13 Oct 2025, so the test covers one year only:
  1. Prediction: each week, the rank correlation (Spearman) between a stock's news
     score and its return over the next 5 trading days, among all scored stocks;
     and the average next-week return of stocks with good, no and bad news.
  2. Backtest of the swing model with news off, "types" and "lean", over the year
     and its two halves. A change is adopted only if it helps in both halves.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from trading import data, model, rotation

START, MIDDLE = "2025-11-14", "2026-05-01"
HALVES = (("year", START, None), ("Nov-Apr", START, "2026-04-30"), ("May-Oct", MIDDLE, None))


def weekly_positions(built, start):
    calendar = built.calendar
    first = int(calendar.searchsorted(pd.Timestamp(start)))
    # The signal day: the last trading day of each week (the list is made from its close).
    days = [p for p in range(first, len(calendar) - 5)
            if calendar[p + 1].isocalendar()[:2] != calendar[p].isocalendar()[:2]]
    return days


def prediction(built, mode):
    config.MODEL_NEWS_MODE = mode
    close = built.prepared["last_close"]
    rows = []
    for position in weekly_positions(built, START):
        factors = built.factors_on(position)
        ahead = (close.iloc[position + 5] / close.iloc[position] - 1).reindex(factors.index)
        table = pd.DataFrame({"news": factors["news_score"], "ahead": ahead}).dropna()
        if len(table) < 50 or table["news"].nunique() < 2:
            continue
        rows.append({"day": built.calendar[position],
                     "ic": table["news"].rank().corr(table["ahead"].rank()),
                     "good": table.loc[table["news"] > 0, "ahead"].mean() * 100,
                     "none": table.loc[table["news"] == 0, "ahead"].mean() * 100,
                     "bad": table.loc[table["news"] < 0, "ahead"].mean() * 100,
                     "n_good": int((table["news"] > 0).sum()), "n_bad": int((table["news"] < 0).sum())})
    return pd.DataFrame(rows)


def summarise_prediction(frame, label):
    out = []
    for name, start, end in HALVES:
        part = frame[(frame["day"] >= pd.Timestamp(start))
                     & ((frame["day"] <= pd.Timestamp(end)) if end else True)]
        ic = part["ic"]
        out.append({"news score": label, "period": name, "weeks": len(part),
                    "avg IC": round(ic.mean(), 3),
                    "t": round(ic.mean() / ic.std() * np.sqrt(len(ic)), 2) if len(ic) > 2 else np.nan,
                    "good news %": round(part["good"].mean(), 2),
                    "no news %": round(part["none"].mean(), 2),
                    "bad news %": round(part["bad"].mean(), 2),
                    "good/bad per week": f"{part['n_good'].mean():.0f}/{part['n_bad'].mean():.0f}"})
    return out


def backtest(built, nifty, label, mode, news_weight):
    config.MODEL_NEWS_MODE = mode
    weights = dict(config.MODEL_WEIGHTS)
    config.MODEL_WEIGHTS["news"] = news_weight
    built._cache = {}
    out = {"variant": label}
    for name, start, end in HALVES:
        result = built.simulate(start=start, end=end, style="swing")
        summary, _ = rotation.summarise(result, nifty)
        out[f"{name} growth"] = round(summary["total_return"] * 100, 1)
        out[f"{name} worst fall"] = round(summary["max_drawdown"] * 100, 1)
        if name == "year":
            out["trades"] = summary["trades"]
            out["nifty"] = round(summary["benchmark_total_return"] * 100, 1)
    config.MODEL_WEIGHTS.clear()
    config.MODEL_WEIGHTS.update(weights)
    built._cache = {}
    return out


if __name__ == "__main__":
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = model.up_to_last_close(data.load_market(config.BENCHMARK), stocks)
    built = model.from_disk(stocks, nifty)
    print(f"model built in {time.time() - started:.0f} s", flush=True)

    rows = []
    for mode in ("types", "lean"):
        frame = prediction(built, mode)
        rows += summarise_prediction(frame, mode)
        print(f"prediction {mode} done ({time.time() - started:.0f} s)", flush=True)
    print("\n=== 1. Does the news score predict next week's return? ===")
    print(pd.DataFrame(rows).to_string(index=False))

    news_weight = config.MODEL_WEIGHTS["news"]
    tests = [backtest(built, nifty, "news off", "types", 0.0),
             backtest(built, nifty, "filing types (now)", "types", news_weight),
             backtest(built, nifty, "good/bad reading", "lean", news_weight)]
    print("\n=== 2. Swing backtest, total return % (not per year) ===")
    print(pd.DataFrame(tests).set_index("variant").to_string())
    print(f"\ndone in {time.time() - started:.0f} s")
