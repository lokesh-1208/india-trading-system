"""After the first three real losses (16 Oct 2026): do any of these rules help?

  A  skip a buy whose signal close is too close to its 20-day EMA (min_room)
  B  sell only when the trend break is real: two closes below the EMA, or a
     close more than 1-2% below it (exit_confirm, exit_buffer)
  D  at most 2 stocks from one industry (max_per_industry)
  E  size each buy so a 1.5 x ATR move costs about 1% (or 0.75%) of the account

Same rule as every entry in the backtest log: a change is adopted only if it helps
in each period, not just overall. Run from the project folder:
    python research/loss_review_test.py
Output: reports/loss_review.txt
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from trading import data, model, rotation

PERIODS = (("2018-22", "2018-02-01", "2022-01-31"), ("2022-24", "2022-02-01", "2024-03-31"),
           ("2024-26", "2024-04-01", None))


def atr_percent(built, stocks):
    calendar, close = built.calendar, built.prepared["last_close"]
    high = rotation._wide(stocks, "High", calendar).ffill()
    low = rotation._wide(stocks, "Low", calendar).ffill()
    before = close.shift(1)
    day_range = np.maximum(high - low, np.maximum((high - before).abs(), (low - before).abs()))
    return (day_range.ewm(alpha=1 / config.ATR_PERIOD, adjust=False,
                          min_periods=config.ATR_PERIOD).mean() / close)


def run(built, nifty, label, **entry):
    out = {"variant": label}
    for name, start, end in PERIODS:
        result = built.simulate(start=start, end=end, style="swing", **entry)
        summary, _ = rotation.summarise(result, nifty)
        trades = result["trades"]
        out[f"{name} growth/yr"] = round(summary["annual_growth_rate"] * 100, 1)
        out[f"{name} worst fall"] = round(summary["max_drawdown"] * 100, 1)
        out[f"{name} trades"] = len(trades)
        out[f"{name} won"] = round((trades["profit"] > 0).mean() * 100) if len(trades) else 0
        out[f"{name} Nifty/yr"] = round(summary["benchmark_annual_growth_rate"] * 100, 1)
    print(label, "done", flush=True)
    return out


if __name__ == "__main__":
    started = time.time()
    stocks = data.load_all_stocks()
    nifty = model.up_to_last_close(data.load_market(config.BENCHMARK), stocks)
    built = model.from_disk(stocks, nifty)
    print(f"model built in {time.time() - started:.0f} s", flush=True)

    swing = config.MODEL_STYLES["swing"]
    caution = np.where(built.strong_market().to_numpy(), 1.0, swing["caution_share"])
    caution = pd.DataFrame(np.repeat(caution[:, None], len(built.prepared["symbols"]), axis=1),
                           index=built.calendar, columns=built.prepared["symbols"])
    atr = atr_percent(built, stocks).reindex(index=built.calendar,
                                             columns=built.prepared["symbols"])
    positions = swing["positions"]

    def risk_scale(risk):
        # A full place is account / positions; a 1.5 x ATR fall on it should cost `risk`.
        scale = (risk * positions / (config.ATR_STOP_MULTIPLE * atr)).clip(upper=1.0)
        return (scale.fillna(1.0) * caution)

    rows = [
        run(built, nifty, "now"),
        run(built, nifty, "A room >= 1%", min_room=0.01),
        run(built, nifty, "A room >= 2%", min_room=0.02),
        run(built, nifty, "B exit after 2 closes below", exit_confirm=2),
        run(built, nifty, "B exit 1% below line", exit_buffer=0.01),
        run(built, nifty, "B exit 2% below line", exit_buffer=0.02),
        run(built, nifty, "D max 2 per industry", max_per_industry=2),
        run(built, nifty, "E risk 1% per trade", budget_scale=risk_scale(0.01)),
        run(built, nifty, "E risk 0.75% per trade", budget_scale=risk_scale(0.0075)),
    ]
    table = pd.DataFrame(rows).set_index("variant")
    nifty_cols = [c for c in table if "Nifty" in c]
    text = (table.drop(columns=nifty_cols).to_string() + "\n\nNifty a year: "
            + ", ".join(f"{c.split()[0]} {table[c].iloc[0]:+.1f}%" for c in nifty_cols)
            + f"\n\ndone in {time.time() - started:.0f} s\n")
    print(text)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/loss_review.txt").write_text(text)
