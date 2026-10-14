"""Back-in-range test (14 Oct 2026): fill free places mid-week from the week's list.

Run from the project folder:  python research/midweek_test.py
With midweek_fill a place left free (a pick that gapped above its limit, or a sale)
is filled on a later day of the same week from the same list, if the stock opens no
more than 2% above its Friday close and is still above its 20-day EMA. Tested with the
fixed and the industry scorecard. Adopted only if it helps in both halves.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from trading import data, model
from research.weights_test import run

if __name__ == "__main__":
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = model.up_to_last_close(data.load_market(config.BENCHMARK), stocks)
    built = model.from_disk(stocks, nifty)
    rows = []
    for card in ("fixed", "industry"):
        config.MODEL_SCORECARD = card
        for fill in (False, True):
            config.MODEL_STYLES["swing"]["midweek_fill"] = fill
            rows.append(run(built, nifty, f"scorecard {card}, " + ("back-in-range buys" if fill else "Monday only")))
    print(pd.DataFrame(rows).set_index("variant").to_string())
    print(f"\ndone in {time.time() - started:.0f} s")
