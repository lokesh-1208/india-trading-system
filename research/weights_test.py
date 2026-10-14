"""Group weights and scorecard test (14 Oct 2026).

Run from the project folder:  python research/weights_test.py
1. Weekly information coefficient (IC) of each score group: rank correlation with the
   next 5 trading days' return, all scored stocks, signal day = last day of the week.
2. Swing backtest, whole period and both halves, for:
   fixed weights (now) / equal weights / measured weights (trading/weights.py);
   scorecard fixed (now) / industry medians / off.
A change is adopted only if it helps in both halves.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from trading import data, model, rotation, weights

HALVES = (("all", config.ROTATION_START, None), ("2022-24", "2022-02-01", "2024-03-31"),
          ("2024-26", "2024-04-01", None))
GROUPS = list(config.MODEL_WEIGHTS)


def run(built, nifty, label):
    built._cache = {}
    out = {"variant": label}
    for name, start, end in HALVES:
        result = built.simulate(start=start, end=end, style="swing")
        summary, _ = rotation.summarise(result, nifty)
        out[f"{name} growth/yr"] = round(summary["annual_growth_rate"] * 100, 1)
        out[f"{name} worst fall"] = round(summary["max_drawdown"] * 100, 1)
        if name == "all":
            out["trades"] = summary["trades"]
            out["won"] = round(summary["win_rate"] * 100)
    return out


def ic_summary(ic):
    rows = []
    for name, start, end in HALVES:
        days = ic.index.map(lambda p: built.calendar[p])
        mask = (days >= pd.Timestamp(start)) & ((days <= pd.Timestamp(end)) if end else True)
        part = ic[mask]
        for group in GROUPS:
            values = part[group].dropna()
            rows.append({"period": name, "group": group, "weeks": len(values),
                         "avg IC": round(values.mean(), 3) if len(values) else np.nan,
                         "t": round(values.mean() / values.std() * np.sqrt(len(values)), 2)
                         if len(values) > 2 else np.nan,
                         "weeks positive %": round((values > 0).mean() * 100) if len(values) else np.nan})
    table = pd.DataFrame(rows)
    return table.pivot(index="group", columns="period", values=["avg IC", "t", "weeks"])


if __name__ == "__main__":
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = model.up_to_last_close(data.load_market(config.BENCHMARK), stocks)
    built = model.from_disk(stocks, nifty)
    print(f"model built in {time.time() - started:.0f} s", flush=True)

    first = int(built.calendar.searchsorted(pd.Timestamp("2020-01-01")))
    ic = weights.weekly_ic(built, GROUPS, start=first)
    print(f"weekly IC for {len(ic)} weeks ({time.time() - started:.0f} s)", flush=True)
    print("\n=== 1. How well each group predicted the next 5 days (weekly IC) ===")
    print(ic_summary(ic).to_string())

    fixed = dict(config.MODEL_WEIGHTS)
    measured = weights.weights_from_ic(ic, GROUPS)
    latest = measured[max(measured)]
    print("\nMeasured weights now:", {g: round(w, 3) for g, w in latest.items()})
    sample = {built.calendar[p].date(): {g: round(w, 2) for g, w in v.items()}
              for p, v in list(measured.items())[::26]}
    print(pd.DataFrame(sample).T.to_string())

    rows = [run(built, nifty, "fixed weights, fixed scorecard (now)")]
    config.MODEL_WEIGHTS.clear(); config.MODEL_WEIGHTS.update({g: 1.0 for g in GROUPS})
    rows.append(run(built, nifty, "equal weights"))
    config.MODEL_WEIGHTS.clear(); config.MODEL_WEIGHTS.update(fixed)
    built.measured_weights = measured
    rows.append(run(built, nifty, "measured weights"))
    built.measured_weights = {}
    for mode in ("industry", "off"):
        config.MODEL_SCORECARD = mode
        rows.append(run(built, nifty, f"scorecard {mode}"))
    config.MODEL_SCORECARD = "fixed"
    print("\n=== 2. Swing backtest ===")
    print(pd.DataFrame(rows).set_index("variant").to_string())
    print(f"\ndone in {time.time() - started:.0f} s")
