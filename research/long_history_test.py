"""Long-history test (14 Oct 2026): the model on 2018-2022, never used to design it.

Run from the project folder:  python research/long_history_test.py
Before 2022 the model has prices, sales and profit (NSE filings from 2017), PE and
earnings yield (with the latest share count), market checks and breadth; ownership,
balance sheet, cash flow and news are unknown (count as average). Three periods:
2018-22 (untouched), 2022-24 and 2024-26 (the halves every earlier test used).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from trading import data, model, rotation, weights
from research.risk_rules_test import set_breadth

PERIODS = (("2018-22", "2018-02-01", "2022-01-31"), ("2022-24", "2022-02-01", "2024-03-31"),
           ("2024-26", "2024-04-01", None))


def run(built, nifty, label, clear=False):
    if clear:
        built._cache = {}
    out = {"variant": label}
    for name, start, end in PERIODS:
        result = built.simulate(start=start, end=end, style="swing")
        summary, _ = rotation.summarise(result, nifty)
        out[f"{name} growth/yr"] = round(summary["annual_growth_rate"] * 100, 1)
        out[f"{name} worst fall"] = round(summary["max_drawdown"] * 100, 1)
        out[f"{name} Nifty/yr"] = round(summary["benchmark_annual_growth_rate"] * 100, 1)
    return out


if __name__ == "__main__":
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = model.up_to_last_close(data.load_market(config.BENCHMARK), stocks)
    config.MODEL_BREADTH_MIN = None
    built = model.from_disk(stocks, nifty)
    base_checks = built.checks.copy()
    swing = config.MODEL_STYLES["swing"]
    base = dict(swing)
    trail = base.pop("profit_trail", None)
    swing.clear(); swing.update(base)
    print(f"model built in {time.time() - started:.0f} s", flush=True)

    rows = []
    config.MODEL_SHARES = "filed"
    rows.append(run(built, nifty, "this morning's model (filed share counts)", clear=True))
    print("1 done", flush=True)
    config.MODEL_SHARES = "latest"
    rows.append(run(built, nifty, "share-count fix", clear=True))
    print("2 done", flush=True)
    set_breadth(built, 0.5, base_checks)
    swing["profit_trail"] = trail
    rows.append(run(built, nifty, "share fix + breadth 50% + profit trail (new model)"))
    print("3 done", flush=True)
    config.MODEL_SCORECARD = "industry"
    rows.append(run(built, nifty, "new model + industry scorecard", clear=True))
    config.MODEL_SCORECARD = "fixed"
    print("4 done", flush=True)
    table = pd.DataFrame(rows).set_index("variant")
    print(table.to_string())

    # Each group's weekly IC, by period, with the share-count fix
    built._cache = {}
    first = int(built.calendar.searchsorted(pd.Timestamp("2017-06-01")))
    groups = list(config.MODEL_WEIGHTS)
    ic = weights.weekly_ic(built, groups, start=first)
    rows = []
    for name, start, end in PERIODS:
        days = ic.index.map(lambda p: built.calendar[p])
        part = ic[(days >= pd.Timestamp(start)) & ((days <= pd.Timestamp(end)) if end else True)]
        for group in groups:
            values = part[group].dropna()
            rows.append({"period": name, "group": group,
                         "IC": round(values.mean(), 3) if len(values) else np.nan,
                         "t": round(values.mean() / values.std() * np.sqrt(len(values)), 1)
                         if len(values) > 2 else np.nan})
    print(pd.DataFrame(rows).pivot(index="group", columns="period", values=["IC", "t"]).to_string())

    built.measured_weights = weights.weights_from_ic(ic, groups)
    built._cache = {}
    print(pd.DataFrame([run(built, nifty, "new model + measured weights")]).set_index("variant").to_string())
    print(f"\ndone in {time.time() - started:.0f} s")
