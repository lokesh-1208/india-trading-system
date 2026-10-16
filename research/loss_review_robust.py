"""Is "sell after two closes below the 20-day EMA" robust? (16 Oct 2026)

Checks 1, 2 and 3 closes with 4, 5 and 6 positions in each period, the 2-close rule
with risk sizing (E), and the 2-close rule from different start months.
Run from the project folder:  python research/loss_review_robust.py
Output: reports/loss_review_robust.txt
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from trading import data, model, rotation
from research.loss_review_test import PERIODS, atr_percent

if __name__ == "__main__":
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = model.up_to_last_close(data.load_market(config.BENCHMARK), stocks)
    built = model.from_disk(stocks, nifty)
    lines = []

    def cell(**entry):
        out = []
        for _, start, end in PERIODS:
            s, _ = rotation.summarise(built.simulate(start=start, end=end, style="swing", **entry),
                                      nifty)
            out.append(f"{s['annual_growth_rate'] * 100:+6.1f}% / {s['max_drawdown'] * 100:6.1f}%")
        return "   ".join(out)

    lines.append("growth a year / worst fall in " + ", ".join(p[0] for p in PERIODS))
    for positions in (4, 5, 6):
        for closes in (1, 2, 3):
            label = f"{positions} stocks, sell after {closes} close{'s' if closes > 1 else ''}"
            lines.append(f"{label:34s}{cell(positions=positions, exit_confirm=closes)}")
            print(lines[-1], flush=True)

    swing = config.MODEL_STYLES["swing"]
    caution = np.where(built.strong_market().to_numpy(), 1.0, swing["caution_share"])
    caution = pd.DataFrame(np.repeat(caution[:, None], len(built.prepared["symbols"]), axis=1),
                           index=built.calendar, columns=built.prepared["symbols"])
    atr = atr_percent(built, stocks).reindex(index=built.calendar,
                                             columns=built.prepared["symbols"])
    scale = (0.01 * swing["positions"] / (config.ATR_STOP_MULTIPLE * atr)).clip(upper=1.0)
    lines.append(f"{'5 stocks, 2 closes + risk 1%':34s}"
                 f"{cell(exit_confirm=2, budget_scale=scale.fillna(1.0) * caution)}")
    print(lines[-1], flush=True)

    lines.append("\nDifferent start months, to 16 Oct 2026 (growth a year / worst fall):")
    for start in ("2022-02-01", "2022-08-01", "2023-02-01", "2023-08-01", "2024-02-01",
                  "2024-08-01", "2025-02-01"):
        row = []
        for closes in (1, 2):
            s, _ = rotation.summarise(built.simulate(start=start, style="swing",
                                                     exit_confirm=closes), nifty)
            row.append(f"{s['annual_growth_rate'] * 100:+6.1f}% / {s['max_drawdown'] * 100:6.1f}%")
        lines.append(f"  from {start}:  now {row[0]}   2 closes {row[1]}")
        print(lines[-1], flush=True)

    lines.append(f"\ndone in {time.time() - started:.0f} s")
    Path("reports/loss_review_robust.txt").write_text("\n".join(lines) + "\n")
