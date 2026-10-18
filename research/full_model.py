"""Compare the full model (rule set E) with the ownership rotation (D) and Nifty.

Run from the project folder:  python research/full_model.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pandas as pd

import config
from trading import data, model, rotation, shareholding

started = time.time()
stocks = data.load_all_stocks()
nifty = data.load_market(config.BENCHMARK)
built = model.from_disk(stocks, nifty)
print(f"Model prepared in {time.time() - started:.0f} seconds")

runs = {
    "Full model, swing": built.simulate(start=config.ROTATION_START, style="swing"),
    "Full model, monthly": built.simulate(start=config.ROTATION_START, style="monthly"),
    "Ownership rotation (D)": rotation.simulate(built.prepared, shareholding.load_shareholding()),
}
print(f"\n{'':26s}{'growth/yr':>10s}{'drawdown':>10s}{'trades':>8s}{'won':>7s}{'charges':>9s}")
for name, result in runs.items():
    summary, by_year = rotation.summarise(result, nifty)
    print(f"{name:26s}{summary['annual_growth_rate']:>10.1%}{summary['max_drawdown']:>10.1%}"
          f"{summary['trades']:>8d}{summary['win_rate']:>7.0%}{summary['total_charges']:>9,.0f}")
    years = by_year
print(f"{'Nifty 50, bought and held':26s}{summary['benchmark_annual_growth_rate']:>10.1%}"
      f"{summary['benchmark_max_drawdown']:>10.1%}")
print(f"\nPeriod: {summary['period_start']} to {summary['period_end']}, after charges.")

print("\nReturn in each year (full model swing, Nifty):")
swing = runs["Full model, swing"]
_, by_year = rotation.summarise(swing, nifty)
trades = swing["trades"]
held = (pd.to_datetime(trades["exit_date"]) - pd.to_datetime(trades["entry_date"])).dt.days
print(f"Swing trades held for {held.median():.0f} days in the middle case "
      f"(a quarter under {held.quantile(0.25):.0f}, a quarter over {held.quantile(0.75):.0f}); "
      f"{(trades['reason'] == 'stop-loss').mean():.0%} ended on the stop-loss.")
print((by_year * 100).round(1).to_string())

plan = built.decision([])
print(f"\nMarket checks passed today: {plan['market_score']:.0%}")
for name, passed in plan["checks"].items():
    print(f"  [{'yes' if passed == 1 else 'no ' if passed == 0 else ' - '}] {name}")
columns = ["score", *model.GROUPS]
print("\nTop 10 today:")
print(plan["today"][columns].head(10).round(0).to_string())
print("\nWeakest 10 today (sell / avoid):")
print(plan["weakest"][columns].round(0).to_string())
