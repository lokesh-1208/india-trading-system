"""Do the news ideas make money? Backtest them over the saved announcements.

Run:  python research/news_ideas_test.py
Prints three results for the same period: buying the news ideas (with the
model's view), buying any good news, and the weekly list. Update
newsview.IDEA_TEST_NOTE when the numbers change.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

import config  # noqa: E402
from trading import data, flows, fundamentals, model, news, newsview, rotation  # noqa: E402

stocks = data.load_all_stocks()
nifty = data.load_market(config.BENCHMARK)
built = model.from_disk(stocks, nifty)
reading = newsview.read_all(news.load(), flows.load_deals(), fundamentals.load_quarterly())
start = reading["time"].min().normalize() + pd.Timedelta(days=7)
keys = ["total_return", "max_drawdown", "benchmark_total_return", "trades", "win_rate"]

for name, needs_model in [("News ideas (good news, model strong, in trend)", True),
                          ("Any good news", False)]:
    result = newsview.backtest_ideas(built, reading, start, require_model=needs_model)
    summary, _ = rotation.summarise(result, nifty)
    print(name, {key: round(float(summary[key]), 3) for key in keys})

summary, _ = rotation.summarise(built.simulate(start=start), nifty)
print("Weekly list, same period", {key: round(float(summary[key]), 3) for key in keys})
