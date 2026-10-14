"""Breadth check and profit trail, each alone, with the share-count fix, over 2018-2026."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from trading import data, model
from research.long_history_test import run
from research.risk_rules_test import set_breadth

if __name__ == "__main__":
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = model.up_to_last_close(data.load_market(config.BENCHMARK), stocks)
    config.MODEL_BREADTH_MIN = None
    config.MODEL_SHARES = "latest"
    built = model.from_disk(stocks, nifty)
    base_checks = built.checks.copy()
    swing = config.MODEL_STYLES["swing"]
    base = dict(swing)
    trail = base.pop("profit_trail", None)
    swing.clear(); swing.update(base)
    rows = [run(built, nifty, "share fix only")]
    set_breadth(built, 0.5, base_checks)
    rows.append(run(built, nifty, "+ breadth 50%"))
    set_breadth(built, 0.4, base_checks)
    rows.append(run(built, nifty, "+ breadth 40%"))
    set_breadth(built, None, base_checks)
    swing["profit_trail"] = trail
    rows.append(run(built, nifty, "+ profit trail 15%/10%"))
    swing["profit_trail"] = {"trigger": 0.10, "fast": True}
    rows.append(run(built, nifty, "+ profit trail 10% then 10-day EMA"))
    swing.clear(); swing.update(base)
    print(pd.DataFrame(rows).set_index("variant").drop(columns=[c for c in rows[0] if "Nifty" in c]).to_string())
    print(f"\ndone in {time.time() - started:.0f} s")
