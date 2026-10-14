"""Breadth check 50% and profit trail (15% up, 10% off the peak), alone and together."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from trading import data, model
from research.weights_test import run
from research.risk_rules_test import set_breadth

if __name__ == "__main__":
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = model.up_to_last_close(data.load_market(config.BENCHMARK), stocks)
    built = model.from_disk(stocks, nifty)
    swing = config.MODEL_STYLES["swing"]
    base = dict(swing)
    base_checks = built.checks.copy()
    trail = {"trigger": 0.15, "trail": 0.10}
    rows = [run(built, nifty, "now")]
    set_breadth(built, 0.5, base_checks)
    rows.append(run(built, nifty, "breadth 50%"))
    swing.update(base, profit_trail=trail)
    rows.append(run(built, nifty, "breadth 50% + profit trail 15%/10%"))
    set_breadth(built, None, base_checks)
    rows.append(run(built, nifty, "profit trail 15%/10%"))
    swing.clear(); swing.update(base)
    print(pd.DataFrame(rows).set_index("variant").to_string())
    print(f"\ndone in {time.time() - started:.0f} s")
