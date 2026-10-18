"""How should a swing-model buy be placed when the stock has already moved?

The swing style decides at a close and buys at the next open. This compares
entry policies over the same period, after charges:
  - buy at the open, whatever the gap (the current rule)
  - skip the buy if the open is more than 1%, 2% or 3% above the signal close
  - a limit order at the signal close, valid 1 or 2 days, cancelled if not filled
It also splits the current rule's trades by the size of the opening gap.

Run from the project folder:  python research/entry_gap.py
Limit: daily prices only, so a fill is assumed when the day's low goes below
the limit. In real markets a touch does not always fill.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pandas as pd

import config
from trading import data, model, rotation

started = time.time()
stocks = data.load_all_stocks()
nifty = data.load_market(config.BENCHMARK)
built = model.from_disk(stocks, nifty)
print(f"Model prepared in {time.time() - started:.0f} seconds")

policies = {
    "Buy at open (now)": {},
    "Skip if gap > 1%": {"max_gap": 0.01},
    "Skip if gap > 2%": {"max_gap": 0.02},
    "Skip if gap > 3%": {"max_gap": 0.03},
    "Limit at signal, 1 day": {"limit_days": 1},
    "Limit at signal, 2 days": {"limit_days": 2},
}
rows, results = [], {}
for name, entry in policies.items():
    result = built.simulate(start=config.ROTATION_START, style="swing", **entry)
    results[name] = result
    summary, by_year = rotation.summarise(result, nifty)
    rows.append({
        "policy": name,
        "growth/yr": summary["annual_growth_rate"],
        "drawdown": summary["max_drawdown"],
        "trades": summary["trades"],
        "won": summary["win_rate"],
        "skipped": sum(result["skipped"].values()),
        **{str(year): value for year, value in by_year["strategy"].items()},
    })
    print(f"{name} done ({time.time() - started:.0f} s)")

table = pd.DataFrame(rows).set_index("policy")
pct = lambda v: f"{v:+.1%}" if isinstance(v, float) else v
print(f"\nPeriod: {summary['period_start']} to {summary['period_end']}, after charges. "
      f"Nifty: {summary['benchmark_annual_growth_rate']:+.1%} a year, "
      f"drawdown {summary['benchmark_max_drawdown']:.1%}\n")
print(table.map(lambda v: pct(v) if isinstance(v, float) else v).to_string())

trades = results["Buy at open (now)"]["trades"].copy()
trades["return_%"] = (trades["exit_price"] / trades["entry_price"] - 1) * 100
buckets = pd.cut(trades["gap_%"], [-100, -1, 0, 1, 2, 3, 100],
                 labels=["below -1%", "-1% to 0", "0 to 1%", "1% to 2%", "2% to 3%", "above 3%"])
split = trades.groupby(buckets, observed=False).agg(
    trades=("profit", "size"), won=("profit", lambda p: (p > 0).mean()),
    avg_return_pct=("return_%", "mean"), median_return_pct=("return_%", "median"),
    total_profit=("profit", "sum"))
print("\nCurrent rule, trades split by opening gap (open on buy day vs signal close):")
print(split.round(2).to_string())

out = config.REPORTS_DIR / "entry_gap.txt"
out.write_text(table.map(lambda v: pct(v) if isinstance(v, float) else v).to_string()
               + "\n\n" + split.round(2).to_string() + "\n", encoding="utf-8")
print(f"\nSaved {out}")
