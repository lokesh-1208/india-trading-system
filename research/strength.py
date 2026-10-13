"""Strength tests for the swing model (13 Oct 2026). One script, every variant.

Run from the project folder:  python research/strength.py [group ...]
Groups: sizing, settings, results, groups, starts. Each variant runs on the whole
period and on both halves; a change is kept only if it helps in both halves.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from trading import data, indicators, model, rotation

HALVES = (("all", config.ROTATION_START, None), ("2022-24", "2022-02-01", "2024-03-31"),
          ("2024-26", "2024-04-01", None))


def run(built, nifty, label, **settings):
    out = {"variant": label}
    for name, start, end in HALVES:
        result = built.simulate(start=start, end=end, style="swing", **settings)
        summary, _ = rotation.summarise(result, nifty)
        out[f"{name} growth"] = round(summary["annual_growth_rate"] * 100, 1)
        out[f"{name} worst fall"] = round(summary["max_drawdown"] * 100, 1)
        if name == "all":
            out["trades"] = summary["trades"]
    return out


def show(rows, title):
    table = pd.DataFrame(rows).set_index("variant")
    print(f"\n=== {title} ===")
    print(table.to_string())
    return table


def sizing(built, nifty):
    calendar, symbols = built.calendar, built.prepared["symbols"]
    level = built.market_score
    above = built.prepared["market_ok"]
    strong = (level >= config.MODEL_STRONG_MARKET) & above
    rows = [run(built, nifty, "equal amounts (now)")]
    for share in (0.75, 0.5):
        scale = pd.DataFrame(np.repeat(np.where(strong.to_numpy(), 1.0, share)[:, None],
                                       len(symbols), axis=1), index=calendar, columns=symbols)
        rows.append(run(built, nifty, f"caution market: {share:.0%} amounts", budget_scale=scale))
    atr = built.price["atr_pct"]
    for q in (0.5, 0.75):
        target = atr.quantile(q, axis=1)
        scale = (1 / atr).mul(target, axis=0).clip(upper=1.0)
        rows.append(run(built, nifty, f"risky stocks smaller (target {q:.0%} quantile)",
                        budget_scale=scale))
    both = pd.DataFrame(np.repeat(np.where(strong.to_numpy(), 1.0, 0.75)[:, None],
                                  len(symbols), axis=1), index=calendar, columns=symbols) * (1 / atr).mul(atr.quantile(0.75, axis=1), axis=0).clip(upper=1.0)
    rows.append(run(built, nifty, "both: caution 75% x risky smaller", budget_scale=both))
    return show(rows, "1. Position sizing")


def settings(built, nifty):
    rows = [run(built, nifty, "now: 8% stop, 20-day EMA, 5 stocks, top 10")]
    for stop in (0.06, 0.10, 0.12, None):
        rows.append(run(built, nifty, f"stop {stop:.0%}" if stop else "no hard stop",
                        stop_loss=stop))
    for positions in (4, 6, 8):
        rows.append(run(built, nifty, f"{positions} stocks", positions=positions))
    for buy_rank in (5, 15, 20):
        rows.append(run(built, nifty, f"buy from top {buy_rank}", buy_rank=buy_rank,
                        keep_rank=buy_rank))
    close = built.prepared["last_close"]
    original = built.trading["in_trend"]
    for span in (10, 30, 50):
        built.trading["in_trend"] = (close > indicators.ema(close, span)).fillna(False)
        rows.append(run(built, nifty, f"exit on {span}-day EMA"))
    built.trading["in_trend"] = original
    return show(rows, "2. Settings")


def results(built, nifty):

    rows = [run(built, nifty, "hold through results (now)")]
    for days in (2, 5):
        table = model.results_soon_table(built.results, built.calendar,
                                         built.prepared["symbols"], days=days)
        rows.append(run(built, nifty, f"sell {days} days before results", exit_before=table))

    return show(rows, "4. Results day")


def groups(built, nifty):
    rows = [run(built, nifty, "all groups (now)")]
    weights = dict(config.MODEL_WEIGHTS)
    for group in weights:
        config.MODEL_WEIGHTS.clear()
        config.MODEL_WEIGHTS.update({g: (0.0 if g == group else w) for g, w in weights.items()})
        built._cache = {}
        rows.append(run(built, nifty, f"without {group}"))
    config.MODEL_WEIGHTS.clear()
    config.MODEL_WEIGHTS.update(weights)
    built._cache = {}
    return show(rows, "3. Score groups")


def starts(built, nifty):
    rows = []
    for start in pd.date_range("2022-02-01", "2025-02-01", freq="6MS"):
        result = built.simulate(start=start, style="swing")
        summary, _ = rotation.summarise(result, nifty)
        rows.append({"variant": f"from {start:%b %Y}",
                     "growth": round(summary["annual_growth_rate"] * 100, 1),
                     "worst fall": round(summary["max_drawdown"] * 100, 1),
                     "nifty": round(summary["benchmark_annual_growth_rate"] * 100, 1)})
    return show(rows, "5. Start dates")


if __name__ == "__main__":
    wanted = sys.argv[1:] or ["sizing", "settings", "results", "groups", "starts"]
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = data.load_market(config.BENCHMARK)
    built = model.from_disk(stocks, nifty)
    print(f"model ready in {time.time() - started:.0f} s")
    for name in wanted:
        globals()[name](built, nifty)
        print(f"({time.time() - started:.0f} s)")
