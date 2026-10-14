"""Risk rules test (14 Oct 2026): industry limit, market breadth check, profit trail.

Run from the project folder:  python research/risk_rules_test.py
Each rule is tried alone against the current model, over the whole period and both
halves. Adopted only if it helps in both halves.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from trading import data, model
from research.weights_test import run


def set_breadth(built, minimum, base_checks):
    """Rebuild the market checks with (or without) the breadth check."""
    checks = base_checks.copy()
    if minimum:
        checks["breadth"] = (built.breadth >= minimum).astype(float).where(built.breadth.notna())
    built.checks = checks
    built.market_score = model.market_score(checks)
    built.market_ok = (built.market_score >= config.MODEL_MARKET_MIN).fillna(False)
    built.trading["market_ok"] = built.market_ok


if __name__ == "__main__":
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = model.up_to_last_close(data.load_market(config.BENCHMARK), stocks)
    built = model.from_disk(stocks, nifty)
    swing = config.MODEL_STYLES["swing"]
    base = dict(swing)
    base_checks = built.checks.copy()
    rows = [run(built, nifty, "now")]

    for limit in (2, 3):
        swing.update(base, max_per_industry=limit)
        rows.append(run(built, nifty, f"max {limit} per industry"))
    swing.clear(); swing.update(base)

    for minimum in (0.4, 0.5):
        set_breadth(built, minimum, base_checks)
        rows.append(run(built, nifty, f"breadth check: {minimum:.0%} above 20-day EMA"))
    set_breadth(built, None, base_checks)

    for label, trail in [("up 10%, then 7% off the peak", {"trigger": 0.10, "trail": 0.07}),
                         ("up 15%, then 10% off the peak", {"trigger": 0.15, "trail": 0.10}),
                         ("up 10%, then the 10-day EMA", {"trigger": 0.10, "fast": True}),
                         ("up 20%, then the 10-day EMA", {"trigger": 0.20, "fast": True})]:
        swing.update(base, profit_trail=trail)
        rows.append(run(built, nifty, f"profit trail: {label}"))
    swing.clear(); swing.update(base)

    print(pd.DataFrame(rows).set_index("variant").to_string())
    print(f"\ndone in {time.time() - started:.0f} s")
